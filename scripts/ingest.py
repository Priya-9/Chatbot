"""Re-index the knowledge base:  python scripts/ingest.py [--dir knowledge]"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import init_db, session_scope  # noqa: E402
from app.rag.ingest import ingest_directory  # noqa: E402
from app.services.container import get_services  # noqa: E402


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=settings.knowledge_dir, help="folder with .md/.txt/.pdf files")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_db()
    services = get_services()
    with session_scope() as db:
        stats = ingest_directory(db, services.retriever, args.dir, settings.rag_chunk_size, settings.rag_chunk_overlap)
    for source, n in stats.items():
        print(f"  {source}: {n} chunks")
    print(f"Done: {sum(stats.values())} chunks from {len(stats)} files.")


if __name__ == "__main__":
    main()
