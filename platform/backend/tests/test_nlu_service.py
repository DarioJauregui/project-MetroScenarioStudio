from __future__ import annotations

from datetime import date
import json
from urllib import request

from metro_scenario_studio.services.nlp_service import (
    LlmChatClient,
    LocalLlmChatClient,
    NaturalLanguageService,
    build_system_prompt,
    parse_last_json_object,
)


class FakeClient(LlmChatClient):
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, str]] = []

    def chat(self, system_prompt: str, input_text: str) -> str:
        self.calls.append({"system_prompt": system_prompt, "input": input_text})
        return self.responses.pop(0)


def test_parse_last_json_object_extracts_trailing_valid_json() -> None:
    payload = parse_last_json_object(
        'razonamiento previo {"bad": true} final {"domain":"eventos","slots":{"impact_level":"medio"}}'
    )

    assert payload == {"domain": "eventos", "slots": {"impact_level": "medio"}}


def test_system_prompt_few_shots_are_valid_json() -> None:
    json_lines = [
        line.removeprefix("JSON: ").strip() for line in build_system_prompt().splitlines() if line.startswith("JSON: ")
    ]

    assert json_lines
    for line in json_lines:
        payload = json.loads(line)
        assert "frames" in payload
        assert isinstance(payload["frames"], list)


