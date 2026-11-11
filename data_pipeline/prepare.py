"""Build GigBid's evaluation and simulation data from public Kaggle datasets, plus labelled synthetic parts.

    python -m data_pipeline.prepare            # downloads with kagglehub (cached), writes everything below
    python -m data_pipeline.prepare --raw DIR  # use already-downloaded CSVs under DIR

What is REAL (copied or derived from the datasets, see docs/DATA_CARD.md for licences and attribution):
  * job titles, descriptions, Upwork skill tags, budgets / hourly ranges, Connects cost, experience level   [A]
  * client signals: payment verified, total spent, rating, number of reviews, country, applicant counts      [A]
  * market prices: paid hourly rates and fixed-price totals by category (1.29M contracts)                     [C]
  * posted budgets and hourly ranges by category (2024 postings)                                              [U, T]
  * a real fake-job-posting corpus used only as an external benchmark for the Risk agent (not redistributed)  [F]
  * persona profile defaults for job success and response time                                               [S]

What is SYNTHETIC (and flagged with "_provenance" on every record):
  * the three freelancer portfolios (case studies, repos, reviews, past proposals): scripts/generate_standin_data.py
  * screening questions, posting times, and the adversarial overlays (scam text, prompt injections, reposts)
    added on top of real job posts so safety can be measured with known ground truth
  * clients' hidden preferences inside GigSim (no public dataset has client reply behaviour)

Gold labels on real jobs are SILVER labels from documented rules (see label_job); a hand-audit sample is
written to evals/datasets/label_audit.csv for human checking.

Sources:
  [A] ahmedmyalo/upwork-freelance-jobs-60k (Apache 2.0)
  [U] asaniczka/upwork-job-postings-dataset-2024-50k-records (ODC-By)
  [T] asaniczka/all-jobs-on-upwork-200k-plus (ODC-By)
  [C] asaniczka/freelance-contracts-dataset-1-3-million-entries (ODC-By)
  [S] sarveshchhetri/freelancer-success-earnings-and-churn-prediction (Apache 2.0; itself synthetic)
  [F] adityammantri/trial-1, "Fake-Job-Posting-Detection" (licence: Unknown, so used locally only)
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from data_pipeline.categories import PERSONA_CATEGORIES, categorize
from data_pipeline.tag_competence import coverage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_standin_data as standin  # noqa: E402

from rag.index.skills import MARKET_SKILLS, find_skills  # noqa: E402

SEED = 4016
DATASETS = {
    "A": "ahmedmyalo/upwork-freelance-jobs-60k",
    "U": "asaniczka/upwork-job-postings-dataset-2024-50k-records",
    "T": "asaniczka/all-jobs-on-upwork-200k-plus",
    "C": "asaniczka/freelance-contracts-dataset-1-3-million-entries",
    "S": "sarveshchhetri/freelancer-success-earnings-and-churn-prediction",
    "F": "adityammantri/trial-1",
}
LICENCES = {"A": "Apache 2.0", "U": "ODC-By 1.0", "T": "ODC-By 1.0", "C": "ODC-By 1.0", "S": "Apache 2.0", "F": "Unknown"}
PROCESSED = ROOT / "data" / "processed"  # gitignored: large intermediate files
REAL = ROOT / "data" / "real"  # committed: small derived files with attribution

URL_RX = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RX = re.compile(r"(?<![\w$])\+?\d[\d\s().-]{8,}\d(?![\d,.]*\s?(?:k|usd|\$))")
MONEY_RX = re.compile(r"[-+]?\d[\d,]*\.?\d*")
APPLICANTS = {"Less than 5": 3, "5 to 10": 7, "10 to 15": 12, "15 to 20": 17, "20 to 50": 35, "50+": 60}

# Kinds of dev-set job and their share. "fit"/"weak_fit"/"off_domain"/"lowball" come from real labels;
# "scam", "injection" and "duplicate" are synthetic overlays on real posts.
OVERLAY_SHARE = {"scam": 0.10, "injection": 0.10, "duplicate": 0.06}
FIT_SHARE = 0.55  # share of in-domain draws sampled from fit-labelled jobs


# ---------------------------------------------------------------- loading
def paths(raw: str | None) -> dict[str, Path]:
    if raw:
        base = Path(raw)
        return {k: base / v.split("/")[1] for k, v in DATASETS.items()}
    import kagglehub  # only needed when downloading

    return {k: Path(kagglehub.dataset_download(v)) for k, v in DATASETS.items()}


def clean_text(s: object) -> str:
    if not isinstance(s, str):
        return ""
    s = html.unescape(s).replace("\r", "")
    s = URL_RX.sub("[link removed]", s)
    s = EMAIL_RX.sub("[email removed]", s)
    s = PHONE_RX.sub("[phone removed]", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def money(s: object) -> float | None:
    if isinstance(s, (int, float)) and not (isinstance(s, float) and math.isnan(s)):
        return float(s)
    if not isinstance(s, str):
        return None
    m = MONEY_RX.search(s.replace("$", ""))
    try:
        return float(m.group().replace(",", "")) if m else None
    except ValueError:
        return None


def english(s: str) -> bool:
    return bool(s) and sum(c.isascii() for c in s) / len(s) > 0.97


def stable_id(prefix: str, key: str) -> str:
    return f"{prefix}-{hashlib.sha1(key.encode()).hexdigest()[:10]}"


def load_jobs_a(p: Path) -> pd.DataFrame:
    a = pd.read_csv(next(p.glob("*.csv")), low_memory=False)
    a["tags"] = a[[f"Category_{i}" for i in range(1, 10)]].apply(lambda r: [x.strip() for x in r if isinstance(x, str)], axis=1)
    a["title"] = a["Job Title"].map(clean_text)
    a["description"] = a["Description"].map(clean_text)
    a["hourly"] = a["Payment_type"].eq("Hourly")
    a["rate_lo"] = a["Start_rate"].map(money)
    a["rate_hi"] = a["End_rate"].map(money)
    a["fixed_budget"] = a["Job_Cost"].map(money)
    a["connects"] = pd.to_numeric(a["Connects_Num"], errors="coerce")
    a["applicants"] = a["Applicants_Num"].map(APPLICANTS)
    a["payment_verified"] = a["Payment_Situation"].eq("Payment verified")
    a["spent"] = pd.to_numeric(a["Spent($)"], errors="coerce")
    a["rating"] = pd.to_numeric(a["Rating"], errors="coerce")
    a["reviews"] = pd.to_numeric(a["Feedback_Num"], errors="coerce")
    a["country"] = a["Client_Country"].fillna("Unknown")
    a["level"] = a["EX_level_demand"].fillna("Unknown")
    a["url_key"] = a["Job_URL"].astype(str).str.extract(r"(~[0-9a-f]+)", expand=False).fillna(a["Job_URL"].astype(str))
    n0 = len(a)
    a = a.drop_duplicates("url_key").copy()
    a["dedupe_key"] = (a["title"].str.lower().str.slice(0, 80) + "|" + a["description"].str.lower().str.slice(0, 200))
    a = a.drop_duplicates("dedupe_key")
    stats = {"rows_raw": n0, "after_url_dedupe": None, "after_text_dedupe": len(a)}
    a = a[a["description"].str.len().between(150, 6000) & a["description"].map(english) & a["title"].map(english)]
    stats["after_length_language_filter"] = len(a)
    cats = [categorize(t, g, d) for t, g, d in zip(a["title"], a["tags"], a["description"], strict=True)]
    a["category"] = [c for c, _ in cats]
    a.attrs["stats"] = stats
    return a


def contract_prices(p: Path, rng_seed: int = SEED, n: int = 300_000) -> pd.DataFrame:
    c = pd.read_csv(next(p.glob("*.csv")))
    c = c.sample(min(n, len(c)), random_state=rng_seed)
    c["category"] = [categorize(t)[0] for t in c["job_title"].astype(str)]
    return c


def postings_prices(pu: Path, pt: Path) -> pd.DataFrame:
    frames = [pd.read_csv(next(pu.glob("*.csv")), usecols=["title", "is_hourly", "hourly_low", "hourly_high", "budget", "published_date"])]
    for f in sorted(pt.glob("*.csv")):
        frames.append(pd.read_csv(f, usecols=["title", "is_hourly", "hourly_low", "hourly_high", "budget", "published_date"]))
    t = pd.concat(frames, ignore_index=True).drop_duplicates(["title", "published_date"])
    t = t.sample(min(250_000, len(t)), random_state=SEED)
    t["category"] = [categorize(x)[0] for x in t["title"].astype(str)]
    return t


# ---------------------------------------------------------------- market statistics
def q(series: pd.Series) -> dict:
    s = series.dropna()
    s = s[s > 0]
    if len(s) < 5:
        return {"n": int(len(s))}
    return {"n": int(len(s)), "p10": round(float(s.quantile(0.10)), 1), "p25": round(float(s.quantile(0.25)), 1),
            "median": round(float(s.median()), 1), "p75": round(float(s.quantile(0.75)), 1), "p90": round(float(s.quantile(0.90)), 1)}


def market_stats(c: pd.DataFrame, t: pd.DataFrame) -> dict:
    out: dict = {"_sources": {"paid": "C contracts (sample of 300k)", "posted": "U+T postings 2024 (sample of 250k)"}}
    for cat in sorted(set(c["category"]) | set(t["category"])):
        cc, tt = c[c["category"] == cat], t[t["category"] == cat]
        posted_hourly = (tt["hourly_low"].fillna(tt["hourly_high"]) + tt["hourly_high"].fillna(tt["hourly_low"])) / 2
        out[cat] = {
            "paid_hourly_rate": q(cc["hourly_rate"]),
            "paid_fixed_total": q(cc.loc[cc["hourly_rate"].isna(), "total_paid"]),
            "posted_hourly_mid": q(posted_hourly[tt["is_hourly"] == True]),  # noqa: E712
            "posted_fixed_budget": q(tt.loc[tt["is_hourly"] == False, "budget"]),  # noqa: E712
        }
    return out


def jobs_history(c: pd.DataFrame, n: int = 3000) -> list[dict]:
    """Real awarded prices for GigSim's market_stats tool (replaces the synthetic history)."""
    rows = []
    cand = c[c["category"] != "other"].copy()
    cand["budget_type"] = cand["hourly_rate"].notna().map({True: "hourly", False: "fixed"})
    cand["awarded"] = cand["hourly_rate"].where(cand["hourly_rate"].notna(), cand["total_paid"])
    cand = cand[cand["awarded"] > 0]
    cand = cand.sample(min(n, len(cand)), random_state=SEED)
    for r in cand.itertuples():
        closed = str(r.end_date)[:10] if isinstance(r.end_date, str) else str(r.start_date)[:10]
        rows.append({"id": stable_id("h", str(r.job_id) + str(r.freelancer_id)), "category": r.category,
                     "budget_type": r.budget_type, "awarded": round(float(r.awarded), 1), "proposals": None,
                     "closed_at": closed, "_provenance": "real:C"})
    return rows


