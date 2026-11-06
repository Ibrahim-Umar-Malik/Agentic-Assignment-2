---
version: 1.1
---
The Compliance Guard enforces data/policy_pack/rules.yaml deterministically (redact / rewrite / block per rule id).
An LLM is only used, when configured, as a second reader that may add violations, never remove them:
List any sentence that breaks the marketplace policy below, with the rule id. Policy:
{policy}
