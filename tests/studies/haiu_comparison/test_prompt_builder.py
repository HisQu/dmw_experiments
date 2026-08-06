import json
from pathlib import Path

from dmw_experiments.studies.haiu_comparison.haiu_ontologizer.models import (
    RegestText,
)
from dmw_experiments.studies.haiu_comparison.haiu_ontologizer.opa_prompt_renderer import (
    INTENTIONAL_STANDALONE_ADDITIONS,
    OPA_PROMPT_SOURCE_COMMIT,
    OPA_PROMPT_SOURCE_PATH,
    OPA_PROMPT_SOURCE_SHA256,
)
from dmw_experiments.studies.haiu_comparison.haiu_ontologizer.prompt_builder import (
    build_stage1_prompts,
    build_stage2_prompts,
    split_turtle_sections,
)


def test_stage1_prompt_uses_raw_regest_and_historian_guidelines() -> None:
    regest = RegestText(
        regest_id="11010116-1",
        header="Header",
        subentries=("Sub 1",),
    )

    prompt = build_stage1_prompts(
        regest=regest,
        historian_input="Make ontology.",
        annotation_guidelines="Tag persons and places conservatively.",
        retrieved_turtle=":Existing a owl:Class .",
    )

    assert "Header" in prompt.user
    assert "Sub 1" in prompt.user
    assert "Historikerinnen-Annotationsrichtlinien" in prompt.user
    assert "keine automatisch erzeugte DMW-Annotation" in prompt.user
    assert "Referenzontologie (Ausschnitt, Turtle)" in prompt.user
    assert ":Existing a owl:Class ." in prompt.user
    assert "Interpretationen sind deaktiviert" in prompt.user
    assert "implizite Ereignisse einfuehren" in prompt.user


def test_stage1_prompt_can_enable_text_interpretation() -> None:
    regest = RegestText(regest_id="11010116-1", header="Header")

    prompt = build_stage1_prompts(
        regest=regest,
        historian_input="Make ontology.",
        retrieved_turtle=":Existing a owl:Class .",
        allow_text_interpretation=True,
    )

    assert "Interpreatationen sind erlaubt" in prompt.user
    assert "Interpretationen sind deaktiviert" not in prompt.user


def test_stage2_prompt_requires_tbox_abox_markers() -> None:
    regest = RegestText(regest_id="11010116-1", header="Header")

    prompt = build_stage2_prompts(
        regest=regest, historian_input="Make ontology."
    )

    assert "# --- TBOX ---" in prompt.user
    assert "# --- ABOX ---" in prompt.user


def test_local_renderer_matches_locked_opa_fixture() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "opa_prompt_parity.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    regest = RegestText(
        regest_id="11010116-1", header="Header", subentries=("Subentry",)
    )

    stage1 = build_stage1_prompts(
        regest=regest,
        historian_input="Historian instruction.",
        annotation_guidelines="Guideline.",
        retrieved_turtle=":Existing a owl:Class .",
    )
    stage2 = build_stage2_prompts(
        regest=regest, historian_input="Historian instruction."
    )

    assert fixture["opa_source"] == {
        "path": OPA_PROMPT_SOURCE_PATH,
        "commit": OPA_PROMPT_SOURCE_COMMIT,
        "sha256": OPA_PROMPT_SOURCE_SHA256,
    }
    assert stage1.system == fixture["stage1_system"]
    assert stage2.system == fixture["stage2_system"]
    assert all(
        section in stage1.user for section in fixture["shared_stage1_sections"]
    )
    assert all(
        section in stage2.user for section in fixture["shared_stage2_sections"]
    )
    assert tuple(fixture["intentional_standalone_additions"]) == (
        INTENTIONAL_STANDALONE_ADDITIONS
    )
    assert "# Petentenvita (Textgrundlage)" in stage1.user
    assert "# Historikerinnen-Annotationsrichtlinien" in stage1.user
    assert "Historian instruction." not in stage2.user


def test_split_turtle_sections() -> None:
    ttl = "@prefix : <x> .\n# --- TBOX ---\n:A a owl:Class .\n# --- ABOX ---\n:i a :A ."

    tbox, abox, warning = split_turtle_sections(ttl)

    assert warning is None
    assert ":A a owl:Class" in tbox
    assert ":i a :A" in abox


def test_split_turtle_sections_removes_outer_markdown_fence() -> None:
    ttl = "\n".join(
        [
            "```turtle",
            "@prefix : <x> .",
            "# --- TBOX ---",
            ":A a owl:Class .",
            "# --- ABOX ---",
            ":i a :A .",
            "```",
        ]
    )

    tbox, abox, warning = split_turtle_sections(ttl)

    assert warning is None
    assert "```" not in tbox
    assert "```" not in abox


def test_split_turtle_sections_warns_when_markers_missing() -> None:
    tbox, abox, warning = split_turtle_sections(":i a :A .")

    assert tbox == ""
    assert abox == ":i a :A ."
    assert warning