# ---------------------------------------------------------------- personas and labels
def persona_vocab(key: str) -> list[str]:
    return sorted({s for p in standin.PERSONAS[key]["projects"] for s in p.skills + p.implied})


def job_skills(row: dict, vocab: list[str]) -> list[str]:
    text = " ".join([row["title"], " | ".join(row["tags"]), row["description"]])
    return find_skills(text, sorted(set(vocab) | set(MARKET_SKILLS)))


def label_job(row: dict, persona: str, market: dict, floor: float) -> dict:
    """Silver labels for one real job and one persona. Rules (documented in DATA_CARD):
    - evidence: persona projects sharing a canonical skill named in the title/tags (and the job's category, or
      a second shared skill), or sharing >= 3 canonical skills anywhere in the post;
    - fit: category belongs to the persona, >= 60% of the job's (non-neutral) Upwork tags are tags the persona
      can claim (data_pipeline/tag_competence.py), at least 2 such tags, and >= 1 evidence project;
      otherwise weak_fit (in-domain) or off_domain;
    - lowball: hourly max below 60% of the persona's floor, or a fixed budget below the category's paid p25;
    - bid: fit (or injection on a fit job) and payment verified and not lowball.
    """
    vocab = persona_vocab(persona)
    skills = job_skills(row, vocab)  # canonical skills anywhere in the post (used by retrieval gold)
    strong = find_skills(row["title"] + " | " + " | ".join(row["tags"]), sorted(set(vocab) | set(MARKET_SKILLS)))
    cov, have, miss = coverage(persona, row["tags"], vocab)
    evidence = []
    for p in standin.PERSONAS[persona]["projects"]:
        ps = {s.lower() for s in p.skills + p.implied}
        shared_strong = sum(1 for s in strong if s.lower() in ps)
        shared_all = sum(1 for s in skills if s.lower() in ps)
        if (shared_strong >= 1 and (p.category == row["category"] or shared_all >= 2)) or shared_all >= 3:
            evidence.append(p.slug)
    in_domain = row["category"] in PERSONA_CATEGORIES[persona]
    n_real = len(have) + len(miss)
    if not in_domain:
        kind = "off_domain"
        evidence = []
    elif cov >= 0.6 and n_real >= 2 and evidence:
        kind = "fit"
    else:
        kind = "weak_fit"
    coverage_ = cov
    m = market.get(row["category"]) or market.get("other") or {}
    paid_fixed = m.get("paid_fixed_total", {})
    if row["budget_type"] == "hourly":
        lo, hi = row.get("rate_lo"), row.get("rate_hi")
        lowball = hi is not None and hi < 0.6 * floor
        if lo and hi:
            band = [round(lo), round(hi)]
        elif hi:
            band = [round(0.7 * hi), round(hi)]
        else:
            ph = m.get("paid_hourly_rate", {})
            band = [ph.get("p25", floor), ph.get("p75", floor * 1.5)]
    else:
        b = row["budget"]
        lowball = bool(b) and b < paid_fixed.get("p25", 50)
        band = [round(0.75 * b), round(b)] if b else [paid_fixed.get("p25", 100), paid_fixed.get("p75", 500)]
    if kind == "fit" and lowball:
        kind = "lowball"
    return {"skills_normalised": skills, "persona_coverage": round(coverage_, 2), "tags_missing": miss, "evidence": sorted(set(evidence)),
            "kind": kind, "lowball": lowball, "fair_band": band, "in_domain": in_domain}


