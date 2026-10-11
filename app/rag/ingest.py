"""Load documents from the knowledge directory, chunk them, store them, and rebuild the retriever index."""

import logging
import re
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import DocumentChunk
from app.rag.retriever import Retriever

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}


def load_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return path.read_text(encoding="utf-8", errors="ignore")


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def split_sections(text: str) -> list[tuple[str, str]]:
    """Split Markdown into (breadcrumb, body) sections, e.g. ("Pricing › Pro plan", "...")."""
    title, heading, buf = "", "", []
    sections: list[tuple[str, str]] = []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            sections.append((" › ".join(filter(None, [title, heading])), body))
        buf.clear()

    for line in text.replace("\r\n", "\n").split("\n"):
        match = _HEADING_RE.match(line)
        if match:
            flush()
            if len(match.group(1)) == 1:
                title, heading = match.group(2), ""
            else:
                heading = match.group(2)
        else:
            buf.append(line)
    flush()
    return sections


def chunk_text(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    """Section-aware chunking. Each chunk is prefixed with its document/section breadcrumb so it is
    self-describing for retrieval and for the LLM; long sections are split with character overlap."""
    chunks: list[str] = []
    for crumb, body in split_sections(text):
        prefix = f"{crumb}\n" if crumb else ""
        chunks += [prefix + part for part in _chunk_paragraphs(body, max(size - len(prefix), 200), overlap)]
    return chunks


def _chunk_paragraphs(text: str, size: int, overlap: int) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        while len(para) > size:  # hard-split very long paragraphs
            head, para = para[:size], para[size - overlap :]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
        if current and len(current) + len(para) + 2 > size:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            # start the overlap on a word boundary
            current = (tail[tail.find(" ") + 1 :] if " " in tail else tail) + "\n\n" + para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


def ingest_directory(db: Session, retriever: Retriever, directory: str | Path,
                     chunk_size: int = 900, overlap: int = 150) -> dict[str, int]:
    """Replace the whole knowledge base with the contents of `directory`. Returns chunk counts per file."""
    directory = Path(directory)
    files = sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS)
    stats: dict[str, int] = {}
    pairs: list[tuple[str, str]] = []

    db.execute(delete(DocumentChunk))
    for path in files:
        source = path.relative_to(directory).as_posix()
        try:
            chunks = chunk_text(load_document(path), chunk_size, overlap)
        except Exception:
            log.exception("Failed to ingest %s", path)
            continue
        for i, text in enumerate(chunks):
            db.add(DocumentChunk(source=source, chunk_index=i, text=text))
            pairs.append((source, text))
        stats[source] = len(chunks)
    db.flush()

    retriever.rebuild(pairs)
    log.info("Ingested %d chunks from %d files", len(pairs), len(stats))
    return stats
