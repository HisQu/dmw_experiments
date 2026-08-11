"""Frozen scientific and runtime settings for data collection."""

from __future__ import annotations

from dmw_experiments.studies.haiu_comparison.model.conditions import (
    CONDITION_IDS,
)
from dmw_experiments.studies.haiu_comparison.operations.repository_paths import (
    TEMPLATE_INPUT_ROOT,
)

DEFAULT_LOCAL_IDS = TEMPLATE_INPUT_ROOT / "ablaesse_cp_ids.txt"
DEFAULT_PROMPT_FILE = TEMPLATE_INPUT_ROOT / "historian_ontology_user_input.md"
DEFAULT_ANNOTATION_GUIDELINES_FILE = (
    TEMPLATE_INPUT_ROOT / "annotation_guidelines.md"
)
DEFAULT_CONDITIONS = CONDITION_IDS

PUBLISHED_HAIU_VERSION = "1.8.1"
APPROVED_HAIU_VCS_URL = "https://github.com/HisQu/haiu.git"
APPROVED_HAIU_VCS_REVISION = "v1.8.1"
APPROVED_RUNTIME_DISTRIBUTIONS = {
    "datamodel-workflow": {
        "version": "1.1.4",
        "url": "https://github.com/HisQu/datamodel-workflow.git",
        "revision": "v1.1.4",
        "repository": "datamodel_workflow",
    },
    "opa": {
        "version": "2.1.3",
        "url": "https://github.com/HisQu/OPA.git",
        "revision": "v2.1.3",
        "repository": "opa",
    },
    "gta": {
        "version": "0.2.5",
        "url": "https://github.com/HisQu/GTA.git",
        "revision": "v0.2.5",
        "repository": "gta",
    },
    "haiu": {
        "version": PUBLISHED_HAIU_VERSION,
        "url": APPROVED_HAIU_VCS_URL,
        "revision": APPROVED_HAIU_VCS_REVISION,
        "repository": "haiu",
    },
}

LOCAL_RUNTIME_RECOVERY_MODEL_ID = "qwen/qwen3.6-27b"
LOCAL_RUNTIME_RECOVERY_CONTEXT_WINDOW_TOKENS = 262_144
LOCAL_RUNTIME_CONTEXT_ADMISSION_ERROR = (
    "number of tokens to keep from the initial prompt is greater than the "
    "context length"
)
LOCAL_RUNTIME_STALE_MODEL_ERROR = 'invalid model identifier "qwen3.6-27b-rtx"'
LOCAL_RUNTIME_INITIAL_RESPONSE_ERROR = (
    "failed to get initial ontology modeling response."
)
