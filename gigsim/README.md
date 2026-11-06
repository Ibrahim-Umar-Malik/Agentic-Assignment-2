# gigsim/ (PROVIDED by the starter kit, do not modify)

This folder is reserved for the official GigSim marketplace simulator from the AI-4016 starter kit.
CI fails if anything under `gigsim/` changes after the official kit is committed (see `scripts/check_gigsim_unchanged.py`).

Until the official kit is dropped in, GigBid runs against `gigsim_standin/`, a simulator with the same
behaviours (REST API, Connects, proposals, messages, rate limits, occasional 5xx, hidden client
preferences, a policy update). The only code that knows GigSim's HTTP shape is
`mcp_servers/marketplace/adapters/gigsim.py`; point `GIGSIM_URL` at the official simulator and adjust the
endpoint paths in that one file if they differ.
