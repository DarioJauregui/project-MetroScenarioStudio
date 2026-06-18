from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Runtime settings for the local MVP.

    The platform owns only its local storage. The model repository is a read-only
    source of artefacts and can be overridden through environment variables.
    """

    app_name: str = "Metro Scenario Studio"
    environment: str = "local"
    storage_dir: Path = Field(default=Path("storage"))
    sqlite_path: Path = Field(default=Path("storage") / "metro_scenario_studio.db")
    historical_demand_csv: Path | None = Field(
        default=None,
        description="Optional CSV with historical network demand used to enrich aggregate actuals.",
    )
    data_root: Path = Field(
        default=Path("..") / ".." / "data",
        description="Monorepo data root used for external features and operational datasets.",
    )
    artifacts_dir_name: str = "artifacts"
    metro_demand_models_root: Path = Field(
        default=Path("..") / "ml_pipeline",
        description="Read-only path to the monorepo ml_pipeline package and artifacts.",
    )
    use_mock_inference: bool = Field(
        default=False,
        description="Use deterministic local inference when model artefacts are absent.",
    )
    reasonable_horizon_days: int = 14
    long_range_days: int = 31
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    nlu_endpoint: str = "http://localhost:1234/api/v1/chat"
    nlu_model: str = "mistralai/devstral-small-2507"
    nlu_timeout_seconds: float = 150.0
    nlu_max_tokens: int = 512
    nlu_temperature: float = 0.05
    nlu_send_generation_options: bool = False
    nlu_system_prompt: str | None = None
    explanation_llm_enabled: bool = False
    explanation_llm_endpoint: str = "http://localhost:1234/v1/chat/completions"
    explanation_llm_model: str = "qwen3.6-35b-a3b"
    explanation_llm_timeout_seconds: float = 200.0
    explanation_llm_max_tokens: int = 10000
    explanation_llm_temperature: float = 0.2

    @property
    def artifacts_dir(self) -> Path:
        return self.storage_dir / self.artifacts_dir_name

    def model_post_init(self, __context) -> None:
        if self.historical_demand_csv is None:
            self.historical_demand_csv = self.storage_dir / "demanda_historica_MM.csv"


def platform_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_from_platform_root(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return platform_root() / path


def _default_models_root() -> Path:
    return platform_root().parent / "ml_pipeline"


def _default_data_root() -> Path:
    return platform_root().parent / "data"


def get_settings() -> Settings:
    storage_dir = _resolve_from_platform_root(os.getenv("MSS_STORAGE_DIR", "storage"))
    sqlite_path = Path(os.getenv("MSS_SQLITE_PATH", str(storage_dir / "metro_scenario_studio.db")))
    if not sqlite_path.is_absolute():
        sqlite_path = _resolve_from_platform_root(sqlite_path)
    historical_demand_csv_value = os.getenv("MSS_HISTORICAL_DEMAND_CSV")
    historical_demand_csv = (
        _resolve_from_platform_root(historical_demand_csv_value)
        if historical_demand_csv_value
        else storage_dir / "demanda_historica_MM.csv"
    )
    models_root_value = os.getenv("MSS_METRO_DEMAND_MODELS_ROOT")
    metro_demand_models_root = (
        _resolve_from_platform_root(models_root_value) if models_root_value else _default_models_root()
    )
    data_root_value = os.getenv("MSS_DATA_ROOT")
    data_root = _resolve_from_platform_root(data_root_value) if data_root_value else _default_data_root()
    return Settings(
        app_name=os.getenv("MSS_APP_NAME", "Metro Scenario Studio"),
        environment=os.getenv("MSS_ENVIRONMENT", "local"),
        storage_dir=storage_dir,
        sqlite_path=sqlite_path,
        historical_demand_csv=historical_demand_csv,
        data_root=data_root,
        metro_demand_models_root=metro_demand_models_root,
        use_mock_inference=os.getenv("MSS_USE_MOCK_INFERENCE", "false").lower() in {"1", "true", "yes", "on"},
        nlu_endpoint=os.getenv("MSS_NLU_ENDPOINT", "http://localhost:1234/api/v1/chat"),
        nlu_model=os.getenv("MSS_NLU_MODEL", "mistralai/devstral-small-2507"),
        nlu_timeout_seconds=float(os.getenv("MSS_NLU_TIMEOUT_SECONDS", "150")),
        nlu_max_tokens=int(os.getenv("MSS_NLU_MAX_TOKENS", "512")),
        nlu_temperature=float(os.getenv("MSS_NLU_TEMPERATURE", "0.05")),
        nlu_send_generation_options=os.getenv("MSS_NLU_SEND_GENERATION_OPTIONS", "false").lower()
        in {"1", "true", "yes", "on"},
        nlu_system_prompt=os.getenv("MSS_NLU_SYSTEM_PROMPT") or None,
        explanation_llm_enabled=os.getenv("MSS_EXPLANATION_LLM_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        explanation_llm_endpoint=os.getenv(
            "MSS_EXPLANATION_LLM_ENDPOINT",
            "http://localhost:1234/v1/chat/completions",
        ),
        explanation_llm_model=os.getenv("MSS_EXPLANATION_LLM_MODEL", "qwen3.6-35b-a3b"),
        explanation_llm_timeout_seconds=float(os.getenv("MSS_EXPLANATION_LLM_TIMEOUT_SECONDS", "200")),
        explanation_llm_max_tokens=int(os.getenv("MSS_EXPLANATION_LLM_MAX_TOKENS", "10000")),
        explanation_llm_temperature=float(os.getenv("MSS_EXPLANATION_LLM_TEMPERATURE", "0.2")),
    )
