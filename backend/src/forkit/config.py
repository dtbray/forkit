from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    forkit_db_path: str = "/data/forkit.db"
    forkit_image_dir: str = "/data/images"
    forkit_cache_dir: str = "/data/cache"
    forkit_llm_primary: str = "ollama"
    forkit_llm_fallback: str = "none"
    forkit_ollama_url: str = "http://localhost:11434"
    forkit_ollama_model: str = "llama3.1:8b-instruct-q4_K_M"
    forkit_anthropic_api_key: SecretStr = SecretStr("")
    forkit_anthropic_model: str = "claude-sonnet-4-6"
    forkit_llm_timeout_sec: int = 30
    forkit_log_level: str = "INFO"
    # Discovery / Phase 1
    forkit_discovery_search_timeout_sec: int = 5
    forkit_discovery_cache_ttl_min: int = 30
    forkit_google_cse_api_key: str = ""  # empty = google_cse adapter is inert

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
