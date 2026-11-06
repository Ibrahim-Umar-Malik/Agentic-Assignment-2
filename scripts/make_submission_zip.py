"""Build the submission ZIP: every file git tracks or would track (respects .gitignore, so no .env, .venv,
node_modules, var/ or build output), plus a copy of the report PDF, write-up and video script beside it.

    python scripts/make_submission_zip.py [OUT_DIR]   # default: dist/submission
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRAS = ["docs/report/GigBid_RnD_Report.pdf", "docs/writeup.md", "docs/VIDEO_SCRIPT.md", "docs/RESUME_BULLET.md"]
FORBIDDEN = (".env", "credentials", "id_rsa")


def files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                         cwd=ROOT, check=True, capture_output=True).stdout.decode()
    names = sorted({n for n in out.split("\0") if n and (ROOT / n).is_file()})
    bad = [n for n in names if Path(n).name in FORBIDDEN or (Path(n).name.startswith(".env") and n != ".env.example"
                                                                and not n.endswith("/.env.example"))]
    if bad:
        raise SystemExit(f"refusing to package secrets-like files: {bad}")
    return names


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "submission"
    out_dir.mkdir(parents=True, exist_ok=True)
    zpath = out_dir / "gigbid-source.zip"
    names = files()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.write(ROOT / n, f"gigbid/{n}")
    for e in EXTRAS:
        if (ROOT / e).exists():
            shutil.copy2(ROOT / e, out_dir / Path(e).name)
    print(f"wrote {zpath} ({len(names)} files, {zpath.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
