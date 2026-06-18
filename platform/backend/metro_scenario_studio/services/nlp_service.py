from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol
from urllib import error, request

from metro_scenario_studio.core.config import Settings, get_settings
from metro_scenario_studio.domain.schemas import (
    LlmDetectedItem,
    LlmNotUsedItem,
    LlmParseResult,
)

logger = logging.getLogger(__name__)

EVENT_TYPES = {"deportivo", "cultural", "universitario", "religioso", "feria/congreso", "otro"}
IMPACT_LEVELS = {"bajo", "medio", "alto", "muy alto"}
ALERT_LEVELS = {"sin_alerta", "amarilla", "naranja", "roja"}
DOMAINS = {"eventos", "meteorologia", "calendario"}
INTENTS = {"crear_evento", "modificar_evento", "eliminar_evento", "modificar_meteorologia", "marcar_festivo"}
MISSING_DATE_MESSAGE = "Debes indicar el día o rango de días al que quieres aplicar el cambio o cambios."


class LlmChatClient(Protocol):
    def chat(self, system_prompt: str, input_text: str) -> str:
        raise NotImplementedError


@dataclass
class LocalLlmChatClient:
    endpoint: str
    model: str
    timeout_seconds: float
    max_tokens: int = 512
    temperature: float = 0.0
    send_generation_options: bool = False

    def chat(self, system_prompt: str, input_text: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "system_prompt": system_prompt,
            "input": f"/no_think\n{input_text}",
        }
        if self.send_generation_options:
            payload.update(
                {
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "stream": False,
                    "enable_thinking": False,
                }
            )
        body = json.dumps(payload).encode("utf-8")
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
            raise RuntimeError(f"NLU LLM request failed: {exc}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return raw

        output = payload.get("output")
        if isinstance(output, list):
            content_parts = [
                str(item.get("content"))
                for item in output
                if isinstance(item, dict) and isinstance(item.get("content"), str)
            ]
            if content_parts:
                return "\n".join(content_parts)
        for key in ("response", "content", "text"):
            if isinstance(payload.get(key), str):
                return str(payload[key])
        message = payload.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return str(message["content"])
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                content = first.get("message", {}).get("content") if isinstance(first.get("message"), dict) else None
                return str(content or first.get("text") or raw)
        return raw


def parse_last_json_object(text: str) -> dict[str, Any]:
    last_close = text.rfind("}")
    if last_close < 0:
        raise ValueError("No JSON object terminator found.")
    for start in range(last_close, -1, -1):
        if text[start] != "{":
            continue
        candidate = text[start : last_close + 1]
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("No valid JSON object found.")


class NaturalLanguageService:
    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: LlmChatClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client or LocalLlmChatClient(
            endpoint=self.settings.nlu_endpoint,
            model=self.settings.nlu_model,
            timeout_seconds=self.settings.nlu_timeout_seconds,
            max_tokens=self.settings.nlu_max_tokens,
            temperature=self.settings.nlu_temperature,
            send_generation_options=self.settings.nlu_send_generation_options,
        )
        self.system_prompt = self.settings.nlu_system_prompt or build_system_prompt()

    def parse(
        self,
        comment: str,
        reference_date: date | None = None,
        stations: list[dict[str, Any]] | None = None,
        require_explicit_temporal_hint: bool = False,
    ) -> LlmParseResult:
        text = comment.strip()
        reference = reference_date or date.today()
        if require_explicit_temporal_hint and not has_temporal_hint(text):
            return LlmParseResult(
                detected_items=[],
                not_used=[
                    LlmNotUsedItem(
                        text=MISSING_DATE_MESSAGE,
                        reason="missing_date",
                    )
                ],
                requires_human_validation=True,
                prompt_version="nlu-frames-v1",
                raw_response={"reason": "missing_temporal_hint"},
            )
        catalog = {
            "event_types": sorted(EVENT_TYPES),
            "impact_levels": sorted(IMPACT_LEVELS),
            "alert_levels": sorted(ALERT_LEVELS),
            "stations": compact_station_catalog(stations or []),
        }
        prompt_input = json.dumps(
            {
                "user_text": text,
                "reference_date": reference.isoformat(),
                "catalogs": catalog,
            },
            ensure_ascii=False,
        )
        logger.info("NLU prompt sent: %s", prompt_input)

        try:
            raw_response = self.llm_client.chat(self.system_prompt, prompt_input)
            logger.info("NLU raw response: %s", raw_response)
            try:
                frame = parse_last_json_object(raw_response)
            except ValueError as exc:
                retry_input = json.dumps(
                    {
                        "previous_error": str(exc),
                        "previous_response": raw_response,
                        "instruction": "Devuelve solo un objeto JSON valido sin texto adicional.",
                        "original_request": prompt_input,
                    },
                    ensure_ascii=False,
                )
                raw_response = self.llm_client.chat(self.system_prompt, retry_input)
                logger.info("NLU retry raw response: %s", raw_response)
                frame = parse_last_json_object(raw_response)
        except Exception as exc:
            logger.warning("NLU LLM failed; using conservative local parser: %s", exc)
            frame = conservative_local_frame(text, reference)
            raw_response = json.dumps(frame, ensure_ascii=False)

        logger.info("NLU parsed JSON: %s", frame)
        result = validate_frame(frame, text, catalog)
        logger.info(
            "NLU validation result: detected=%s not_used=%s",
            [item.model_dump() for item in result.detected_items],
            [item.model_dump() for item in result.not_used],
        )
        return result


def legacy_build_system_prompt() -> str:
    return """
Eres un modulo NLU para un wizard de escenarios de Metro de Malaga.
Devuelve solo JSON valido con este frame:
{
  "domain": "eventos|meteorologia|calendario",
  "intent": "crear_evento|modificar_evento|eliminar_evento|modificar_meteorologia|marcar_festivo",
  "date_range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"} | null,
  "slots": {},
  "mentioned_fields": [],
  "missing_required_slots": [],
  "validation_errors": [],
  "warnings": []
}
Reglas:
- La fecha o rango temporal es obligatorio. Resuelve fechas relativas usando reference_date.
- Si hay varios cambios, devuelve {"frames":[...]} con un frame por cambio.
- Incluye en slots solo campos mencionados explicitamente o decididos por el LLM a partir de caracteristicas del usuario.
- No inventes estaciones, tipo, impacto, alerta ni codigo meteo.
- Si un valor no esta en catalogos, copialo en validation_errors y no lo sustituyas.
- Usa affected_stations:["all"] solo si el usuario dice todas las estaciones/red completa.
- Si el usuario describe un evento pero no da nombre, no inventes titulo; omite name.
- Si el usuario indica festivo, usa domain calendario, intent marcar_festivo y slots {"is_holiday": true}.
- Expresiones como "dia de inicio del rango" se resuelven con reference_date.
Few-shots:
Usuario: Crear evento deportivo el 12/04/2026 con impacto medio en todas las estaciones
JSON: {"domain":"eventos","intent":"crear_evento","date_range":{"start":"2026-04-12","end":"2026-04-12"},"slots":{"event_type":"deportivo","impact_level":"medio","affected_stations":["all"]},"mentioned_fields":["event_type","impact_level","affected_stations"],"missing_required_slots":[],"validation_errors":[],"warnings":[]}
Usuario: Mañana pon lluvia intensa, 20 mm y alerta naranja
JSON: {"domain":"meteorologia","intent":"modificar_meteorologia","date_range":{"start":"<reference_date+1>","end":"<reference_date+1>"},"slots":{"rain":true,"heavy_rain":true,"precip_mm":20,"alert_level":"naranja"},"mentioned_fields":["rain","heavy_rain","precip_mm","alert_level"],"missing_required_slots":[],"validation_errors":[],"warnings":[]}
Usuario: Los 3 primeros días del rango seleccionado hay un evento que afecta mayormente a ciudad de la justicia, es una feria allí y el 10/03 es festivo
JSON: {"frames":["domain":"eventos","intent":"crear_evento","date_range":{"start":"<reference_date>","end":"<reference_date+3>"},"slots":{"name":"Feria en Ciudad de la Justicia","affected_stations":["CDJ"]},"mentioned_fields":["name","affected_stations"],"missing_required_slots":[],"validation_errors":[],"warnings":[], "domain":"calendario","intent":"marcar_festivo","date_range":{"start":"2026-03-10","end":"2026-03-10"},"slots":{"is_holiday":true},"mentioned_fields":["is_holiday"],"missing_required_slots":[],"validation_errors":[],"warnings":[]]}
Usuario: Partido del Málaga con lluvia mañana afectando a Guadalmedina
JSON: {"frames":["domain":"eventos","intent":"crear_evento","date_range":{"start":"<reference_date+1>","end":"<reference_date+1>"},"slots":{"name":"Partido del Málaga","affected_stations":["GDL1", "GDL2"]},"mentioned_fields":["name","affected_stations"],"missing_required_slots":[],"validation_errors":[],"warnings":[], "domain":"meteorologia","intent":"modificar_meteorologia","date_range":{"start":"<reference_date+1>","end":"<reference_date+1>"},"slots":{"rain":true},"mentioned_fields":["rain"],"missing_required_slots":[],"validation_errors":[],"warnings":[]]}
""".strip()


def compact_station_catalog(stations: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "id": str(station.get("series_id", "")),
            "label": str(station.get("estacion", "")),
            "abbr": str(station.get("station_abbrev", "")),
        }
        for station in stations
        if isinstance(station, dict)
    ]


