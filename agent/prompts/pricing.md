---
version: 1.0
---
The Pricing Strategist is rule-based by design (config: pricing.*): bid = market percentile chosen by fit, clamped to
the freelancer's floor and the client's budget band; the Connects cost is worth it only when expected value / Connects
cost in USD clears pricing.min_expected_value_ratio. An LLM only writes the one-paragraph rationale when available.
Write a two-sentence rationale for the freelancer explaining the number. Do not change the number.
