"""Build docs/report/GigBid_RnD_Report.pdf from docs/report/report.md (pandoc -> HTML -> headless Chromium PDF).

    python -m evals.make_tables && python scripts/build_report.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "report" / "report.md"
OUT = ROOT / "docs" / "report" / "GigBid_RnD_Report.pdf"

CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
body { font-family: "Helvetica Neue", Arial, sans-serif; font-size: 9.6pt; line-height: 1.38; color: #1d2329; }
header#title-block-header { border-bottom: 2px solid #1f6f5c; margin-bottom: 10px; padding-bottom: 6px; }
h1.title { font-size: 20pt; margin: 0; color: #1f6f5c; }
p.subtitle { font-size: 11pt; margin: 2px 0; color: #444; }
p.author, p.date { display: inline; margin-right: 12px; color: #555; font-size: 9pt; }
h1 { font-size: 13pt; color: #1f6f5c; margin: 14px 0 4px; break-after: avoid; }
h2 { font-size: 11pt; margin: 10px 0 4px; }
p { margin: 4px 0 6px; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 8px; font-size: 8.3pt; break-inside: avoid; }
th, td { border: 1px solid #cfd6dc; padding: 2.5px 5px; text-align: left; vertical-align: top; }
th { background: #eef3f1; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.3pt; background: #f3f5f7; padding: 0 2px; }
pre { background: #f3f5f7; padding: 6px; font-size: 8pt; }
img { max-width: 100%; }
ol, ul { margin: 2px 0 6px 18px; padding: 0; }
"""


def main() -> int:
    if not shutil.which("pandoc"):
        print("pandoc is required")
        return 1
    tmp = Path(tempfile.mkdtemp())
    css = tmp / "r.css"
    css.write_text(CSS)
    html = tmp / "report.html"
    subprocess.run(["pandoc", str(SRC), "-s", "--embed-resources", "--css", str(css), "--metadata", "lang=en",
                    "--resource-path", str(SRC.parent), "-o", str(html)], check=True)
    js = tmp / "pdf.cjs"
    exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else ""
    js.write_text(f"""
const {{ chromium }} = require('playwright');
(async () => {{
  const b = await chromium.launch({json_exe(exe)});
  const p = await b.newPage();
  await p.goto('file://{html}', {{ waitUntil: 'load' }});
  await p.pdf({{ path: '{OUT}', format: 'A4', printBackground: true, displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: '<div style="font-size:7pt;width:100%;text-align:center;color:#777">GigBid R&amp;D report · page <span class="pageNumber"></span> of <span class="totalPages"></span></div>',
    margin: {{ top: '14mm', bottom: '16mm', left: '14mm', right: '14mm' }} }});
  await b.close();
}})();
""")
    env = dict(os.environ)
    subprocess.run(["node", str(js)], check=True, env=env, cwd=ROOT / "apps" / "web")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


def json_exe(exe: str) -> str:
    return "{ executablePath: '" + exe + "' }" if exe else "{}"


if __name__ == "__main__":
    sys.exit(main())