def build_system_prompt() -> str:
    return """
Eres un extractor NLU para un wizard de escenarios de Metro de Malaga.
Responde solo JSON valido, sin markdown, sin explicaciones y sin razonamiento.
Devuelve siempre {"frames":[frame,...]}, incluso si solo hay un cambio.
Frame: {"domain":"eventos|meteorologia|calendario","intent":"crear_evento|modificar_evento|eliminar_evento|modificar_meteorologia|marcar_festivo","date_range":{"start":"YYYY-MM-DD","end":"YYYY-MM-DD"},"slots":{},"mentioned_fields":[],"missing_required_slots":[],"validation_errors":[],"warnings":[]}
Reglas: fecha/rango obligatorio; resuelve fechas con reference_date; usa solo catalogos recibidos; si no hay fecha segura, usa date_range {"start":"","end":""} y missing_required_slots ["date_range"]; si se menciona un nombre o descripcion descriptiva del evento (ej: "Concierto de Alejandro Sanz", "Feria de Malaga"), extraelo en slots["name"]. Si no tiene nombre claro, omite el slot "name"; festivo => calendario/marcar_festivo/is_holiday true.
JSON: {"frames":[{"domain":"eventos","intent":"crear_evento","date_range":{"start":"2026-04-12","end":"2026-04-12"},"slots":{"name":"Concierto de Alejandro Sanz","event_type":"deportivo","impact_level":"medio","affected_stations":["all"]},"mentioned_fields":["name","event_type","impact_level","affected_stations"],"missing_required_slots":[],"validation_errors":[],"warnings":[]}]}
JSON: {"frames":[{"domain":"meteorologia","intent":"modificar_meteorologia","date_range":{"start":"2026-04-13","end":"2026-04-13"},"slots":{"rain":true,"heavy_rain":true,"precip_mm":20,"alert_level":"naranja"},"mentioned_fields":["rain","heavy_rain","precip_mm","alert_level"],"missing_required_slots":[],"validation_errors":[],"warnings":[]}]}
JSON: {"frames":[{"domain":"eventos","intent":"crear_evento","date_range":{"start":"2026-03-10","end":"2026-03-12"},"slots":{"name":"Feria internacional","event_type":"feria/congreso","affected_stations":["CDJ"]},"mentioned_fields":["name","event_type","affected_stations"],"missing_required_slots":[],"validation_errors":[],"warnings":[]},{"domain":"calendario","intent":"marcar_festivo","date_range":{"start":"2026-03-10","end":"2026-03-10"},"slots":{"is_holiday":true},"mentioned_fields":["is_holiday"],"missing_required_slots":[],"validation_errors":[],"warnings":[]}]}
JSON: {"frames":[{"domain":"eventos","intent":"crear_evento","date_range":{"start":"2026-04-13","end":"2026-04-13"},"slots":{"name":"Partido de futbol","event_type":"deportivo","affected_stations":["Guadalmedina"]},"mentioned_fields":["name","event_type","affected_stations"],"missing_required_slots":[],"validation_errors":[],"warnings":[]},{"domain":"meteorologia","intent":"modificar_meteorologia","date_range":{"start":"2026-04-13","end":"2026-04-13"},"slots":{"rain":true},"mentioned_fields":["rain"],"missing_required_slots":[],"validation_errors":[],"warnings":[]}]}
""".strip()


