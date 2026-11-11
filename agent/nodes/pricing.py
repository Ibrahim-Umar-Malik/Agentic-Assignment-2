"""Pricing Strategist: market statistics + client budget + the user's floor; is the Connects cost worth it?"""

from __future__ import annotations

from core import config, llm

from ..handoffs import PriceQuote
from ..mcp_client import ToolGateway
from .common import load_prompt, node


def quote(job: dict, fit: float, stats: dict, floor: float, connects_cost: int, policy: dict | None = None) -> PriceQuote:
    p = config.get("pricing", {})
    bt = job.get("budget_type") or "fixed"
    pct = p["percentile_by_fit"]
    tier = "high" if fit >= 0.7 else "mid" if fit >= 0.5 else "low"
    q = pct[tier]
    if stats.get("n"):
        lo, hi = stats["p25"], stats["p75"]
        market = lo + (hi - lo) * (q - 0.25) / 0.5 if q >= 0.25 else lo
        market = max(lo * 0.8, min(hi * 1.1, market))
    else:
        market = float(job.get("budget") or floor or 50)
    amount = market
    notes = [f"market {stats.get('p25', '?')}-{stats.get('p75', '?')} (p25-p75, n={stats.get('n', 0)}), fit tier {tier} -> p{int(q * 100)}"]
    min_amount = floor if bt == "hourly" else floor * config.get("decision.min_fixed_hours", 8)
    if amount < min_amount:
        amount = min_amount
        notes.append(f"raised to your floor (${min_amount:.0f})")
    budget = float(job.get("budget") or 0)
    # Anchor to the client's stated budget. On real Upwork posts (docs/DATA_CARD.md) the category's paid p25-p75
    # is far below most posted budgets (most contracts are small), so market-only pricing under-bid 24 of 32
    # mispriced tune-split jobs, e.g. $270 on a $4,000 job (report section 8). With a budget, quote a fit-dependent
    # share of it; the market band is used only when the post has no budget. The floor still wins.
    anchor = p.get("budget_anchor", {"max_ratio": 1.0, "share_by_fit": {"high": 0.95, "mid": 0.88, "low": 0.8}})
    if budget:
        target = budget * anchor["share_by_fit"][tier]
        amount = max(min_amount, min(budget * anchor["max_ratio"], target))
        notes.append(f"{int(anchor['share_by_fit'][tier] * 100)}% of the client's budget (${budget:.0f}) for a {tier} fit")
        if amount > budget * anchor["max_ratio"]:
            notes.append("your floor is above the client's budget")
    amount = round(amount, 0) if bt == "hourly" else round(amount / 10) * 10
    p_win = max(0.02, min(0.35, 0.05 + 0.3 * fit))
    value = amount * (20 if bt == "hourly" else 1)  # expected engagement value
    connects_usd = connects_cost * p["usd_per_connect"]
    ev = p_win * value * 0.1  # margin-weighted expected value of the bid
    worth = connects_cost <= p["max_connects_per_bid"] and (connects_usd == 0 or ev / connects_usd >= p["min_expected_value_ratio"])
    if policy and policy.get("version", 1) >= 2 and policy.get("connects_surcharge_recent"):
        notes.append(f"includes policy v{policy['version']} early-bid fee")
    return PriceQuote(amount=amount, budget_type=bt, rationale="; ".join(notes), market=stats, floor=floor,
                      connects_cost=connects_cost, connects_usd=round(connects_usd, 2), expected_value_usd=round(ev, 2),
                      worth_connects=worth)


@node("pricing")
async def pricing(state: dict) -> dict:
    gw = ToolGateway(state["user_id"])
    job = state["job"]
    stats = await gw.call("pricing", "marketplace", "get_market_stats",
                          {"category": job.get("category") or "unknown", "budget_type": job.get("budget_type") or "fixed"})
    try:
        policy = await gw.call("pricing", "marketplace", "get_policy", {})
    except Exception:
        policy = {}
    floor = float((state.get("meta") or {}).get("hourly_floor") or 0)
    pq = quote(job, (state.get("fit") or {}).get("fit_score", 0), stats, floor, int(job.get("connects_cost") or 0), policy)
    if not llm.is_offline("pricing"):
        _, system = load_prompt("pricing")
        text = await llm.call("pricing", system, f"Quote: {pq.model_dump_json()}\nJob budget: {job.get('budget')} {job.get('budget_type')}")
        if text:
            pq.rationale = f"{text.strip()} ({pq.rationale})"
    out = {"price": pq.model_dump(), "meta": {"marketplace_policy": {k: policy.get(k) for k in
                                                                ("version", "require_all_screening_answers", "connects_surcharge_recent")}},
           "_summary": f"${pq.amount:.0f} {pq.budget_type}; Connects {pq.connects_cost} worth it: {pq.worth_connects}"}
    if not pq.worth_connects:
        out.update({"status": "skipped", "status_reason": f"Connects not worth it: EV ${pq.expected_value_usd} vs cost ${pq.connects_usd}",
                    "decision": {**state.get("decision", {}), "action": "skip",
                                 "reasons": (state.get("decision") or {}).get("reasons", []) + ["pricing: Connects cost not worth it"]}})
    return out
