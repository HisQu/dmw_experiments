from typing import Any, cast
from types import SimpleNamespace

from dmw_experiments.studies.haiu_comparison.data_collection.haiu import (
    runner as direct_runner,
)
from haiu import HaiuRC
from haiu.clients.llm.generation_budget import GenerationBudget
from haiu.clients.llm.llm_metrics import LLMCallMeta, LLMCallMetrics
from dmw_experiments.studies.haiu_comparison.data_collection.haiu.runner import (
    DirectRunConfig,
    run_direct_baseline,
)
from dmw_experiments.studies.haiu_comparison.model.traces import (
    RegestText,
)
from dmw_experiments.studies.haiu_comparison.data_collection.haiu.retrieval import (
    RetrievalTrace,
)


class FakeLLMClient:
    calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.system_prompt = str(kwargs["system_prompt"])
        self._responses = iter(
            (
                ("Plan", _meta("Plan")),
                (
                    "# --- TBOX ---\n:A a owl:Class .\n"
                    "# --- ABOX ---\n:i a :A .",
                    _meta(":i a :A ."),
                ),
            )
        )

    def prompt(self, **kwargs: Any) -> tuple[str, LLMCallMeta]:
        self.calls.append(
            {
                "system_prompt": self.system_prompt,
                "ignore_history": kwargs["ignore_history"],
                "max_tokens": kwargs["max_tokens"],
            }
        )
        return next(self._responses)

    def close(self) -> None:
        return None


def test_direct_runner_unpacks_current_haiu_prompt_result(
    monkeypatch,
) -> None:
    FakeLLMClient.calls = []
    monkeypatch.setattr(direct_runner, "LLMClient", FakeLLMClient)
    monkeypatch.setattr(
        direct_runner,
        "retrieve_regest_context",
        lambda **_kwargs: RetrievalTrace(
            query="Header",
            turtle="@prefix : <https://example.org/> .\n:Known a owl:Class .",
            snapshot={"snapshot_fidelity": "native_full_graph"},
            duration_seconds=0.25,
        ),
    )

    trace = run_direct_baseline(
        regest=RegestText(regest_id="11010116", header="Header"),
        config=DirectRunConfig(
            model="model",
            historian_input="Model it.",
            annotation_guidelines="Use historian curation.",
        ),
        rc=cast(HaiuRC, SimpleNamespace(client=object())),
    )

    assert trace.success is True
    assert trace.stage1.output == "Plan"
    assert trace.stage2.output.endswith(":i a :A .")
    assert trace.stage1.response is not None
    assert trace.stage1.response.metrics.prompt_tokens == 10
    assert [call["ignore_history"] for call in FakeLLMClient.calls] == [
        True,
        False,
    ]
    assert trace.retrieved_turtle.endswith(":Known a owl:Class .")
    assert trace.retrieval_duration_seconds == 0.25


def test_direct_runner_uses_predictive_cap_for_each_same_thread_stage(
    monkeypatch,
) -> None:
    FakeLLMClient.calls = []
    measured_messages: list[list[dict[str, str]]] = []
    effective_caps = iter((13_566, 11_000))

    def resolve_generation_budget(
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> GenerationBudget:
        measured_messages.append(messages)
        effective = next(effective_caps)
        return _budget(effective=effective, **kwargs)

    monkeypatch.setattr(direct_runner, "LLMClient", FakeLLMClient)
    monkeypatch.setattr(
        direct_runner,
        "llm_spec",
        lambda _model: SimpleNamespace(context_token_limit=262_144),
    )
    monkeypatch.setattr(
        direct_runner,
        "resolve_generation_budget",
        resolve_generation_budget,
    )
    monkeypatch.setattr(
        direct_runner,
        "retrieve_regest_context",
        lambda **_kwargs: RetrievalTrace(
            query="Header",
            turtle=":Known a owl:Class .",
            snapshot={"snapshot_fidelity": "native_full_graph"},
            duration_seconds=0.1,
        ),
    )

    trace = run_direct_baseline(
        regest=RegestText(regest_id="11010116", header="Header"),
        config=DirectRunConfig(
            model="qwen3.6-27b",
            historian_input="Model it.",
            annotation_guidelines="Guideline.",
            max_tokens=20_000,
            output_safety_margin_tokens=4_096,
        ),
        rc=cast(HaiuRC, SimpleNamespace(client=object())),
    )

    assert trace.success is True
    assert [call["max_tokens"] for call in FakeLLMClient.calls] == [
        13_566,
        11_000,
    ]
    assert [message["role"] for message in measured_messages[0]] == [
        "system",
        "user",
    ]
    assert [message["role"] for message in measured_messages[1]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert trace.stage1.generation_budget is not None
    assert trace.stage1.generation_budget.finish_reason == "stop"
    assert trace.stage2.generation_budget is not None
    assert trace.stage2.generation_budget.output_constrained is True


def _meta(text: str) -> LLMCallMeta:
    return LLMCallMeta(
        text=text,
        model="model",
        metrics=LLMCallMetrics(
            total_time_s=0.1,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            finish_reason="stop",
            completion_tokens_source="provider",
        ),
    )


def _budget(
    *,
    effective: int,
    requested_max_output_tokens: int,
    context_window_tokens: int,
    safety_margin_tokens: int,
    **_kwargs: Any,
) -> GenerationBudget:
    return GenerationBudget(
        requested_max_output_tokens=requested_max_output_tokens,
        predicted_max_output_tokens=effective,
        effective_max_output_tokens=effective,
        measured_prompt_tokens=(
            context_window_tokens - safety_margin_tokens - effective
        ),
        prompt_token_source="huggingface_chat_template",
        provider_prompt_tokens=None,
        context_window_tokens=context_window_tokens,
        safety_margin_tokens=safety_margin_tokens,
        output_constrained=effective < requested_max_output_tokens,
        finish_reason=None,
        output_truncated=None,
        adjustments=(),
        tokenizer_repo="Qwen/Qwen3.6-27B",
        tokenizer_revision="revision",
    )
