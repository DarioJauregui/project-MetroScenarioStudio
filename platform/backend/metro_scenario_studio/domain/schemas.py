from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class ScenarioStatus(StrEnum):
    DRAFT = "draft"
    BASE = "base"
    WHAT_IF = "what_if"
    IMPORTADA = "importada"
    DERIVADA = "derivada"
    HISTORICO_EVALUADO = "historico_evaluado"


class OriginType(StrEnum):
    MANUAL = "manual"
    EXCEL_IMPORT = "excel_import"
    DERIVED = "derived"


class EventType(StrEnum):
    SPORTS = "deportivo"
    CULTURAL = "cultural"
    UNIVERSITY = "universitario"
    RELIGIOUS = "religioso"
    CONGRESS = "feria/congreso"
    OTHER = "otro"


class ImpactLevel(StrEnum):
    LOW = "bajo"
    MEDIUM = "medio"
    HIGH = "alto"
    VERY_HIGH = "muy alto"


class CalendarVariable(BaseModel):
    target_date: date
    day_of_week: int
    is_holiday: bool = False
    is_preholiday: bool = False
    is_postholiday: bool = False
    is_bridge: bool = False
    special_day: str | None = None
    source: str = "calendar"
    modified: bool = False
    used_by_model: bool = True


class EventVariable(BaseModel):
    event_id: str
    name: str
    target_date: date
    date_mode: str = "range"
    start_date: date | None = None
    end_date: date | None = None
    selected_dates: list[date] = Field(default_factory=list)
    all_day: bool = True
    start_time: str | None = None
    end_time: str | None = None
    event_type: EventType = EventType.OTHER
    impact_level: ImpactLevel = ImpactLevel.MEDIUM
    affected_stations: list[str] = Field(default_factory=lambda: ["all"])
    comment: str | None = None
    source: str | None = None
    origin_event_id: str | None = None
    deleted: bool = False
    modified: bool = False
    used_by_model: bool = True


class WeatherVariable(BaseModel):
    target_date: date
    rain: bool = False
    heavy_rain: bool = False
    approx_temperature: float | None = None
    hot_day: bool = False
    cold_day: bool = False
    bad_weather: bool = False
    temp_min: float | None = None
    temp_mean: float | None = None
    temp_max: float | None = None
    precip_mm: float | None = None
    rain_hours: float | None = None
    wind: float | None = None
    humidity: float | None = None
    weather_code: str | None = None
    alert_level: str | None = None
    alert_summary: str | None = None
    source: str = "automatic"
    modified: bool = False
    used_by_model: bool = False


class LlmDetectedItem(BaseModel):
    type: str
    name: str | None = None
    impact_level: str | None = None
    affected_stations: list[str] = Field(default_factory=list)
    rain_expected: bool | None = None
    time_window: str | None = None
    confidence: str = "medium"
    payload: dict[str, Any] = Field(default_factory=dict)


class LlmNotUsedItem(BaseModel):
    text: str
    reason: str


class LlmParseResult(BaseModel):
    detected_items: list[LlmDetectedItem] = Field(default_factory=list)
    not_used: list[LlmNotUsedItem] = Field(default_factory=list)
    requires_human_validation: bool = True
    prompt_version: str = "mvp-rule-based-v1"
    raw_response: dict[str, Any] = Field(default_factory=dict)


class ScenarioInput(BaseModel):
    natural_language_comment: str | None = None
    calendar_final: list[CalendarVariable] = Field(default_factory=list)
    events_final: list[EventVariable] = Field(default_factory=list)
    weather_final: list[WeatherVariable] = Field(default_factory=list)
    manual_overrides: list[dict[str, Any]] = Field(default_factory=list)
    llm_detected_items: list[LlmDetectedItem] = Field(default_factory=list)
    llm_accepted_items: list[LlmDetectedItem] = Field(default_factory=list)
    llm_rejected_items: list[LlmDetectedItem] = Field(default_factory=list)