def test_local_llm_client_uses_minimal_compatible_payload_by_default(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"response":"{}"}'

    def fake_urlopen(http_request: request.Request, timeout: float):
        captured["timeout"] = timeout
        captured["body"] = json.loads(http_request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(request, "urlopen", fake_urlopen)
    client = LocalLlmChatClient(
        endpoint="http://localhost:1234/api/v1/chat",
        model="mistralai/devstral-small-2507",
        timeout_seconds=7,
    )

    client.chat("system", "input")

    assert captured["timeout"] == 7
    assert captured["body"] == {
        "model": "mistralai/devstral-small-2507",
        "system_prompt": "system",
        "input": "/no_think\ninput",
    }


def test_local_llm_client_can_send_generation_options_when_enabled(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"response":"{}"}'

    def fake_urlopen(http_request: request.Request, timeout: float):
        captured["body"] = json.loads(http_request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(request, "urlopen", fake_urlopen)
    client = LocalLlmChatClient(
        endpoint="http://localhost:1234/api/v1/chat",
        model="mistralai/devstral-small-2507",
        timeout_seconds=7,
        max_tokens=384,
        temperature=0,
        send_generation_options=True,
    )

    client.chat("system", "input")

    assert captured["body"]["max_tokens"] == 384
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["stream"] is False


def test_local_llm_client_extracts_lm_studio_output_content(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(
                {
                    "model_instance_id": "mistralai/devstral-small-2507",
                    "output": [
                        {
                            "type": "message",
                            "content": '{"frames":[{"domain":"meteorologia","intent":"modificar_meteorologia","date_range":{"start":"2026-03-07","end":"2026-03-07"},"slots":{"rain":true},"mentioned_fields":["rain"],"missing_required_slots":[],"validation_errors":[],"warnings":[]}]}',
                        }
                    ],
                }
            ).encode("utf-8")

    monkeypatch.setattr(request, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    client = LocalLlmChatClient(
        endpoint="http://localhost:1234/api/v1/chat",
        model="mistralai/devstral-small-2507",
        timeout_seconds=7,
    )

    assert client.chat("system", "input").startswith('{"frames"')


def test_nlu_retries_once_when_model_returns_invalid_json() -> None:
    client = FakeClient(
        [
            "no es json",
            '{"domain":"eventos","intent":"crear_evento","date_range":{"start":"2026-04-12","end":"2026-04-12"},"slots":{"event_type":"deportivo","impact_level":"medio","affected_stations":["all"]},"mentioned_fields":["event_type","impact_level","affected_stations"],"missing_required_slots":[],"validation_errors":[],"warnings":[]}',
        ]
    )
    service = NaturalLanguageService(llm_client=client)

    result = service.parse(
        "Crear evento deportivo el 12/04/2026 con impacto medio en todas las estaciones",
        reference_date=date(2026, 4, 10),
        stations=[],
    )

    assert len(client.calls) == 2
    assert result.detected_items[0].type == "event"
    assert result.detected_items[0].payload["intent"] == "crear_evento"


def test_nlu_missing_date_is_not_applied() -> None:
    client = FakeClient(
        [
            '{"domain":"eventos","intent":"crear_evento","slots":{"event_type":"deportivo"},"mentioned_fields":["event_type"],"missing_required_slots":["date_range"],"validation_errors":[],"warnings":[]}',
        ]
    )
    service = NaturalLanguageService(llm_client=client)

    result = service.parse(
        "Crear evento deportivo con impacto medio",
        reference_date=date(2026, 4, 10),
        stations=[],
    )

    assert len(client.calls) == 1
    assert result.detected_items == []
    assert result.not_used[0].reason == "missing_date"
    assert "Debes indicar el día o rango" in result.not_used[0].text


def test_nlu_validates_categorical_values_against_catalogs() -> None:
    client = FakeClient(
        [
            '{"domain":"meteorologia","intent":"modificar_meteorologia","date_range":{"start":"2026-04-11","end":"2026-04-11"},"slots":{"alert_level":"azul","precip_mm":20},"mentioned_fields":["alert_level","precip_mm"],"missing_required_slots":[],"validation_errors":[],"warnings":[]}',
        ]
    )
    service = NaturalLanguageService(llm_client=client)

    result = service.parse(
        "Mañana pon lluvia intensa, 20 mm y alerta azul",
        reference_date=date(2026, 4, 10),
        stations=[],
    )

    assert result.detected_items == []
    assert result.not_used[0].reason == "invalid_catalog_value"
    assert "alert_level=azul" in result.not_used[0].text


def test_nlu_accepts_multiple_frames_and_normalizes_station_labels() -> None:
    client = FakeClient(
        [
            """
            {
              "frames": [
                {
                  "domain": "eventos",
                  "intent": "crear_evento",
                  "date_range": {"start": "2026-04-13", "end": "2026-04-13"},
                  "slots": {"event_type": "deportivo", "affected_stations": ["Guadalmedina"]},
                  "mentioned_fields": ["event_type", "affected_stations"],
                  "missing_required_slots": [],
                  "validation_errors": [],
                  "warnings": []
                },
                {
                  "domain": "meteorologia",
                  "intent": "modificar_meteorologia",
                  "date_range": {"start": "2026-04-13", "end": "2026-04-13"},
                  "slots": {"rain": true},
                  "mentioned_fields": ["rain"],
                  "missing_required_slots": [],
                  "validation_errors": [],
                  "warnings": []
                }
              ]
            }
            """,
        ]
    )
    service = NaturalLanguageService(llm_client=client)

    result = service.parse(
        "Partido del Malaga con lluvia mañana afectando a Guadalmedina",
        reference_date=date(2026, 4, 12),
        stations=[{"series_id": "GDM", "estacion": "Guadalmedina", "station_abbrev": "GDM"}],
    )

    assert [item.type for item in result.detected_items] == ["event", "weather"]
    event = result.detected_items[0]
    assert event.name == "Evento sin nombre"
    assert event.affected_stations == ["GDM"]
    assert event.payload["slots"]["affected_stations"] == ["GDM"]


def test_nlu_station_label_matches_all_lines_for_that_station() -> None:
    client = FakeClient(
        [
            '{"frames":[{"domain":"eventos","intent":"crear_evento","date_range":{"start":"2026-03-07","end":"2026-03-07"},"slots":{"event_type":"deportivo","affected_stations":["Guadalmedina"]},"mentioned_fields":["event_type","affected_stations"],"missing_required_slots":[],"validation_errors":[],"warnings":[]}]}',
        ]
    )
    service = NaturalLanguageService(llm_client=client)

    result = service.parse(
        "Partido el 7/3/26 afectando a Guadalmedina",
        reference_date=date(2026, 3, 6),
        stations=[
            {"series_id": "GDL1", "estacion": "Guadalmedina", "station_abbrev": "GDL1"},
            {"series_id": "GDL2", "estacion": "Guadalmedina", "station_abbrev": "GDL2"},
        ],
    )

    assert result.detected_items[0].affected_stations == ["GDL1", "GDL2"]
    assert result.detected_items[0].payload["slots"]["affected_stations"] == ["GDL1", "GDL2"]


def test_nlu_accepts_calendar_holiday_frame() -> None:
    client = FakeClient(
        [
            '{"domain":"calendario","intent":"marcar_festivo","date_range":{"start":"2026-02-18","end":"2026-02-18"},"slots":{"is_holiday":true},"mentioned_fields":["is_holiday"],"missing_required_slots":[],"validation_errors":[],"warnings":[]}',
        ]
    )
    service = NaturalLanguageService(llm_client=client)

    result = service.parse(
        "El 18 de febrero es festivo",
        reference_date=date(2026, 2, 1),
        stations=[],
    )

    assert result.detected_items[0].type == "calendar"
    assert result.detected_items[0].payload["intent"] == "marcar_festivo"


def test_nlu_treats_empty_schema_date_range_as_missing_date() -> None:
    client = FakeClient(
        [
            '{"frames":[{"domain":"eventos","intent":"crear_evento","date_range":{"start":"","end":""},"slots":{"event_type":"deportivo"},"mentioned_fields":["event_type"],"missing_required_slots":["date_range"],"validation_errors":[],"warnings":[]}]}',
        ]
    )
    service = NaturalLanguageService(llm_client=client)

    result = service.parse(
        "Crear evento deportivo",
        reference_date=date(2026, 4, 10),
        stations=[],
    )

    assert result.detected_items == []
    assert result.not_used[0].reason == "missing_date"


def test_nlu_local_fallback_extracts_event_name_from_text() -> None:
    from metro_scenario_studio.services.nlp_service import conservative_local_frame

    # Test 1: prefix removal and capitalization
    frame = conservative_local_frame("añadir concierto de Alejandro Sanz hoy", date(2026, 6, 15))
    assert frame["slots"].get("name") == "Concierto de Alejandro Sanz"

    # Test 2: date/type/impact suffix removal
    frame2 = conservative_local_frame("crear evento de feria el 12/04/2026 con impacto medio", date(2026, 6, 15))
    assert frame2["slots"].get("name") == "Feria"
