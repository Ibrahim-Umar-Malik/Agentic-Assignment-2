"""CI guard: every prompt lives in agent/prompts/*.md with a version header, and no node embeds a long inline prompt."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    bad = []
    for p in sorted((ROOT / "agent" / "prompts").glob("*.md")):
        head = p.read_text().split("---")
        if len(head) < 3 or "version:" not in head[1]:
            bad.append(f"{p.relative_to(ROOT)}: missing '---\\nversion: x\\n---' header")
    for p in (ROOT / "agent").rglob("*.py"):
        src = p.read_text()
        for m in re.finditer(r'"""(.*?)"""', src, re.S):
            body = m.group(1)
            if re.search(r"(?i)\byou are (a|an|the)\b", body) and len(body) > 200:
                bad.append(f"{p.relative_to(ROOT)}: inline prompt-like string; move it to agent/prompts/")
        if re.search(r'(?i)("|\')you are (a|an|the) [^"\']{60,}', src) and "prompts" not in p.parts:
            bad.append(f"{p.relative_to(ROOT)}: inline prompt string; move it to agent/prompts/")
    if bad:
        print("\n".join(bad))
        return 1
    print("prompts: all versioned, none inline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
