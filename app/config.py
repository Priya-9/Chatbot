"""Central configuration. Every value can be overridden via environment variables or `.env`."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General -----------------------------------------------------------
    app_name: str = "WhatsApp AI Assistant"
    business_name: str = "Acme Cloud"
    environment: str = "development"  # development | production
    log_level: str = "INFO"

    # --- WhatsApp Business Cloud API ---------------------------------------
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = "change-me-verify-token"
    whatsapp_app_secret: str = ""  # used to verify X-Hub-Signature-256 on webhooks
    whatsapp_api_version: str = "v26.0"
    whatsapp_api_base: str = "https://graph.facebook.com"

    # --- LLM ----------------------------------------------------------------
    llm_provider: str = "claude"  # claude | groq

    # Groq (OpenAI-compatible API, https://console.groq.com)
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_api_base: str = "https://api.groq.com/openai/v1"

    # Claude
    anthropic_api_key: str = ""  # empty -> SDK resolves ANTHROPIC_API_KEY / `ant auth login` profile
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "low"  # low | medium | high | xhigh | max  (low keeps chat replies fast; Groq caps at high)
    llm_max_tokens: int = 4096
    llm_fallbacks: bool = True  # server-side refusal fallback (Claude API only; disable on Bedrock/Vertex)
    llm_history_turns: int = 10  # previous AI exchanges sent as conversation memory
    llm_timeout_seconds: float = 60.0

    # --- RAG ----------------------------------------------------------------
    knowledge_dir: str = "knowledge"
    rag_backend: str = "bm25"  # bm25 (zero-dependency) | chroma (vector embeddings, optional extra)
    rag_top_k: int = 4
    rag_chunk_size: int = 900
    rag_chunk_overlap: int = 150
    chroma_path: str = "data/chroma"
    rag_reindex_on_startup: bool = False  # true -> re-read knowledge_dir on every start (client deployments)

    # --- Database -----------------------------------------------------------
    database_url: str = "sqlite:///./data/app.db"

    # --- CRM ----------------------------------------------------------------
    crm_provider: str = "local"  # local | hubspot | webhook
    hubspot_access_token: str = ""
    crm_webhook_url: str = ""
    crm_webhook_secret: str = ""

    # --- End-user authentication (OTP) --------------------------------------
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    session_ttl_hours: int = 24
    smtp_host: str = ""  # empty -> OTP codes are logged to console (development only)
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@example.com"
    smtp_use_tls: bool = True

    # --- Admin API ----------------------------------------------------------
    admin_username: str = "admin"
    admin_password: str = "change-me"
    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_ttl_minutes: int = 720

    # --- Conversation / i18n -------------------------------------------------
    default_language: str = "en"
    supported_languages: str = "en,es,hi,ar"  # comma-separated; each needs locales/<code>.yaml
    locales_dir: str = "locales"
    journey_file: str = "app/journeys/flows/main.yaml"
    system_prompt_file: str = "prompts/system_prompt.md"  # AI tone and rules; {business} is replaced
    niches_file: str = ""  # sales-demo mode: demo/niches.yaml (see app/demo); empty for client deployments

    @property
    def languages(self) -> list[str]:
        return [code.strip() for code in self.supported_languages.split(",") if code.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