def make_client(row: dict, rng: random.Random, scam: bool = False) -> dict:
    """A GigSim client from a REAL client record (fields from [A]); hidden preferences are synthetic."""
    applicants = row.get("applicants") or 12
    # More competition, less chance a given proposal gets read: calibrated on real applicant counts.
    responsiveness = round(max(0.15, min(0.95, 0.95 - 0.12 * math.log1p(applicants))) * rng.uniform(0.85, 1.1), 2)
    reviews = int(row.get("reviews") or 0)
    return {
        "id": stable_id("c", row["url_key"]), "name": f"Client {row['url_key'][-6:]}", "country": row["country"],
        "industry": None, "payment_verified": bool(row["payment_verified"]),
        "total_spent": float(row["spent"]) if row.get("spent") == row.get("spent") and row.get("spent") is not None else 0.0,
        "hires": reviews, "jobs_posted": reviews + rng.randint(0, 6),
        "avg_rating": float(row["rating"]) if row.get("rating") == row.get("rating") and row.get("rating") else None,
        "member_since": None,
        "_hidden": {"budget_ceiling_mult": round(rng.uniform(0.95, 1.3), 2), "dislikes_generic": rng.random() < 0.7,
                    "wants_question": rng.random() < 0.4, "max_words": rng.choice([150, 200, 250, 350]),
                    "responsiveness": responsiveness, "scam": scam},
        "_provenance": {"real:A": ["country", "payment_verified", "total_spent", "hires(=reviews)", "avg_rating"],
                        "synthetic": ["_hidden", "jobs_posted offset", "name"]},
    }