def validate_frame(frame: dict[str, Any], source_text: str, catalog: dict[str, Any]) -> LlmParseResult:
    frames = frame.get("frames") if isinstance(frame.get("frames"), list) else [frame]
    detected: list[LlmDetectedItem] = []
    not_used: list[LlmNotUsedItem] = []
    normalized_frames: list[dict[str, Any]] = []
    for candidate in frames:
        if not isinstance(candidate, dict):
            not_used.append(LlmNotUsedItem(text=str(candidate), reason="invalid_frame"))
            continue
        item, rejected, normalized = validate_single_frame(candidate, source_text, catalog)
        normalized_frames.append(normalized)
        if item:
            detected.append(item)
        if rejected:
            not_used.append(rejected)
    return LlmParseResult(
        detected_items=detected,
        not_used=not_used,
        requires_human_validation=True,
        prompt_version="nlu-frames-v1",
        raw_response={"nlu_frames": normalized_frames},
    )


def validate_single_frame(
    frame: dict[str, Any],
    source_text: str,
    catalog: dict[str, Any],
) -> tuple[LlmDetectedItem | None, LlmNotUsedItem | None, dict[str, Any]]:
    missing_slots = set(str(item) for item in frame.get("missing_required_slots", []))
    date_range = frame.get("date_range")
    if "date_range" in missing_slots or not valid_date_range(date_range):
        return None, LlmNotUsedItem(text=MISSING_DATE_MESSAGE, reason="missing_date"), frame

    domain = str(frame.get("domain", ""))
    intent = str(frame.get("intent", ""))
    slots = frame.get("slots") if isinstance(frame.get("slots"), dict) else {}
    mentioned_fields = [str(item) for item in frame.get("mentioned_fields", [])]
    slots = normalize_slot_values(slots, catalog)
    frame = {**frame, "slots": slots}
    invalid_values = validate_catalog_values(domain, slots, catalog)
    if domain not in DOMAINS:
        invalid_values.append(f"domain={domain}")
    if intent not in INTENTS:
        invalid_values.append(f"intent={intent}")
    if invalid_values:
        return None, LlmNotUsedItem(text=", ".join(invalid_values), reason="invalid_catalog_value"), frame

    detected_type = {"eventos": "event", "meteorologia": "weather", "calendario": "calendar"}[domain]
    payload = {
        "domain": domain,
        "intent": intent,
        "date_range": date_range,
        "slots": {key: value for key, value in slots.items() if key in mentioned_fields},
        "mentioned_fields": mentioned_fields,
        "validation_errors": frame.get("validation_errors", []),
        "warnings": frame.get("warnings", []),
    }
    return (
        LlmDetectedItem(
            type=detected_type,
            name=item_name_from_slots(detected_type, slots),
            impact_level=slots.get("impact_level") if isinstance(slots.get("impact_level"), str) else None,
            affected_stations=slots.get("affected_stations")
            if isinstance(slots.get("affected_stations"), list)
            else [],
            rain_expected=slots.get("rain") if isinstance(slots.get("rain"), bool) else None,
            confidence="medium",
            payload=payload,
        ),
        None,
        frame,
    )


