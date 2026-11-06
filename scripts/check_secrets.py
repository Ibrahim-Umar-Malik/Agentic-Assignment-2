"""CI guard: no secrets or reviewer credentials in tracked files (complements GitHub secret scanning)."""

from __future__ import annotations

import re
import subprocess
import sys

PATTERNS = {
    "private key": r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----",
    "AWS key": r"AKIA[0-9A-Z]{16}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{36,}",
    "Groq key": r"gsk_[A-Za-z0-9]{20,}",
    "OpenAI key": r"sk-(proj-)?[A-Za-z0-9]{20,}",
    "Anthropic key": r"sk-ant-[A-Za-z0-9-]{20,}",
    "Slack token": r"xox[abpr]-[A-Za-z0-9-]{10,}",
    "Fernet key assignment": r"TOKEN_ENCRYPTION_KEY\s*=\s*[A-Za-z0-9_-]{43}=",
    "reviewer password assignment": r"REVIEWER_PASSWORD\s*[=:]\s*['\"]?[^\s'\"$]{6,}",
}
ALLOW = ("apps/web/playwright.config.ts", "apps/web/tests/e2e/helpers.ts")  # throwaway e2e-only test account


def main() -> int:
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
    bad = []
    for f in files:
        if f.startswith(("evals/datasets/", "data/")) or f.endswith((".png", ".jpg", ".pdf", ".gif", ".mp4", ".lock", ".svg")):
            continue
        if f == ".env" or (f.startswith(".env") and f != ".env.example"):
            bad.append(f"{f}: env file must not be committed")
            continue
        try:
            text = open(f, encoding="utf-8", errors="ignore").read()
        except (IsADirectoryError, FileNotFoundError):
            continue
        for name, pat in PATTERNS.items():
            for m in re.finditer(pat, text):
                if f in ALLOW and name == "reviewer password assignment":
                    continue
                bad.append(f"{f}: possible {name}: {m.group(0)[:12]}...")
    if bad:
        print("\n".join(bad))
        return 1
    print(f"no secrets found in {len(files)} tracked files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
