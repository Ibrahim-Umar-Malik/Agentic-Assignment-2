"""CI guard: gigsim/ (the provided simulator) must not change after the official kit is committed.

The first commit that adds files under gigsim/ other than README.md is treated as the kit drop; any later diff to
those files fails CI. Until the kit is present only README.md exists and the check passes trivially."""

from __future__ import annotations

import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False).stdout.strip()


def main() -> int:
    files = [f for f in git("ls-files", "gigsim").splitlines() if f != "gigsim/README.md"]
    if not files:
        print("gigsim/: official kit not committed yet (only README.md) - nothing to protect")
        return 0
    first = git("log", "--diff-filter=A", "--format=%H", "--reverse", "--", *files).splitlines()
    if not first:
        return 0
    changed = git("diff", "--name-only", first[0], "HEAD", "--", "gigsim").splitlines()
    changed += git("diff", "--name-only", "--", "gigsim").splitlines()
    changed = sorted({c for c in changed if c != "gigsim/README.md"})
    if changed:
        print("gigsim/ was modified after the kit was committed:\n  " + "\n  ".join(changed))
        return 1
    print(f"gigsim/ unchanged since {first[0][:8]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
