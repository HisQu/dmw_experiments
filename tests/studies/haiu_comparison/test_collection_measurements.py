from dmw_experiments.studies.haiu_comparison.data_collection.measurements import (
    summarize_rows,
    turtle_generation_input_tokens,
)
from dmw_experiments.studies.haiu_comparison.model.ontology import (
    turtle_syntax_fields,
)
from dmw_experiments.studies.haiu_comparison.model.results import (
    provider_prompt_token_measurement,
)


def test_turtle_generation_input_uses_full_stage2_provider_usage() -> None:
    provider = provider_prompt_token_measurement(150)
    stage2_input = turtle_generation_input_tokens(
        stage1_user="user 1",
        stage1_output="plan",
        stage2_system="system 2",
        stage2_user="user 2",
        stage2_provider_prompt_tokens=150,
        model="cl100k_base",
    )

    assert provider is not None
    assert provider.tokens == 150
    assert provider.source == "provider"
    assert stage2_input.tokens == 150
    assert stage2_input.source == "provider"


def test_turtle_syntax_fields_adds_expected_prefixes() -> None:
    fields = turtle_syntax_fields(
        ":A a owl:Class .\n:i a :A .",
    )

    assert fields["turtle_syntax_valid"] is True
    assert fields["turtle_triple_count"] == 2
    assert fields["turtle_syntax_error"] is None


def test_turtle_syntax_fields_reports_invalid_output() -> None:
    fields = turtle_syntax_fields(":i a")

    assert fields["turtle_syntax_valid"] is False
    assert fields["turtle_triple_count"] is None
    assert fields["turtle_syntax_error"]


def test_turtle_syntax_fields_accepts_one_outer_turtle_fence() -> None:
    fields = turtle_syntax_fields(
        "```ttl\n@prefix : <x:> .\n:i a :Thing .\n```"
    )

    assert fields["turtle_syntax_valid"] is True
    assert fields["turtle_triple_count"] == 1
    assert fields["turtle_outer_fence_removed"] is True


def test_turtle_syntax_fields_does_not_hide_partial_fence() -> None:
    fields = turtle_syntax_fields("```ttl\n:i a :Thing .")

    assert fields["turtle_syntax_valid"] is False
    assert fields["turtle_outer_fence_removed"] is False


def test_turtle_syntax_fields_does_not_guess_unlabelled_fence() -> None:
    fields = turtle_syntax_fields("```\n:i a :Thing .\n```")

    assert fields["turtle_syntax_valid"] is False
    assert fields["turtle_outer_fence_removed"] is False


def test_summary_excludes_failures_from_success_metrics() -> None:
    summary = summarize_rows(
        [
            {
                "condition": "condition",
                "success": True,
                "duration_seconds": 12.0,
                "total_attempt_duration_seconds": 15.0,
                "total_elapsed_seconds": 75.0,
                "prompt_tokens": 100,
                "prompt_tokens_complete": True,
                "output_tokens": 50,
                "turtle_syntax_valid": True,
            },
            {
                "condition": "condition",
                "success": False,
                "duration_seconds": 0.1,
                "total_attempt_duration_seconds": 0.2,
                "total_elapsed_seconds": 60.2,
                "prompt_tokens": 0,
                "prompt_tokens_complete": False,
                "output_tokens": 0,
                "turtle_syntax_valid": None,
            },
        ]
    )["condition"]

    assert summary["duration_seconds"]["count"] == 1
    assert summary["duration_seconds"]["mean"] == 12.0
    assert summary["failure_duration_seconds"]["mean"] == 0.1
    assert summary["total_attempt_duration_seconds"]["mean"] == 15.0
    assert summary["total_elapsed_seconds"]["mean"] == 75.0
    assert summary["failure_total_elapsed_seconds"]["mean"] == 60.2
    assert summary["complete_prompt_tokens"]["mean"] == 100.0
    assert summary["partial_prompt_tokens"]["count"] == 0
    assert summary["output_tokens"]["mean"] == 50.0
    assert summary["turtle_syntax"]["valid_count"] == 1
