"""FastAPI application entry point:  uvicorn app.main:app --reload"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import func, select

from app.admin.routes import protected as admin_protected
from app.admin.routes import router as admin_router
from app.config import get_settings
from app.db import init_db, session_scope
from app.models import Customer, DocumentChunk
from app.rag.ingest import ingest_directory
from app.services.container import get_services
from app.whatsapp.client import ConsoleSender, WhatsAppClient
from app.whatsapp.webhook import router as whatsapp_router

log = logging.getLogger(__name__)

DEMO_CUSTOMERS = [
    {"email": "jane@example.com", "name": "Jane Doe", "plan": "Pro", "status": "active"},
    {"email": "raj@example.com", "name": "Raj Patel", "plan": "Business", "status": "active"},
]


def bootstrap() -> None:
    """Create tables, seed demo data in development, and index the knowledge base on first run
    (or on every start with RAG_REINDEX_ON_STARTUP, so a client's edited files apply on restart)."""
    settings = get_settings()
    services = get_services()
    init_db()
    with session_scope() as db:
        if not settings.is_production and not db.scalar(select(func.count()).select_from(Customer)):
            db.add_all(Customer(**c) for c in DEMO_CUSTOMERS)
            log.info("Seeded %d demo customers", len(DEMO_CUSTOMERS))
        if settings.rag_reindex_on_startup or not db.scalar(select(func.count()).select_from(DocumentChunk)):
            ingest_directory(db, services.retriever, settings.knowledge_dir,
                             settings.rag_chunk_size, settings.rag_chunk_overlap)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if settings.is_production:
        insecure = [k for k in ("admin_password", "jwt_secret", "whatsapp_verify_token")
                    if getattr(settings, k).startswith("change-me")]
        if insecure:
            raise RuntimeError(f"Set secure values for: {', '.join(insecure)}")
    bootstrap()
    if settings.whatsapp_token and settings.whatsapp_phone_number_id:
        app.state.sender = WhatsAppClient(settings)
    else:
        log.warning("WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID not set - replies are printed to the console")
        app.state.sender = ConsoleSender()
    yield


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
app.include_router(whatsapp_router)
app.include_router(admin_router)
app.include_router(admin_protected)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}