class ScenarioExecution(BaseModel):
    id: str
    status: ScenarioStatus = ScenarioStatus.DRAFT
    real_data_status: str = "datos reales no disponibles"
    origin_type: OriginType = OriginType.MANUAL
    parent_execution_id: str | None = None
    range_start: date
    range_end: date
    author: str | None = None
    comment: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    executed_at: datetime | None = None
    model_name: str = "tabular_hgbr"
    model_variant: str = "strict_available"
    dataset_version: str = "local-readonly"
    warnings: list[str] = Field(default_factory=list)
    input: ScenarioInput = Field(default_factory=ScenarioInput)


class PredictionRow(BaseModel):
    target_date: date
    linea: str
    estacion: str
    series_id: str
    station_abbrev: str
    network_order: int
    y_pred: float
    y_real: float | None = None
    model_variant: str
    horizon_days: int
    forecast_origin_date: date | None = None
    prediction_mode: str = "artifact_prediction"
    model_artifact: str | None = None
    model_artifact_sha256: str | None = None
    feature_row_hash: str | None = None

    @property
    def real_available(self) -> bool:
        return self.y_real is not None


class AggregateRow(BaseModel):
    level: str
    target_date: date | None = None
    linea: str | None = None
    estacion: str | None = None
    y_pred: float
    y_real: float | None = None
    real_available: bool = False
    abs_error: float | None = None
    pct_error: float | None = None
    delta_abs: float | None = None
    delta_pct: float | None = None


class ExplanationItem(BaseModel):
    section: str
    item_type: str
    label: str
    description: str
    source: str
    used_by_model: bool
    confidence: str | None = None
    limitation: str | None = None


class AuditEvent(BaseModel):
    execution_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    action: str
    actor: str | None = None
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)


class CoverageSummary(BaseModel):
    calendar_days: int
    event_days: int
    weather_days: int
    total_days: int


class WarningItem(BaseModel):
    code: str
    message: str
    severity: str = "warning"


class ExternalDataSnapshot(BaseModel):
    range_start: date
    range_end: date
    calendar: list[CalendarVariable] = Field(default_factory=list)
    events: list[EventVariable] = Field(default_factory=list)
    weather: list[WeatherVariable] = Field(default_factory=list)
    coverage: CoverageSummary
    warnings: list[WarningItem] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    execution: ScenarioExecution
    prediction_rows: list[PredictionRow]
    aggregates: list[AggregateRow]
    explanations: list[ExplanationItem]
    narrative_summary: str | None = None
    audit_events: list[AuditEvent] = Field(default_factory=list)


class CreateScenarioRequest(BaseModel):
    range_start: date
    range_end: date
    author: str | None = None
    comment: str | None = None
    natural_language_comment: str | None = None
    calendar_final: list[CalendarVariable] = Field(default_factory=list)
    events_final: list[EventVariable] = Field(default_factory=list)
    weather_final: list[WeatherVariable] = Field(default_factory=list)
    manual_overrides: list[dict[str, Any]] = Field(default_factory=list)
    llm_detected_items: list[LlmDetectedItem] = Field(default_factory=list)
    llm_accepted_items: list[LlmDetectedItem] = Field(default_factory=list)
    llm_rejected_items: list[LlmDetectedItem] = Field(default_factory=list)


class UpdateScenarioRequest(BaseModel):
    range_start: date | None = None
    range_end: date | None = None
    author: str | None = None
    comment: str | None = None
    natural_language_comment: str | None = None
    calendar_final: list[CalendarVariable] | None = None
    events_final: list[EventVariable] | None = None
    weather_final: list[WeatherVariable] | None = None
    manual_overrides: list[dict[str, Any]] | None = None
    llm_detected_items: list[LlmDetectedItem] | None = None
    llm_accepted_items: list[LlmDetectedItem] | None = None
    llm_rejected_items: list[LlmDetectedItem] | None = None


class DeriveScenarioRequest(BaseModel):
    comment: str | None = None


class ImportExcelRequest(BaseModel):
    path: str


class NlpParseRequest(BaseModel):
    comment: str
    range_start: date
    range_end: date
