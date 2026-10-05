"""Global settings, read from environment / backend/.env."""
import os
from functools import lru_cache
from typing import Literal

from pydantic import Field
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

    # core/aux: writing, analysis, review; fast: planning, dispatch, sentiment.
    llm_provider: Literal["mock", "qwen", "openai"] = "mock"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model_core: str = "gpt-4.1-mini"
    openai_model_fast: str = "gpt-4.1-mini"
    qwen_api_key: str = ""
    dashscope_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model_core: str = "qwen-plus"
    qwen_model_fast: str = "qwen-plus"

    # Local budgets, not provider-reported quota. 0 disables the cap.
    llm_rpm_core: int = Field(default=0, ge=0)
    llm_rpd_core: int = Field(default=0, ge=0)
    llm_tpm_core: int = Field(default=0, ge=0)
    llm_rpm_fast: int = Field(default=0, ge=0)
    llm_rpd_fast: int = Field(default=0, ge=0)
    llm_tpm_fast: int = Field(default=0, ge=0)
    llm_max_concurrency: int = Field(default=4, ge=1)
    llm_timeout: float = Field(default=180.0, gt=0)
    llm_max_retries: int = Field(default=3, ge=0)

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
        return self.is_mock or bool(self.llm_api_key.strip())

    @property
    def is_mock(self) -> bool:
        return self.llm_provider == "mock"

    @property
    def llm_api_key(self) -> str:
        if self.llm_provider == "qwen":
            return self.qwen_api_key.strip() or self.dashscope_api_key.strip()
        return self.openai_api_key.strip() if self.llm_provider == "openai" else ""

    @property
    def llm_base_url(self) -> str:
        return self.qwen_base_url if self.llm_provider == "qwen" else self.openai_base_url

    @property
    def llm_model_core(self) -> str:
        return "mock-core" if self.is_mock else getattr(self, f"{self.llm_provider}_model_core")

    @property
    def llm_model_fast(self) -> str:
        return "mock-fast" if self.is_mock else getattr(self, f"{self.llm_provider}_model_fast")

    @property
    def llm_configuration_error(self) -> str:
        key = "QWEN_API_KEY (or DASHSCOPE_API_KEY)" if self.llm_provider == "qwen" else "OPENAI_API_KEY"
        return f"{key} is not set for LLM_PROVIDER={self.llm_provider}. Configure backend/.env."

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
