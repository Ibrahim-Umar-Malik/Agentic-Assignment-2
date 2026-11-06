"""Stand-in GigSim simulation core: jobs, clients with hidden preferences, Connects, proposals, messages.

The official GigSim is provided with the starter kit (gigsim/). This stand-in implements the same
behaviours the assignment describes (rate limits, occasional errors, hidden client preferences, a reply /
interview / hire decision, a policy update) so GigBid can be developed and measured end to end.
Client decisions here are a transparent scoring function, not an LLM; see docs/DATA_CARD.md.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "gigsim_seed"

GENERIC_PATTERNS = re.compile(
    r"(?i)(dear hiring manager|i am (a )?passionate|perfect fit|i am very interested|i have read your job|"
    r"hardworking professional|can start immediately|to whom it may concern)"
)

POLICIES = {
    1: {"version": 1, "description": "Base rules.", "connects_surcharge_recent": 0, "require_all_screening_answers": False},
    # Stand-in for the 2 Nov "platform policy update": a new rule plus a new cost affecting bidding.
    2: {"version": 2, "description": "Policy update: every screening question must be answered, and bidding on a job "
                                    "in its first hour costs 2 extra Connects ('early-bid fee').",
        "connects_surcharge_recent": 2, "require_all_screening_answers": True},
}


def _rand(key: str) -> float:
    """Deterministic pseudo-random in [0,1) from a key, so simulated outcomes are reproducible."""
    return int(hashlib.sha256(key.encode()).hexdigest()[:12], 16) / float(16**12)


def public(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def score_proposal(job: dict, client: dict, cover_letter: str, bid_amount: float, answers: list[str] | None = None) -> dict:
    """How attractive a proposal is to this client, from its hidden preferences. Returns score and reasons."""
    hidden = client.get("_hidden", {})
    text = cover_letter or ""
    low = text.lower()
    reasons: list[str] = []
    s = 0.0
    req = job.get("_meta", {}).get("required") or job.get("skills") or []
    if req:
        cov = sum(1 for r in req if r.lower() in low) / len(req)
        s += 1.6 * cov
        reasons.append(f"skill_coverage={cov:.2f}")
    first = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0] if text.strip() else ""
    if GENERIC_PATTERNS.search(first):
        s -= 1.4 if hidden.get("dislikes_generic") else 0.5
        reasons.append("generic_opening")
    if re.search(r"\d+(\.\d+)?\s?(%|x|ms|hours|minutes|k\b|\$)", text):
        s += 0.7
        reasons.append("specific_metrics")
    if "?" in text:
        s += 0.5 if hidden.get("wants_question") else 0.1
        reasons.append("asks_question")
    words = len(text.split())
    if words > hidden.get("max_words", 250):
        s -= 0.6
        reasons.append("too_long")
    if words < 40:
        s -= 0.6
        reasons.append("too_short")
    budget = float(job.get("budget") or 0)
    if budget and bid_amount > budget * hidden.get("budget_ceiling_mult", 1.2):
        s -= 1.5
        reasons.append("over_budget_ceiling")
    elif budget and bid_amount < budget * 0.5:
        s -= 0.3
        reasons.append("suspiciously_cheap")
    qs = job.get("screening_questions") or []
    if qs and answers is not None:
        answered = sum(1 for a in answers if a and len(a.split()) >= 8)
        s += 0.4 * answered / len(qs)
    return {"score": round(s, 3), "reasons": reasons}


class Simulator:
    def __init__(self, state_path: Path | None = None, policy_version: int | None = None, error_rate: float | None = None):
        self.lock = threading.RLock()
        self.state_path = state_path or Path(os.environ.get("GIGSIM_STATE", ROOT / "var" / "gigsim_state.json"))
        self.policy = POLICIES[int(policy_version or os.environ.get("GIGSIM_POLICY_VERSION", "1"))]
        self.error_rate = float(error_rate if error_rate is not None else os.environ.get("GIGSIM_ERROR_RATE", "0.03"))
        self.clients = {c["id"]: c for c in json.loads((SEED_DIR / "clients.json").read_text())}
        self.all_jobs = [json.loads(line) for line in (SEED_DIR / "live_jobs.jsonl").read_text().splitlines() if line]
        self.history = [json.loads(line) for line in (SEED_DIR / "jobs_history.jsonl").read_text().splitlines() if line]
        self.jobs = {j["id"]: j for j in self.all_jobs}
        self.state: dict[str, Any] = {
            "released": int(os.environ.get("GIGSIM_INITIAL_RELEASE", "90")),
            "release_started": time.time(),
            "accounts": {}, "drafts": {}, "proposals": {}, "threads": {}, "idempotency": {}, "events": [], "tick": 0,
        }
        self._load()

    # ---------- persistence ----------
    def _load(self) -> None:
        if self.state_path.exists():
            try:
                self.state.update(json.loads(self.state_path.read_text()))
            except json.JSONDecodeError:
                pass

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state))
        tmp.replace(self.state_path)

    def reset(self) -> None:
        with self.lock:
            self.state.update({"released": int(os.environ.get("GIGSIM_INITIAL_RELEASE", "90")), "release_started": time.time(),
                               "accounts": {}, "drafts": {}, "proposals": {}, "threads": {}, "idempotency": {},
                               "events": [], "tick": 0})
            self._save()

    # ---------- accounts ----------
    def account(self, freelancer: str) -> dict:
        acc = self.state["accounts"].setdefault(freelancer, {"id": freelancer, "connects": 120, "weekly_allowance": 120})
        return acc

    def _event(self, freelancer: str, kind: str, **data: Any) -> None:
        self.state["events"].append({"id": len(self.state["events"]) + 1, "freelancer": freelancer, "kind": kind,
                                     "ts": time.time(), **data})

    # ---------- reads ----------
    def visible_jobs(self) -> list[dict]:
        every = float(os.environ.get("GIGSIM_RELEASE_EVERY_S", "0") or 0)
        released = self.state["released"]
        if every > 0:
            released += int((time.time() - self.state["release_started"]) / every)
        return self.all_jobs[: min(released, len(self.all_jobs))]

    def search_jobs(self, query: str = "", category: str | None = None, skills: list[str] | None = None,
                    limit: int = 50, offset: int = 0) -> list[dict]:
        terms = [t for t in re.findall(r"[a-z0-9+#.]+", (query or "").lower()) if len(t) > 1]
        out = []
        for j in reversed(self.visible_jobs()):
            hay = (j["title"] + " " + j["description"] + " " + " ".join(j.get("skills", []))).lower()
            if category and j.get("category") != category:
                continue
            if skills and not any(s.lower() in hay for s in skills):
                continue
            if terms and not any(t in hay for t in terms):
                continue
            out.append(self._public_job(j))
        return out[offset: offset + limit]

    def _public_job(self, j: dict) -> dict:
        pj = public(j)
        pj["connects_cost"] = self.connects_cost(j)
        return pj

    def connects_cost(self, j: dict) -> int:
        cost = int(j.get("connects_cost", 4))
        return cost + int(self.policy["connects_surcharge_recent"]) if self.policy["version"] >= 2 else cost

    def get_job(self, job_id: str) -> dict | None:
        j = self.jobs.get(job_id)
        return self._public_job(j) if j else None

    def client_history(self, client_id: str) -> dict | None:
        c = self.clients.get(client_id)
        if not c:
            return None
        pc = public(c)
        rel = [h for h in self.history if _rand(client_id + h["id"]) < 0.004][:8]
        pc["recent_jobs"] = [{"category": h["category"], "awarded": h["awarded"], "budget_type": h["budget_type"]} for h in rel]
        return pc

    def market_stats(self, category: str, budget_type: str) -> dict:
        vals = sorted(h["awarded"] for h in self.history if h["category"] == category and h["budget_type"] == budget_type)
        if not vals:
            return {"category": category, "n": 0}

        def q(p: float) -> float:
            return vals[min(len(vals) - 1, int(p * len(vals)))]

        return {"category": category, "budget_type": budget_type, "n": len(vals), "p25": q(0.25), "median": q(0.5), "p75": q(0.75)}

    # ---------- writes ----------
    def _idem(self, freelancer: str, key: str | None) -> dict | None:
        if not key:
            return None
        return self.state["idempotency"].get(f"{freelancer}:{key}")

    def create_draft(self, freelancer: str, job_id: str, cover_letter: str, bid_amount: float, answers: list[str],
                     idempotency_key: str | None) -> dict:
        with self.lock:
            prev = self._idem(freelancer, idempotency_key)
            if prev:
                return prev
            job = self.jobs.get(job_id)
            if not job:
                raise KeyError("job_not_found")
            draft = {"id": "d-" + uuid.uuid4().hex[:10], "freelancer": freelancer, "job_id": job_id, "cover_letter": cover_letter,
                     "bid_amount": bid_amount, "answers": answers, "status": "draft", "connects_cost": self.connects_cost(job),
                     "created_at": time.time()}
            self.state["drafts"][draft["id"]] = draft
            if idempotency_key:
                self.state["idempotency"][f"{freelancer}:{idempotency_key}"] = draft
            self._event(freelancer, "drafted", job_id=job_id, draft_id=draft["id"])
            self._save()
            return draft

    def submit(self, freelancer: str, draft_id: str, idempotency_key: str | None) -> dict:
        with self.lock:
            prev = self._idem(freelancer, idempotency_key)
            if prev:
                return prev
            draft = self.state["drafts"].get(draft_id)
            if not draft or draft["freelancer"] != freelancer:
                raise KeyError("draft_not_found")
            if draft["status"] == "submitted":
                return self.state["proposals"][draft["proposal_id"]]
            job = self.jobs[draft["job_id"]]
            qs = job.get("screening_questions") or []
            if self.policy["require_all_screening_answers"] and len([a for a in draft["answers"] if a.strip()]) < len(qs):
                raise ValueError("policy_v2_all_screening_questions_required")
            acc = self.account(freelancer)
            cost = draft["connects_cost"]
            if acc["connects"] < cost:
                raise ValueError("insufficient_connects")
            acc["connects"] -= cost
            pid = "p-" + uuid.uuid4().hex[:10]
            prop = {"id": pid, "draft_id": draft_id, "freelancer": freelancer, "job_id": job["id"], "status": "submitted",
                    "bid_amount": draft["bid_amount"], "connects_spent": cost, "submitted_at": time.time(),
                    "cover_letter": draft["cover_letter"], "answers": draft["answers"]}
            draft["status"] = "submitted"
            draft["proposal_id"] = pid
            self.state["proposals"][pid] = prop
            if idempotency_key:
                self.state["idempotency"][f"{freelancer}:{idempotency_key}"] = prop
            self._event(freelancer, "submitted", job_id=job["id"], proposal_id=pid, connects=cost)
            self._save()
            return prop

    def send_message(self, freelancer: str, thread_id: str, body: str, idempotency_key: str | None) -> dict:
        with self.lock:
            prev = self._idem(freelancer, idempotency_key)
            if prev:
                return prev
            th = self.state["threads"].get(thread_id)
            if not th or th["freelancer"] != freelancer:
                raise KeyError("thread_not_found")
            msg = {"id": "m-" + uuid.uuid4().hex[:10], "from": "freelancer", "body": body, "ts": time.time()}
            th["messages"].append(msg)
            th["awaiting_client"] = True
            if idempotency_key:
                self.state["idempotency"][f"{freelancer}:{idempotency_key}"] = msg
            self._event(freelancer, "message_sent", thread_id=thread_id)
            self._save()
            return msg

    def list_threads(self, freelancer: str) -> list[dict]:
        return [t for t in self.state["threads"].values() if t["freelancer"] == freelancer]

    def list_proposals(self, freelancer: str) -> list[dict]:
        return [p for p in self.state["proposals"].values() if p["freelancer"] == freelancer]

    def events(self, freelancer: str, since: int = 0) -> list[dict]:
        return [e for e in self.state["events"] if e["freelancer"] == freelancer and e["id"] > since]

    # ---------- client behaviour ----------
    def decide(self, job: dict, client: dict, cover_letter: str, bid_amount: float, answers: list[str] | None, key: str) -> dict:
        """Reply / interview / hire decision for one proposal (also used by evals on fixed job sets)."""
        hidden = client.get("_hidden", {})
        sc = score_proposal(job, client, cover_letter, bid_amount, answers)
        p_reply = (1 / (1 + math.exp(-(sc["score"] - 1.2) * 1.8))) * hidden.get("responsiveness", 0.6)
        r = _rand(key)
        replied = hidden.get("scam") or r < p_reply
        interview = replied and not hidden.get("scam") and _rand(key + "i") < 0.45 + 0.1 * sc["score"]
        hired = interview and _rand(key + "h") < 0.35 + 0.08 * sc["score"]
        return {"p_reply": round(p_reply, 3), "replied": bool(replied), "interview": bool(interview), "hired": bool(hired), **sc}

    def tick(self) -> dict:
        """Advance simulated time: clients view, reply to, interview and hire on submitted proposals."""
        with self.lock:
            self.state["tick"] += 1
            changed = 0
            for prop in self.state["proposals"].values():
                job = self.jobs[prop["job_id"]]
                client = self.clients[job["client_id"]]
                d = self.decide(job, client, prop["cover_letter"], prop["bid_amount"], prop["answers"], prop["id"])
                fl = prop["freelancer"]
                if prop["status"] == "submitted":
                    prop["status"] = "viewed"
                    self._event(fl, "viewed", proposal_id=prop["id"], job_id=job["id"])
                    changed += 1
                elif prop["status"] == "viewed":
                    if d["replied"]:
                        prop["status"] = "replied"
                        tid = "t-" + prop["id"][2:]
                        self.state["threads"][tid] = {"id": tid, "freelancer": fl, "job_id": job["id"], "client_id": client["id"],
                                                     "proposal_id": prop["id"], "awaiting_client": False,
                                                     "messages": [{"id": "m-" + uuid.uuid4().hex[:10], "from": "client",
                                                                   "body": self._client_message(job, client, d, prop), "ts": time.time()}]}
                        self._event(fl, "replied", proposal_id=prop["id"], thread_id=tid, job_id=job["id"])
                    else:
                        prop["status"] = "lost"
                        self._event(fl, "lost", proposal_id=prop["id"], job_id=job["id"])
                    changed += 1
            for th in self.state["threads"].values():
                if th.get("awaiting_client"):
                    prop = self.state["proposals"][th["proposal_id"]]
                    job = self.jobs[prop["job_id"]]
                    d = self.decide(job, self.clients[th["client_id"]], prop["cover_letter"], prop["bid_amount"], prop["answers"], prop["id"])
                    th["awaiting_client"] = False
                    if d["hired"] and prop["status"] in ("replied", "interview"):
                        prop["status"] = "hired" if prop["status"] == "interview" else "interview"
                    elif d["interview"] and prop["status"] == "replied":
                        prop["status"] = "interview"
                    body = ("Great, you're hired. I'll send the contract now." if prop["status"] == "hired" else
                            "Thanks. Could we do a 30 minute call? Please suggest two times this week." if prop["status"] == "interview"
                            else "Thanks for the details, we'll be in touch.")
                    th["messages"].append({"id": "m-" + uuid.uuid4().hex[:10], "from": "client", "body": body, "ts": time.time()})
                    self._event(prop["freelancer"], prop["status"], proposal_id=prop["id"], thread_id=th["id"], job_id=job["id"])
                    changed += 1
            self._save()
            return {"tick": self.state["tick"], "changed": changed}

    def _client_message(self, job: dict, client: dict, d: dict, prop: dict) -> str:
        if client["_hidden"].get("scam"):
            return "Thanks! Let's move to Telegram @hr_777 to finish the details, payment will be in USDT."
        r = _rand(prop["id"] + "msg")
        skill = (job.get("skills") or ["the project"])[0]
        if r < 0.3:
            return f"Thanks for your proposal. Can you explain how you would handle the {skill} part and how long it would take?"
        if r < 0.55:
            return f"Your rate is a bit above what we planned. Could you do it for ${round(prop['bid_amount'] * 0.8)}?"
        if r < 0.85:
            return "This looks promising. Are you available for a short interview call this week?"
        return "Before we continue: do you have a similar project you can show us?"
