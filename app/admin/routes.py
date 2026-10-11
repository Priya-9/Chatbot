"""Admin REST API: conversations, human handoff replies, leads, customers, knowledge base.

Open /docs for interactive Swagger UI. Authenticate with POST /admin/login, then send
`Authorization: Bearer <token>`.
"""

import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.security import check_credentials, create_token, require_admin
from app.db import get_db
from app.models import Customer, DocumentChunk, Lead, Message, User
from app.rag.ingest import SUPPORTED_EXTENSIONS, ingest_directory
from app.services.container import get_services
from app.whatsapp.messages import TextOut

router = APIRouter(prefix="/admin", tags=["admin"])
protected = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ---------------------------------------------------------------- schemas

class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    wa_id: str
    name: str | None
    language: str | None
    journey_node: str | None
    handoff: bool
    verified: bool
    last_seen_at: datetime


class MessageOut(BaseModel):
    id: int
    direction: str
    sender: str
    content: str
    created_at: datetime


class ReplyIn(BaseModel):
    text: str


class LeadOut(BaseModel):
    id: int
    name: str
    email: str
    phone: str | None
    interest: str | None
    crm_ref: str | None
    synced: bool
    created_at: datetime


class CustomerIn(BaseModel):
    email: EmailStr
    name: str
    phone: str | None = None
    plan: str = "Free"
    status: str = "active"


class CustomerOut(CustomerIn):
    id: int
    email: str


# ---------------------------------------------------------------- routes

@router.post("/login", response_model=TokenOut)
def login(body: LoginIn):
    if not check_credentials(body.username, body.password):
        raise HTTPException(401, "Invalid credentials")
    return TokenOut(access_token=create_token(body.username))


@protected.get("/stats")
def stats(db: Session = Depends(get_db)):
    count = lambda model: db.scalar(select(func.count()).select_from(model))  # noqa: E731
    return {
        "users": count(User),
        "messages": count(Message),
        "leads": count(Lead),
        "customers": count(Customer),
        "knowledge_chunks": count(DocumentChunk),
        "open_handoffs": db.scalar(select(func.count()).select_from(User).where(User.handoff.is_(True))),
    }


@protected.get("/users", response_model=list[UserOut])
def list_users(handoff: bool | None = None, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    stmt = select(User).order_by(User.last_seen_at.desc()).limit(min(limit, 200)).offset(offset)
    if handoff is not None:
        stmt = stmt.where(User.handoff.is_(handoff))
    auth = get_services().auth
    return [
        UserOut(**{k: getattr(u, k) for k in UserOut.model_fields if k != "verified"}, verified=auth.is_verified(u))
        for u in db.scalars(stmt)
    ]


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return user


@protected.get("/users/{user_id}/messages", response_model=list[MessageOut])
def user_messages(user_id: int, limit: int = 100, db: Session = Depends(get_db)):
    _get_user(db, user_id)
    rows = db.scalars(
        select(Message).where(Message.user_id == user_id).order_by(Message.id.desc()).limit(min(limit, 500))
    )
    return [MessageOut.model_validate(m, from_attributes=True) for m in reversed(list(rows))]


@protected.post("/users/{user_id}/reply")
def agent_reply(user_id: int, body: ReplyIn, request: Request, db: Session = Depends(get_db)):
    """Send a message as a human agent. Free-form messages only work within 24h of the user's last message."""
    user = _get_user(db, user_id)
    request.app.state.sender.send(user.wa_id, TextOut(body.text))
    db.add(Message(user_id=user.id, direction="out", sender="agent", content=body.text))
    return {"status": "sent"}


@protected.post("/users/{user_id}/handoff")
def set_handoff(user_id: int, active: bool, request: Request, db: Session = Depends(get_db)):
    """Take over (active=true) or hand the chat back to the bot (active=false)."""
    user = _get_user(db, user_id)
    user.handoff = active
    if not active:
        services = get_services()
        text = services.translator.t("handoff.ended", user.language)
        request.app.state.sender.send(user.wa_id, TextOut(text))
        db.add(Message(user_id=user.id, direction="out", sender="bot", content=text))
        user.journey_node = services.engine.home
    return {"handoff": user.handoff}


@protected.get("/leads", response_model=list[LeadOut])
def list_leads(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    rows = db.scalars(select(Lead).order_by(Lead.id.desc()).limit(min(limit, 500)).offset(offset))
    return [LeadOut.model_validate(r, from_attributes=True) for r in rows]


@protected.get("/customers", response_model=list[CustomerOut])
def list_customers(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    rows = db.scalars(select(Customer).order_by(Customer.id).limit(min(limit, 500)).offset(offset))
    return [CustomerOut.model_validate(r, from_attributes=True) for r in rows]


@protected.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerIn, db: Session = Depends(get_db)):
    if db.scalar(select(Customer).where(func.lower(Customer.email) == body.email.lower())):
        raise HTTPException(409, "A customer with this email already exists")
    customer = Customer(**body.model_dump())
    db.add(customer)
    db.flush()
    return CustomerOut.model_validate(customer, from_attributes=True)


@protected.get("/knowledge")
def list_knowledge(db: Session = Depends(get_db)):
    rows = db.execute(
        select(DocumentChunk.source, func.count()).group_by(DocumentChunk.source).order_by(DocumentChunk.source)
    ).all()
    return [{"source": source, "chunks": n} for source, n in rows]


@protected.post("/knowledge/upload")
async def upload_knowledge(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a .md/.txt/.pdf into the knowledge directory and re-index."""
    name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file.filename or "upload.txt").name)
    if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    services = get_services()
    target = Path(services.settings.knowledge_dir) / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(await file.read())
    return _reindex(db)


@protected.post("/knowledge/reindex")
def reindex_knowledge(db: Session = Depends(get_db)):
    return _reindex(db)


def _reindex(db: Session) -> dict:
    s = get_services()
    files = ingest_directory(
        db, s.retriever, s.settings.knowledge_dir, s.settings.rag_chunk_size, s.settings.rag_chunk_overlap
    )
    return {"files": files, "total_chunks": sum(files.values())}
