"""Global settings, read from environment / .env. Secrets are never hardcoded.

Every quota number is configurable because Gemini's free-tier limits change:
read the live values from AI Studio and override them in `.env` rather than
editing code.
"""
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve backend/.env by absolute path so the working directory the server was
# launched from cannot change which secrets get loaded.
# This file lives at backend/app/core/, so three levels up is backend/.
_BACKEND_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_ENV_FILE = os.path.join(_BACKEND_DIR, ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    # ---- LLM: Google Gemini -------------------------------------------------
    gemini_api_key: str = ""
    # The free tier offers Flash and Flash-Lite only; Pro models are paid-only,
    # so the pipeline runs on two tiers rather than three.
    #   core — report sections, cross-analysis, audit review (quality-critical)
    #   fast — intake, clarification, expert dispatch, sentiment classification
    gemini_model_core: str = "gemini-3.5-flash"
    gemini_model_fast: str = "gemini-3.5-flash-lite"

    # Free-tier quotas, per model tier. Defaults are conservative; confirm the
    # real numbers for your project at https://aistudio.google.com/rate-limit
    gemini_rpm_core: int = 10
    gemini_rpd_core: int = 1500
    gemini_tpm_core: int = 250_000
    gemini_rpm_fast: int = 15
    gemini_rpd_fast: int = 1000
    gemini_tpm_fast: int = 250_000

    # Ceiling on simultaneously in-flight LLM calls. The pipeline fans out up to
    # 12 concurrent section writes; without this the burst trips 429 instantly.
    gemini_max_concurrency: int = 4

    # Thinking budget in tokens. The research pipeline wants fast, stable output
    # over deep deliberation; 0 disables thinking where the model allows it.
    gemini_thinking_budget: int = 0

    llm_timeout: float = 180.0
    llm_max_retries: int = 3

    # ---- Search -------------------------------------------------------------
    # Ordered failover chain. Each name must match a provider in core/search/.
    search_providers: str = "exa,tavily,ddg"
    exa_api_key: str = ""
    tavily_api_key: str = ""
    search_timeout: float = 30.0

    # ---- Social listening ---------------------------------------------------
    # Reddit: register a "script" app at https://www.reddit.com/prefs/apps
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "vantage/0.1 (competitive intelligence research)"

    # ---- Service ------------------------------------------------------------
    frontend_origin: str = "http://localhost:5173"

    @property
    def llm_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def search_provider_chain(self) -> list[str]:
        """`search_providers` parsed into an ordered, de-duplicated list."""
        seen: set[str] = set()
        chain: list[str] = []
        for raw in self.search_providers.split(","):
            name = raw.strip().lower()
            if name and name not in seen:
                seen.add(name)
                chain.append(name)
        return chain

    @property
    def cors_origins(self) -> list[str]:
        """Allowed browser origins. Comma-separated to support multiple hosts."""
        return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
