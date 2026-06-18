from __future__ import annotations

from datetime import date

from metro_scenario_studio.core.config import Settings
from metro_scenario_studio.domain.schemas import (
    AggregateRow,
    ExecutionResult,
    ExplanationItem,
    PredictionRow,
    ScenarioExecution,
    ScenarioInput,
    ScenarioStatus,
)
from metro_scenario_studio.services.prediction_explanation_service import (
    OpenAICompatibleChatClient,
    PredictionExplanationService,
)


class FakeExplanationClient:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.messages: list[tuple[str, str]] = []

    def chat(self, system_prompt: str, user_payload: str) -> str:
        self.messages.append((system_prompt, user_payload))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_prediction_explanation_service_sends_auditable_prediction_context() -> None:
    client = FakeExplanationClient(
        "La prediccion apunta a una demanda alta por el evento validado y la lluvia prevista."
    )
    service = PredictionExplanationService(
        Settings(explanation_llm_enabled=True),
        llm_client=client,
    )

    summary = service.summarize(_sample_result(ScenarioStatus.WHAT_IF))

    assert "demanda alta" in summary
    assert client.messages
    system_prompt, user_payload = client.messages[0]
    assert "sin afirmar causalidad" in system_prompt
    assert "forecastable_scenario" in user_payload
    assert "manual_overrides" in user_payload
    assert "Partido validado" in user_payload


def test_prediction_explanation_service_falls_back_when_llm_is_unavailable() -> None:
    service = PredictionExplanationService(
        Settings(explanation_llm_enabled=True),
        llm_client=FakeExplanationClient(RuntimeError("LM Studio offline")),
    )

    summary = service.summarize(_sample_result(ScenarioStatus.BASE))

    assert "El resumen LLM local no esta disponible" in summary
    assert "viajes previstos" in summary


def test_prediction_explanation_service_hides_visible_thinking_and_uses_local_summary() -> None:
    service = PredictionExplanationService(
        Settings(explanation_llm_enabled=True),
        llm_client=FakeExplanationClient("Here's a thinking process:\n1. Analizo la peticion."),
    )

    summary = service.summarize(_sample_result(ScenarioStatus.WHAT_IF))

    assert "Here's a thinking process" not in summary
    assert "viajes previstos" in summary
    assert "what_if" in summary


def test_prediction_explanation_service_extracts_final_response_after_thinking_block() -> None:
    llm_response = """
Here's a thinking process:
1. Analizo la peticion.
2. Redacto una respuesta.
</think>

RESPUESTA_FINAL: La prediccion diaria muestra una subida asociada al evento registrado y mantiene avisos de cobertura parcial.

La variante forecastable_scenario permite aplicar este supuesto manual sin interpretarlo como causalidad directa.
""".strip()
    service = PredictionExplanationService(
        Settings(explanation_llm_enabled=True),
        llm_client=FakeExplanationClient(llm_response),
    )

    summary = service.summarize(_sample_result(ScenarioStatus.WHAT_IF))

    assert "Here's a thinking process" not in summary
    assert summary.startswith("La prediccion diaria muestra una subida")
    assert "forecastable_scenario" in summary


def test_prediction_explanation_service_can_be_disabled() -> None:
    service = PredictionExplanationService(Settings(explanation_llm_enabled=False))

    summary = service.summarize(_sample_result(ScenarioStatus.BASE))

    assert summary is None


def test_explanation_client_uses_loaded_lm_studio_model_when_configured_model_is_invalid(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return __import__("json").dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        url = request.full_url
        if url.endswith("/v1/models"):
            return FakeResponse({"data": [{"id": "qwen3.6-35b-a3b"}]})
        body = __import__("json").loads(request.data.decode("utf-8"))
        calls.append((url, body))
        return FakeResponse({"choices": [{"message": {"content": "Resumen generado."}}]})

    monkeypatch.setattr("metro_scenario_studio.services.prediction_explanation_service.request.urlopen", fake_urlopen)
    client = OpenAICompatibleChatClient(
        endpoint="http://localhost:1234/api/v1/chat",
        model="qwen3.6-35b-a3b",
        timeout_seconds=5,
        max_tokens=100,
        temperature=0.2,
    )

    response = client.chat("Sistema", "Payload")

    assert response == "Resumen generado."
    assert calls[0][1]["model"] == "qwen3.6-35b-a3b"


def _sample_result(status: ScenarioStatus) -> ExecutionResult:
    execution = ScenarioExecution(
        id="scn_20260520-20260520_what-if_001",
        status=status,
        range_start=date(2026, 5, 20),
        range_end=date(2026, 5, 20),
        model_variant="forecastable_scenario" if status == ScenarioStatus.WHAT_IF else "strict_available",
        dataset_version="dataset-test",
        warnings=["missing_future_weather"],
        input=ScenarioInput(
            natural_language_comment="Partido del Malaga con lluvia",
            manual_overrides=[{"type": "weather", "field": "rain", "final": True}],
        ),
    )
    return ExecutionResult(
        execution=execution,
        prediction_rows=[
            PredictionRow(
                target_date=date(2026, 5, 20),
                linea="LINEA 1",
                estacion="Atarazanas",
                series_id="ATZ",
                station_abbrev="ATZ",
                network_order=1,
                y_pred=120.0,
                y_real=115.0,
                model_variant=execution.model_variant,
                horizon_days=1,
            )
        ],
        aggregates=[
            AggregateRow(
                level="network",
                target_date=None,
                y_pred=120.0,
                y_real=115.0,
                real_available=True,
            )
        ],
        explanations=[
            ExplanationItem(
                section="texto_libre",
                item_type="llm_validated",
                label="Partido validado",
                description="Evento aceptado por validacion humana.",
                source="llm_with_human_validation",
                used_by_model=True,
                confidence="medium",
            )
        ],
    )
