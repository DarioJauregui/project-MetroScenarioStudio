from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol
from urllib import error, request

from metro_scenario_studio.core.config import Settings, get_settings

if TYPE_CHECKING:
    from metro_scenario_studio.domain.schemas import ExecutionResult

logger = logging.getLogger(__name__)

FALLBACK_SUMMARY = (
    "No se ha podido generar la explicacion narrativa local porque el servicio LLM no esta "
    "disponible o no ha devuelto una respuesta valida. La prediccion sigue registrada con "
    "trazabilidad tecnica: modelo, variante, variables usadas, cambios manuales, avisos y "
    "resultados exportables."
)
THINKING_MARKERS = (
    "Here's a thinking process:",
    "Thinking process:",
    "Final Output Generation:",
)


class ExplanationChatClient(Protocol):
    def chat(self, system_prompt: str, user_payload: str) -> str:
        raise NotImplementedError


@dataclass
class OpenAICompatibleChatClient:
    endpoint: str
    model: str
    timeout_seconds: float
    max_tokens: int
    temperature: float

    def chat(self, system_prompt: str, user_payload: str) -> str:
        model = self._resolve_model_identifier()
        payload = self._build_payload(model, system_prompt, user_payload)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except (error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Prediction explanation LLM request failed: {exc}") from exc

        try:
            response_payload = json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip()

        choices = response_payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return message["content"].strip()
                if isinstance(first.get("text"), str):
                    return first["text"].strip()
        output = response_payload.get("output")
        if isinstance(output, list):
            content_parts = [
                str(item.get("content"))
                for item in output
                if isinstance(item, dict) and isinstance(item.get("content"), str)
            ]
            if content_parts:
                return "\n".join(content_parts).strip()
        for key in ("response", "content", "text"):
            if isinstance(response_payload.get(key), str):
                return str(response_payload[key]).strip()
        return raw.strip()

    def _build_payload(self, model: str, system_prompt: str, user_payload: str) -> dict[str, Any]:
        if "/api/v1/chat" in self.endpoint:
            return {
                "model": model,
                "system_prompt": system_prompt,
                "input": user_payload,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "stream": False,
            }
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }

    def _resolve_model_identifier(self) -> str:
        model_ids = self._loaded_model_ids()
        if not model_ids or self.model in model_ids:
            return self.model
        normalized_requested = _normalize_model_id(self.model)
        for model_id in model_ids:
            if _normalize_model_id(model_id) == normalized_requested:
                return model_id
        preferred = [model_id for model_id in model_ids if "qwen" in model_id.lower()]
        return preferred[0] if preferred else model_ids[0]

    def _loaded_model_ids(self) -> list[str]:
        for models_endpoint in _candidate_models_endpoints(self.endpoint):
            http_request = request.Request(models_endpoint, method="GET")
            try:
                with request.urlopen(http_request, timeout=min(self.timeout_seconds, 10)) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception:
                continue
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, list):
                ids = [str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id")]
                if ids:
                    return ids
            if isinstance(payload, dict) and isinstance(payload.get("models"), list):
                ids = [
                    str(item.get("id") or item.get("model") or item.get("name"))
                    for item in payload["models"]
                    if isinstance(item, dict) and (item.get("id") or item.get("model") or item.get("name"))
                ]
                if ids:
                    return ids
        return []


class PredictionExplanationService:
    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: ExplanationChatClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client or OpenAICompatibleChatClient(
            endpoint=self.settings.explanation_llm_endpoint,
            model=self.settings.explanation_llm_model,
            timeout_seconds=self.settings.explanation_llm_timeout_seconds,
            max_tokens=self.settings.explanation_llm_max_tokens,
            temperature=self.settings.explanation_llm_temperature,
        )

    def summarize(self, result: ExecutionResult) -> str | None:
        if not self.settings.explanation_llm_enabled:
            return None
        try:
            response = self.llm_client.chat(
                build_system_prompt(),
                build_prediction_context(result),
            )
        except Exception as exc:
            logger.warning("Prediction explanation LLM failed: %s", exc)
            return build_deterministic_summary(result, prefix="El resumen LLM local no esta disponible.")
        cleaned = _clean_response(response)
        if not cleaned:
            return build_deterministic_summary(result, prefix="El modelo local no devolvio una respuesta final limpia.")
        return cleaned


def build_system_prompt() -> str:
    return """
Eres un analista funcional de Metro Scenario Studio.
Escribe en espanol claro para un usuario interno no experto.
Resume la prediccion diaria en 2 o 3 parrafos cortos, con tono prudente y util.
Explica que factores parecen impulsar o frenar el resultado segun la informacion disponible, sin afirmar causalidad.
Si el escenario es what-if o derivado, explica que supuestos introducidos se han registrado y si la variante del modelo permite usarlos.
Si no hay comparacion base calculada, no inventes porcentajes ni diferencias.
Menciona limitaciones relevantes: cobertura de datos externos, horizonte, datos reales o avisos.
No uses markdown de tabla ni listas largas.
Tu respuesta final debe empezar por "RESPUESTA_FINAL:" y despues incluir solo el texto visible para el usuario.
""".strip()


def build_prediction_context(result: ExecutionResult) -> str:
    execution = result.execution
    network_total = next(
        (
            aggregate.y_pred
            for aggregate in result.aggregates
            if aggregate.level == "network" and aggregate.target_date is None
        ),
        sum(row.y_pred for row in result.prediction_rows),
    )
    real_total = next(
        (
            aggregate.y_real
            for aggregate in result.aggregates
            if aggregate.level == "network" and aggregate.target_date is None
        ),
        None,
    )
    daily_totals = [
        {
            "date": aggregate.target_date.isoformat() if aggregate.target_date else None,
            "predicted": round(aggregate.y_pred, 2),
            "real": round(aggregate.y_real, 2) if aggregate.y_real is not None else None,
        }
        for aggregate in result.aggregates
        if aggregate.level in {"date", "network_date"} and aggregate.target_date is not None
    ][:20]
    top_stations = sorted(result.prediction_rows, key=lambda row: row.y_pred, reverse=True)[:8]
    used_explanations = [
        {
            "section": item.section,
            "label": item.label,
            "description": item.description,
            "used_by_model": item.used_by_model,
            "limitation": item.limitation,
        }
        for item in result.explanations
    ][:20]
    context: dict[str, Any] = {
        "execution": {
            "id": execution.id,
            "status": execution.status.value,
            "range_start": execution.range_start.isoformat(),
            "range_end": execution.range_end.isoformat(),
            "model_name": execution.model_name,
            "model_variant": execution.model_variant,
            "dataset_version": execution.dataset_version,
            "real_data_status": execution.real_data_status,
            "warnings": execution.warnings,
        },
        "prediction_summary": {
            "network_total_predicted": round(network_total, 2),
            "network_total_real": round(real_total, 2) if real_total is not None else None,
            "daily_totals_sample": daily_totals,
            "top_station_rows": [
                {
                    "date": row.target_date.isoformat(),
                    "line": row.linea,
                    "station": row.estacion,
                    "predicted": round(row.y_pred, 2),
                    "real": round(row.y_real, 2) if row.y_real is not None else None,
                }
                for row in top_stations
            ],
        },
        "scenario_inputs": {
            "natural_language_comment": execution.input.natural_language_comment,
            "manual_overrides": execution.input.manual_overrides,
            "accepted_llm_items": [item.model_dump(mode="json") for item in execution.input.llm_accepted_items],
            "rejected_llm_items": [item.model_dump(mode="json") for item in execution.input.llm_rejected_items],
            "modified_calendar_days": [
                item.model_dump(mode="json") for item in execution.input.calendar_final if item.modified
            ][:20],
            "modified_events": [
                item.model_dump(mode="json")
                for item in execution.input.events_final
                if item.modified or item.source == "manual_scenario"
            ][:20],
            "modified_weather_days": [
                item.model_dump(mode="json")
                for item in execution.input.weather_final
                if item.modified or item.source == "manual_scenario"
            ][:20],
        },
        "traceability_factors": used_explanations,
        "guardrails": [
            "No interpretar what-if como causalidad.",
            "No inventar diferencias contra base si no se proporcionan.",
            "Explicar si una variable solo se registro pero no fue usada por la variante del modelo.",
        ],
    }
    return json.dumps(context, ensure_ascii=False, sort_keys=True)


def build_deterministic_summary(result: ExecutionResult, *, prefix: str | None = None) -> str:
    execution = result.execution
    network_total = next(
        (
            aggregate.y_pred
            for aggregate in result.aggregates
            if aggregate.level == "network" and aggregate.target_date is None
        ),
        sum(row.y_pred for row in result.prediction_rows),
    )
    changed_parts: list[str] = []
    if execution.input.manual_overrides:
        changed_parts.append("cambios manuales")
    if any(item.modified for item in execution.input.events_final):
        changed_parts.append("eventos modificados o anadidos")
    if any(item.modified for item in execution.input.weather_final):
        changed_parts.append("meteorologia de simulacion")
    if any(item.modified for item in execution.input.calendar_final):
        changed_parts.append("calendario editado")
    warnings = ", ".join(execution.warnings[:4]) if execution.warnings else "sin avisos principales"
    scenario_text = (
        f"Es un escenario {execution.status.value} con {', '.join(changed_parts)}."
        if changed_parts
        else f"Es una ejecucion {execution.status.value} sin cambios manuales relevantes."
    )
    prefix_text = f"{prefix} " if prefix else ""
    return (
        f"{prefix_text}La prediccion estima {network_total:,.0f} viajes previstos entre "
        f"{execution.range_start.isoformat()} y {execution.range_end.isoformat()}. {scenario_text} "
        f"Los factores registrados se interpretan como variables asociadas al modelo, no como causalidad directa. "
        f"Limitaciones/avisos: {warnings}."
    )


def _clean_response(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
    extracted_final = _extract_final_response(cleaned)
    if extracted_final:
        return extracted_final
    if any(marker in cleaned for marker in THINKING_MARKERS) or "</think>" in cleaned.lower():
        return ""
    return cleaned


def _candidate_models_endpoints(endpoint: str) -> list[str]:
    if "/v1/chat/completions" in endpoint:
        return [endpoint.split("/v1/chat/completions", 1)[0] + "/v1/models"]
    if "/api/v1/chat" in endpoint:
        base = endpoint.split("/api/v1/chat", 1)[0]
        return [base + "/api/v1/models", base + "/v1/models"]
    return [endpoint.rstrip("/") + "/models"]


def _normalize_model_id(value: str) -> str:
    return value.lower().replace("_", "-").replace("/", "-")


def _extract_final_response(value: str) -> str:
    if "RESPUESTA_FINAL:" not in value:
        return ""
    final = value.rsplit("RESPUESTA_FINAL:", 1)[1].strip()
    if "</think>" in final.lower():
        final = final.split("</think>", 1)[-1].strip()
    lines = [line.rstrip() for line in final.splitlines()]
    useful_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if useful_lines and useful_lines[-1] != "":
                useful_lines.append("")
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            continue
        if stripped.startswith("*(") and stripped.endswith(")*"):
            continue
        useful_lines.append(stripped)
    normalized = "\n".join(useful_lines).strip()
    return normalized