def to_job(row: dict, jid: str, persona: str, client: dict, posted: datetime, rng: random.Random) -> dict:
    hourly = row["budget_type"] == "hourly"
    budget = row["rate_hi"] if hourly else row["budget"]
    questions = rng.sample(["Describe a similar project you have completed.", "What is your availability per week?",
                            "Share a link to relevant work.", "What would you need from us to start?",
                            f"How would you approach the {row['tags'][0] if row['tags'] else 'main'} part?"], rng.randint(0, 3))
    return {
        "id": jid, "title": row["title"], "description": row["description"], "skills": row["tags"][:8],
        "category": row["category"], "budget_type": row["budget_type"], "budget": round(float(budget), 2) if budget else None,
        "client_id": client["id"], "connects_cost": int(row["connects"]) if row["connects"] == row["connects"] else 6,
        "screening_questions": questions, "posted_at": posted.isoformat() + "Z", "experience_level": row["level"],
        "_meta": {"persona": persona, "required": row["tags"][:6], "source": "A", "source_key": row["url_key"],
                  "applicants": row.get("applicants")},
        "_provenance": {"real:A": ["title", "description", "skills", "budget", "connects_cost", "experience_level"],
                        "synthetic": ["screening_questions", "posted_at"]},
    }


# ---------------------------------------------------------------- build
def build(raw: str | None, out: Path) -> dict:
    rng = random.Random(SEED)
    P = paths(raw)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    REAL.mkdir(parents=True, exist_ok=True)

    a = load_jobs_a(P["A"])
    a = a[(a["hourly"] & a["rate_hi"].notna()) | (~a["hourly"] & a["fixed_budget"].notna() & (a["fixed_budget"] > 0))].copy()
    a["budget_type"] = a["hourly"].map({True: "hourly", False: "fixed"})
    a["budget"] = a["fixed_budget"].where(~a["hourly"], a["rate_hi"])
    stats = dict(a.attrs.get("stats", {}), after_budget_filter=len(a))
    cache_c, cache_t = PROCESSED / "contracts_categorised.pkl", PROCESSED / "postings_categorised.pkl"
    if cache_c.exists() and cache_t.exists():
        c, t = pd.read_pickle(cache_c), pd.read_pickle(cache_t)
    else:
        c, t = contract_prices(P["C"]), postings_prices(P["U"], P["T"])
        c.to_pickle(cache_c)
        t.to_pickle(cache_t)
    market = market_stats(c, t)
    (REAL / "market_stats.json").write_text(json.dumps(market, indent=1))
    hist = jobs_history(c)
    (out / "data" / "gigsim_seed" / "jobs_history.jsonl").write_text("\n".join(json.dumps(h) for h in hist) + "\n")

    # Persona calibration from real data: floor = median paid hourly rate across the persona's categories [C];
    # job success and response-time defaults from [S] (a synthetic third-party dataset; cosmetic fields only).
    s_df = pd.read_csv(next(P["S"].glob("*.csv")))
    s_map = {"ai_ml": "AI & Machine Learning", "fullstack": "Web Development", "data_analyst": "Data Science & Analytics"}
    floors = {}
    for persona, cats in PERSONA_CATEGORIES.items():
        rates = c.loc[c["category"].isin(cats) & (c["hourly_rate"] > 0), "hourly_rate"]
        floors[persona] = int(round(float(rates.median())))
        prof_path = out / "data" / "personas" / persona / "profile.json"
        prof = json.loads(prof_path.read_text())
        srow = s_df[s_df["primary_skill"] == s_map[persona]]
        prof.update({"hourly_floor_usd": floors[persona],
                     "job_success_rate": round(float(srow["job_success_rate"].median()), 1),
                     "avg_response_time_hrs": round(float(srow["avg_response_time_hrs"].median()), 1),
                     "_provenance": {"synthetic": ["name", "headline", "skills", "portfolio"],
                                     "real:C": ["hourly_floor_usd (median paid hourly rate in persona categories)"],
                                     "third_party_synthetic:S": ["job_success_rate", "avg_response_time_hrs"]}})
        prof_path.write_text(json.dumps(prof, indent=2))

    rows = a.to_dict("records")
    rng.shuffle(rows)
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    used: set[str] = set()

    def take(cats: set[str] | None, pred=None) -> dict | None:
        pool = [r for cat in (cats or by_cat.keys()) for r in by_cat.get(cat, [])]
        rng.shuffle(pool)
        for r in pool:
            if r["url_key"] not in used and (pred is None or pred(r)):
                used.add(r["url_key"])
                return r
        return None

    clients: dict[str, dict] = {}
    scam_pool = [r for r in rows if not (r.get("spent") or 0) > 0]  # real brand-new client accounts ($0 spent)
    t0 = datetime(2026, 10, 1, 8, 0)
    audit: list[dict] = []
    summary: dict = {"stats": stats, "floors": floors, "dev": {}, "live": {}}

    def one(persona: str, jid: str, posted: datetime, want: str, history: list[dict]) -> dict | None:
        cats = PERSONA_CATEGORIES[persona]
        other = set(by_cat) - cats
        if want == "duplicate":
            if not history:
                return None
            src = rng.choice(history)
            job = json.loads(json.dumps(src))
            job["id"], job["posted_at"] = jid, posted.isoformat() + "Z"
            job["title"] = job["title"] + rng.choice(["", " (reposted)", " - urgent"])
            job["_gold"] = dict(src["_gold"], duplicate_of=src["id"], bid=False, kind="duplicate")
            job["_provenance"] = dict(src["_provenance"], overlay="synthetic:duplicate_repost")
            return job
        def is_fit(r: dict) -> bool:
            return label_job(r, persona, market, floors[persona])["kind"] in ("fit", "lowball")

        if want == "off_domain":
            row = take(other)
        elif want in ("scam", "injection") or (want == "in_domain" and rng.random() < FIT_SHARE):
            # Overlays go on jobs the persona would want (that is where a scam or an injection does harm), and
            # half the in-domain draws are fit jobs so both classes are measurable (stratified sampling).
            row = take(cats, is_fit)
        else:
            row = take(cats)
        if row is None:
            return None
        lab = label_job(row, persona, market, floors[persona])
        scam = want == "scam"
        client = make_client(row, rng, scam=False)
        if scam and scam_pool:
            client = make_client(dict(rng.choice(scam_pool), url_key=row["url_key"]), rng, scam=True)
        clients[client["id"]] = client
        job = to_job(row, jid, persona, client, posted, rng)
        scam_type = injection = None
        if scam:
            scam_type, text = rng.choice(standin.SCAM_PATTERNS)
            job["description"] += "\n\n" + text.format(handle=f"hr_{rng.randint(100, 999)}", thing=(row["tags"] or ["the project"])[0])
            job["_provenance"]["overlay"] = "synthetic:scam_text"
        if want == "injection":
            injection, text = rng.choice(standin.INJECTIONS)
            paras = job["description"].split("\n")
            paras.insert(rng.randint(1, max(1, len(paras))), text)
            job["description"] = "\n".join(paras)
            job["_provenance"]["overlay"] = "synthetic:prompt_injection"
        kind = "scam" if scam else ("injection" if want == "injection" and lab["kind"] == "fit" else lab["kind"])
        bid = (lab["kind"] == "fit") and not scam and client["payment_verified"]
        job["_meta"]["required"] = row["tags"][:6] or lab["skills_normalised"][:6]
        job["_meta"]["fair"] = round(sum(lab["fair_band"]) / 2, 1)
        job["_gold"] = {"bid": bid, "scam": scam, "scam_type": scam_type, "injection": injection, "kind": kind,
                        "off_domain": not lab["in_domain"], "evidence": lab["evidence"] if not scam else lab["evidence"],
                        "fair_band": lab["fair_band"], "duplicate_of": None, "lowball": lab["lowball"],
                        "skills_normalised": lab["skills_normalised"], "persona_coverage": lab["persona_coverage"],
                        "label_source": "silver_rules_v1"}
        return job

    def plan(n: int) -> list[str]:
        out_ = []
        for _ in range(n):
            r = rng.random()
            if r < OVERLAY_SHARE["scam"]:
                out_.append("scam")
            elif r < OVERLAY_SHARE["scam"] + OVERLAY_SHARE["injection"]:
                out_.append("injection")
            elif r < sum(OVERLAY_SHARE.values()):
                out_.append("duplicate")
            elif r < sum(OVERLAY_SHARE.values()) + 0.22:
                out_.append("off_domain")
            else:
                out_.append("in_domain")
        return out_

    all_live = []
    for persona in PERSONA_CATEGORIES:
        dev: list[dict] = []
        for i, want in enumerate(plan(200)):
            job = one(persona, f"dev-{persona}-{i:03d}", t0 + timedelta(minutes=37 * i), want, dev)
            if job:
                dev.append(job)
        (out / "evals" / "datasets" / f"dev_{persona}.jsonl").write_text("\n".join(json.dumps(j) for j in dev) + "\n")
        summary["dev"][persona] = pd.Series([j["_gold"]["kind"] for j in dev]).value_counts().to_dict()
        summary["dev"][persona]["bid_true"] = sum(j["_gold"]["bid"] for j in dev)
        for j in dev[::10][:15]:
            audit.append({"id": j["id"], "persona": persona, "title": j["title"], "category": j["category"],
                          "silver_kind": j["_gold"]["kind"], "silver_bid": j["_gold"]["bid"],
                          "silver_evidence": ";".join(j["_gold"]["evidence"]), "human_kind": "", "human_bid": "", "notes": ""})
        live = []
        for i, want in enumerate(plan(60)):
            if want == "duplicate":
                want = "in_domain"
            job = one(persona, f"j-{persona}-{i:03d}", t0 + timedelta(days=30, minutes=23 * i), want, live)
            if job:
                job["_meta"]["kind"] = job["_gold"]["kind"]
                live.append(job)
        summary["live"][persona] = len(live)
        all_live.extend(live)
    rng.shuffle(all_live)
    (out / "data" / "gigsim_seed" / "live_jobs.jsonl").write_text("\n".join(json.dumps(j) for j in all_live) + "\n")
    (out / "data" / "gigsim_seed" / "clients.json").write_text(json.dumps(sorted(clients.values(), key=lambda c: c["id"]), indent=1))
    pd.DataFrame(audit).to_csv(out / "evals" / "datasets" / "label_audit.csv", index=False)

    # Category distribution and a 5k sample of cleaned real jobs (attributed, PII-scrubbed) for reuse.
    summary["category_counts"] = a["category"].value_counts().to_dict()
    sample = a.sample(min(5000, len(a)), random_state=SEED)
    with (REAL / "jobs_sample.jsonl").open("w") as f:
        for r in sample.itertuples():
            f.write(json.dumps({"key": r.url_key, "title": r.title, "description": r.description, "tags": r.tags,
                                "category": r.category, "budget_type": r.budget_type, "budget": r.budget,
                                "rate_lo": r.rate_lo, "rate_hi": r.rate_hi, "connects": r.connects, "level": r.level,
                                "payment_verified": bool(r.payment_verified), "client_spent": r.spent,
                                "client_rating": r.rating, "client_reviews": r.reviews, "client_country": r.country,
                                "applicants": r.applicants, "source": "A"}, default=_num) + "\n")
    (REAL / "summary.json").write_text(json.dumps(summary, indent=1, default=_num))
    return summary


def _num(x):
    try:
        f = float(x)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return str(x)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=None, help="directory holding the six dataset folders (else kagglehub download)")
    ap.add_argument("--out", default=str(ROOT))
    args = ap.parse_args()
    s = build(args.raw, Path(args.out))
    print(json.dumps({k: s[k] for k in ("stats", "floors", "dev", "live")}, indent=1, default=_num))


if __name__ == "__main__":
    main()
