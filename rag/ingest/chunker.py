"""Chunkers: fixed word windows (V0 baseline) and structure-aware chunks (sections, code, one record per review)."""

from __future__ import annotations

import re

from ..types import Chunk
from .loaders import Document


def fixed_chunks(doc: Document, size: int = 120, overlap: int = 20) -> list[Chunk]:
    words = doc.text.split()
    out = []
    step = max(1, size - overlap)
    for i in range(0, max(1, len(words)), step):
        piece = " ".join(words[i: i + size])
        if piece.strip():
            out.append(Chunk(f"{doc.id}#f{i}", piece, doc.id, dict(doc.meta)))
        if i + size >= len(words):
            break
    return out


def structured_chunks(doc: Document, max_words: int = 180) -> list[Chunk]:
    t = doc.meta.get("type")
    if t in ("review", "proposal") or len(doc.text.split()) <= max_words:
        return [Chunk(f"{doc.id}#s0", doc.text.strip(), doc.id, dict(doc.meta))]
    if t == "repo_code":
        parts = re.split(r"\n(?=(?:def |class |async def |export |function |@app\.task|--\s))", doc.text)
    else:
        parts = re.split(r"\n(?=#{1,3} )", doc.text)
    chunks, buf = [], ""
    for p in parts:
        if buf and len((buf + p).split()) > max_words:
            chunks.append(buf)
            buf = p
        else:
            buf = (buf + "\n" + p) if buf else p
    if buf.strip():
        chunks.append(buf)
    title = doc.meta.get("title") or ""
    return [Chunk(f"{doc.id}#s{i}", (f"{title}\n" if i and title else "") + c.strip(), doc.id, dict(doc.meta))
            for i, c in enumerate(chunks)]


def context_line(doc_meta: dict) -> str:
    """V6-style contextual prefix: a short line situating the chunk (deterministic, no LLM needed)."""
    bits = [doc_meta.get("type", "item").replace("_", " ")]
    if doc_meta.get("title"):
        bits.append(f"'{doc_meta['title']}'")
    if doc_meta.get("client_industry"):
        bits.append(f"for a {doc_meta['client_industry']} client")
    if doc_meta.get("skills"):
        bits.append("using " + ", ".join(doc_meta["skills"][:6]))
    if doc_meta.get("outcome"):
        bits.append(f"(outcome: {doc_meta['outcome']})")
    return "[" + " ".join(bits) + "]"
