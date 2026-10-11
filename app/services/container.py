"""Wires all services together once. Tests and scripts can swap pieces via `set_services()`."""

from dataclasses import dataclass

from app.auth.otp import AuthService
from app.config import Settings, get_settings
from app.crm.providers import CRMProvider, build_crm
from app.i18n.translator import Translator
from app.journeys.actions import ACTIONS
from app.journeys.engine import JourneyEngine
from app.llm.assistant import AIAssistant
from app.llm.claude import LLM, ClaudeLLM
from app.llm.groq import GroqLLM
from app.rag.retriever import BM25Retriever, ChromaRetriever, Retriever


@dataclass
class Services:
    settings: Settings
    translator: Translator
    engine: JourneyEngine
    retriever: Retriever
    crm: CRMProvider
    auth: AuthService
    ai: AIAssistant


def build_llm(settings: Settings) -> LLM:
    provider = settings.llm_provider.lower()
    if provider == "groq":
        return GroqLLM(settings)
    if provider == "claude":
        return ClaudeLLM(settings)
    raise ValueError(f"Unknown LLM_PROVIDER {settings.llm_provider!r} (expected claude or groq)")


def build_services(settings: Settings | None = None, *, llm: LLM | None = None,
                   crm: CRMProvider | None = None, otp_delivery=None) -> Services:
    settings = settings or get_settings()
    translator = Translator(settings.locales_dir, settings.languages, settings.default_language)
    retriever: Retriever = (
        ChromaRetriever(settings.chroma_path) if settings.rag_backend == "chroma" else BM25Retriever()
    )
    crm = crm or build_crm(settings)
    return Services(
        settings=settings,
        translator=translator,
        engine=JourneyEngine.from_yaml(settings.journey_file, ACTIONS),
        retriever=retriever,
        crm=crm,
        auth=AuthService(settings, crm, deliver=otp_delivery),
        ai=AIAssistant(llm or build_llm(settings), retriever, translator, settings),
    )


_services: Services | None = None


def get_services() -> Services:
    global _services
    if _services is None:
        _services = build_services()
    return _services


def set_services(services: Services | None) -> None:
    global _services
    _services = services
