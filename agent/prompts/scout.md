---
version: 1.0
---
The Scout is deterministic (no LLM): it runs saved searches on schedule, normalises job posts, de-duplicates them by a
fingerprint of client id + normalised title + first 200 characters of the description, and queues new jobs.
This file documents its rules so every node has a versioned prompt file.
