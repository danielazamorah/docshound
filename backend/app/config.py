from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"

    github_token: str | None = None

    merge_gateway_api_key: str | None = None
    merge_gateway_base_url: str = "https://api-gateway.merge.dev/v1/openai"
    merge_gateway_primary_model: str = "google/gemini-3.7-flash"
    merge_gateway_fallback_model: str = "openai/gpt-5.6-luna"

    # Google 1P Gemini through Vertex AI's OpenAI-compatible endpoint. When
    # vertex_project is set it takes priority over the Merge Gateway. Auth uses
    # Application Default Credentials (user creds locally, the runtime service
    # account on Agent Engine / Cloud Run) so no API keys are stored.
    vertex_project: str | None = None
    vertex_location: str = "global"
    vertex_primary_model: str = "google/gemini-3.7-flash"
    vertex_fallback_model: str = "google/gemini-3.5-flash"

    # Backwards compatibility for installations that call OpenAI directly.
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    docshound_db_path: str | None = None
    docshound_demo_scenario: str | None = None

    allowed_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8080,http://127.0.0.1:8080"
    )

    @property
    def allowed_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