def normalize_slot_values(slots: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    normalized = {**slots}
    if "affected_stations" in normalized and isinstance(normalized["affected_stations"], list):
        station_ids: list[str] = []
        for station in normalized["affected_stations"]:
            station_ids.extend(normalize_station_value(str(station), catalog))
        normalized["affected_stations"] = list(dict.fromkeys(station_ids))
    return normalized


def normalize_station_value(value: str, catalog: dict[str, Any]) -> list[str]:
    if value == "all":
        return [value]
    normalized_value = normalize_text(value)
    matched_by_label: list[str] = []
    for station in catalog.get("stations", []):
        if not isinstance(station, dict):
            continue
        series_id = str(station.get("series_id") or station.get("id") or "")
        label = str(station.get("estacion") or station.get("label") or "")
        abbr = str(station.get("station_abbrev") or station.get("abbr") or "")
        if normalized_value in {normalize_text(series_id), normalize_text(abbr)}:
            return [series_id]
        if normalized_value == normalize_text(label):
            matched_by_label.append(series_id)
    return matched_by_label or [value]


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(character for character in decomposed if not unicodedata.combining(character))
    return without_accents.strip().lower()


def valid_date_range(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        start = date.fromisoformat(str(value.get("start", "")))
        end = date.fromisoformat(str(value.get("end", "")))
    except ValueError:
        return False
    return end >= start


def validate_catalog_values(domain: str, slots: dict[str, Any], catalog: dict[str, Any]) -> list[str]:
    invalid: list[str] = []
    if "event_type" in slots and slots["event_type"] not in EVENT_TYPES:
        invalid.append(f"event_type={slots['event_type']}")
    if "impact_level" in slots and slots["impact_level"] not in IMPACT_LEVELS:
        invalid.append(f"impact_level={slots['impact_level']}")
    if "alert_level" in slots and slots["alert_level"] not in ALERT_LEVELS:
        invalid.append(f"alert_level={slots['alert_level']}")
    if "affected_stations" in slots:
        station_ids = {"all"} | {
            str(item.get("series_id") or item.get("id"))
            for item in catalog.get("stations", [])
            if isinstance(item, dict)
        }
        for station in slots["affected_stations"] if isinstance(slots["affected_stations"], list) else []:
            if str(station) not in station_ids:
                invalid.append(f"affected_stations={station}")
    return invalid


def item_name_from_slots(detected_type: str, slots: dict[str, Any]) -> str:
    if detected_type == "weather":
        return "Cambio meteorologico"
    if detected_type == "calendar":
        return "Cambio de calendario"
    if isinstance(slots.get("name"), str) and str(slots["name"]).strip():
        return str(slots["name"]).strip()
    return "Evento sin nombre"


def conservative_local_frame(text: str, reference: date) -> dict[str, Any]:
    normalized = text.lower()
    date_range = infer_date_range(normalized, reference)
    if not date_range:
        return {
            "domain": "eventos" if "evento" in normalized else "meteorologia",
            "intent": "crear_evento" if "evento" in normalized else "modificar_meteorologia",
            "date_range": None,
            "slots": {},
            "mentioned_fields": [],
            "missing_required_slots": ["date_range"],
            "validation_errors": [],
            "warnings": ["local_fallback_used"],
        }
    slots: dict[str, Any] = {}
    mentioned: list[str] = []
    domain = "meteorologia" if any(word in normalized for word in ("lluvia", "alerta", "mm", "meteo")) else "eventos"
    intent = "modificar_meteorologia" if domain == "meteorologia" else "crear_evento"
    if domain == "eventos":
        name_candidate = text.strip()
        while True:
            prev_len = len(name_candidate)
            name_candidate = re.sub(
                r"^(añade|añadir|crea|crear|inserta|insertar|programa|programar|registra|registrar)\b",
                "",
                name_candidate,
                flags=re.IGNORECASE,
            ).strip()
            name_candidate = re.sub(
                r"^(el|un|una|los|las|de|del|evento de|evento|eventos)\b",
                "",
                name_candidate,
                flags=re.IGNORECASE,
            ).strip()
            if len(name_candidate) == prev_len:
                break
        name_candidate = re.sub(
            r"\b(para\s+)?(hoy|mañana|manana|pasado\s+mañana|pasado\s+manana)\b",
            "",
            name_candidate,
            flags=re.IGNORECASE,
        ).strip()
        name_candidate = re.sub(r"\b(el\s+)?\d{1,2}/\d{1,2}/\d{4}\b", "", name_candidate, flags=re.IGNORECASE).strip()
        name_candidate = re.sub(
            r"\b(con\s+)?impacto\s+(bajo|medio|alto|muy\s+alto)\b", "", name_candidate, flags=re.IGNORECASE
        ).strip()
        name_candidate = re.sub(
            r"\b(de\s+)?tipo\s+(deportivo|cultural|universitario|religioso|feria/congreso|feria|congreso|otro)\b",
            "",
            name_candidate,
            flags=re.IGNORECASE,
        ).strip()
        name_candidate = re.sub(r"\s+", " ", name_candidate).strip()
        if name_candidate:
            slots["name"] = name_candidate[0].upper() + name_candidate[1:]
            mentioned.append("name")
    for event_type in EVENT_TYPES:
        if event_type in normalized or (event_type == "deportivo" and "deportiv" in normalized):
            slots["event_type"] = event_type
            mentioned.append("event_type")
    for impact in sorted(IMPACT_LEVELS, key=len, reverse=True):
        if impact in normalized:
            slots["impact_level"] = impact
            mentioned.append("impact_level")
    if "todas las estaciones" in normalized or "red completa" in normalized:
        slots["affected_stations"] = ["all"]
        mentioned.append("affected_stations")
    if "lluvia" in normalized:
        slots["rain"] = True
        mentioned.append("rain")
    if "lluvia intensa" in normalized:
        slots["heavy_rain"] = True
        mentioned.append("heavy_rain")
    precip = re.search(r"(\d+(?:[,.]\d+)?)\s*mm\b", normalized)
    if precip:
        slots["precip_mm"] = float(precip.group(1).replace(",", "."))
        mentioned.append("precip_mm")
    for alert in ALERT_LEVELS:
        if alert != "sin_alerta" and alert in normalized:
            slots["alert_level"] = alert
            mentioned.append("alert_level")
    return {
        "domain": domain,
        "intent": intent,
        "date_range": date_range,
        "slots": slots,
        "mentioned_fields": mentioned,
        "missing_required_slots": [],
        "validation_errors": [],
        "warnings": ["local_fallback_used"],
    }


def infer_date_range(normalized: str, reference: date) -> dict[str, str] | None:
    if "pasado mañana" in normalized or "pasado manana" in normalized:
        target = reference + timedelta(days=2)
        return {"start": target.isoformat(), "end": target.isoformat()}
    if "mañana" in normalized or "manana" in normalized:
        target = reference + timedelta(days=1)
        return {"start": target.isoformat(), "end": target.isoformat()}
    if "hoy" in normalized:
        return {"start": reference.isoformat(), "end": reference.isoformat()}
    explicit = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", normalized)
    if explicit:
        day, month, year = map(int, explicit.groups())
        target = date(year, month, day)
        return {"start": target.isoformat(), "end": target.isoformat()}
    return None


def has_temporal_hint(text: str) -> bool:
    normalized = text.lower()
    temporal_words = (
        "hoy",
        "mañana",
        "manana",
        "pasado mañana",
        "pasado manana",
        "domingo",
        "lunes",
        "martes",
        "miercoles",
        "miércoles",
        "jueves",
        "viernes",
        "sabado",
        "sábado",
        "fin de semana",
    )
    if any(word in normalized for word in temporal_words):
        return True
    if re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", normalized):
        return True
    if re.search(
        r"\b\d{1,2}\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b",
        normalized,
    ):
        return True
    if re.search(r"\bdel?\s+\d{1,2}\s+al\s+\d{1,2}\b", normalized):
        return True
    return bool(
        re.search(
            r"\bdel?\s+(lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)\s+al\s+(lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)\b",
            normalized,
        )
    )
