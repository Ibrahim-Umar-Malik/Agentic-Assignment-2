"""Loaders for PDF/Markdown CVs, Markdown case studies, repo READMEs and code, reviews and past proposals.

Every document carries metadata: persona, type, project, skills, date, client industry and, for proposals,
outcome. `item_id` is the evidence item a host can load in full (portfolio://case/{id}, ...).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".sql", ".ipynb", ".go", ".rb", ".java"}


@dataclass
class Document:
    id: str
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


def _front_matter(text: str) -> tuple[dict, str]:
    if text.startswith("---\n"):
        head, _, body = text[4:].partition("\n---\n")
        try:
            return json.loads(head), body
        except json.JSONDecodeError:
            import yaml

            return yaml.safe_load(head) or {}, body
    return {}, text


def load_pdf(path: Path) -> str:
    from pypdf import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def load_persona(pdir: Path) -> list[Document]:
    pdir = Path(pdir)
    persona = pdir.name
    profile = json.loads((pdir / "profile.json").read_text()) if (pdir / "profile.json").exists() else {}
    docs: list[Document] = []
    for cv in [pdir / "cv.pdf", pdir / "cv.md"]:
        if cv.exists():
            text = load_pdf(cv) if cv.suffix == ".pdf" else cv.read_text()
            docs.append(Document(f"{persona}:cv", text, {"persona": persona, "type": "cv", "item_id": f"{persona}:cv",
                                                         "source": cv.name, "skills": profile.get("skills", []),
                                                         "title": "CV", "project": None}))
            break
    for f in sorted((pdir / "case_studies").glob("*.md")):
        fm, body = _front_matter(f.read_text())
        docs.append(Document(fm.get("id", f"{persona}:case:{f.stem}"), body, {
            "persona": persona, "type": "case_study", "item_id": fm.get("id", f"{persona}:case:{f.stem}"),
            "project": fm.get("project", f.stem), "title": fm.get("title", f.stem), "skills": fm.get("skills", []),
            "date": fm.get("date"), "client_industry": fm.get("client_industry"), "category": fm.get("category"),
            "source": f"case_studies/{f.name}"}))
    for repo in sorted(p for p in (pdir / "repos").glob("*") if p.is_dir()):
        meta = json.loads((repo / "meta.json").read_text()) if (repo / "meta.json").exists() else {}
        base = {"persona": persona, "project": meta.get("project", repo.name), "item_id": meta.get("id", f"{persona}:repo:{repo.name}"),
                "skills": meta.get("skills", []), "date": meta.get("date"), "title": repo.name}
        if (repo / "README.md").exists():
            docs.append(Document(f"{persona}:repo:{repo.name}:readme", (repo / "README.md").read_text(),
                                 {**base, "type": "repo_readme", "source": f"repos/{repo.name}/README.md"}))
        for code in sorted(repo.rglob("*")):
            if code.suffix in CODE_EXT and code.is_file():
                rel = code.relative_to(repo)
                docs.append(Document(f"{persona}:repo:{repo.name}:{rel}", code.read_text(errors="ignore"),
                                     {**base, "type": "repo_code", "source": f"repos/{repo.name}/{rel}"}))
    if (pdir / "reviews.jsonl").exists():
        for line in (pdir / "reviews.jsonl").read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                docs.append(Document(r["id"], r["text"], {"persona": persona, "type": "review", "item_id": r["id"],
                                                          "project": r.get("project"), "date": r.get("date"),
                                                          "client_industry": r.get("client_industry"), "rating": r.get("rating"),
                                                          "source": "reviews.jsonl", "title": f"Review ({r.get('rating')}★)"}))
    if (pdir / "proposals.jsonl").exists():
        for line in (pdir / "proposals.jsonl").read_text().splitlines():
            if line.strip():
                p = json.loads(line)
                docs.append(Document(p["id"], p["text"], {"persona": persona, "type": "proposal", "item_id": p["id"],
                                                          "project": p.get("project"), "date": p.get("date"),
                                                          "outcome": p.get("outcome"), "category": p.get("category"),
                                                          "skills": p.get("skills", []), "source": "proposals.jsonl",
                                                          "title": p.get("job_title")}))
    # user uploads (UI "add work"): plain .md/.txt/.pdf files in uploads/, re-indexed incrementally
    for f in sorted((pdir / "uploads").glob("*")) if (pdir / "uploads").exists() else []:
        if f.suffix in {".md", ".txt", ".pdf"}:
            fm, body = _front_matter(load_pdf(f) if f.suffix == ".pdf" else f.read_text())
            iid = fm.get("id", f"{persona}:upload:{f.stem}")
            docs.append(Document(iid, body, {"persona": persona, "type": fm.get("type", "case_study"), "item_id": iid,
                                             "project": fm.get("project", f.stem), "title": fm.get("title", f.stem),
                                             "skills": fm.get("skills", []), "date": fm.get("date"),
                                             "source": f"uploads/{f.name}"}))
    return docs
