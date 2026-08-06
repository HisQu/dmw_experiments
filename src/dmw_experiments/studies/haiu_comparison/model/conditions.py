"""Stable identifiers used throughout the Haiu comparison study."""

from __future__ import annotations

from enum import StrEnum


class ConditionId(StrEnum):
    """Identify one scientific ontology-generation condition."""

    DMW_FULL_ONTOLOGY = "workflow_full_ontology"
    DMW_HAIU_RAG = "workflow_rag"
    HAIU_RAG = "haiu_rag_ontologizer"


class ExecutionId(StrEnum):
    """Identify one independently supervised provider execution."""

    ACADEMICCLOUD = "academiccloud"
    LMSTUDIO = "lmstudio"


class RunMode(StrEnum):
    """Identify whether a copied run measures one or every input unit."""

    SMOKE = "smoke"
    FULL = "full"


CONDITION_IDS = tuple(condition.value for condition in ConditionId)
EXECUTION_IDS = tuple(execution.value for execution in ExecutionId)
RUN_MODES = tuple(mode.value for mode in RunMode)
