"""HTTP access to datamodel-workflow without importing its Python package."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Any

import httpx

from dmw_experiments.studies.haiu_comparison.haiu_ontologizer.models import (
    RegestText,
)


_LEGACY_REGEST_FORMATTING_TOKENS = ("&w&w", "&w&", "&w", "&y")


class RegestNotFoundError(RuntimeError):
    """Raised when datamodel-workflow has no raw regest for an ID.

    :param regest_id: Datamodel regest identifier.
    :param status_code: HTTP status code returned by datamodel-workflow.
    :param response_text: Raw response text for diagnostic output.
    """

    def __init__(
        self, regest_id: str, status_code: int, response_text: str
    ) -> None:
        self.regest_id = regest_id
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(
            f"Regest fetch failed for {regest_id} "
            f"({status_code}): {response_text}"
        )


@dataclass(frozen=True, slots=True)
class WorkflowRequestConfig:
    """Settings used to build one datamodel E2E workflow request.

    :param branch: DMW ontology branch containing the requested context version.
    :param annotation_model: Model used by datamodel's annotation stage.
    :param annotation_guideline_version: Annotation guideline version.
    :param annotation_min_version: Optional minimum annotation version.
    :param annotation_top_n: Example retrieval count for annotation.
    :param annotation_example_limit: Example limit for annotation.
    :param ontology_record_version: Datamodel ontology record version.
    :param ontology_context_version: Existing ontology version used as context.
    :param ontology_user_input: Historian instruction text.
    :param ontology_min_example_version: Minimum prior example ontology version.
    :param ontology_model_name: Model used by datamodel's ontology stage.
    :param ontology_context_mode: ``rag`` or ``full_ontology``.
    :param ontology_example_limit: Top-ranked OPA modeling examples.
    :param max_output_tokens: Configured output ceiling for both stages.
    :param output_safety_margin_tokens: Reserved model context allowance.
    :param require_exact_prompt_tokens: Require pinned chat-template counting.
    :param require_finish_reason: Require provider stop metadata for publication.
    :param include_annotations: Whether datamodel should include annotations.
    :param use_only_existing_ontology_terms: Strict reuse flag.
    :param allow_text_interpretation: Whether OPA may infer implicit text facts.
    :param existing_data_policy: Datamodel reuse policy.
    :param require_existing_annotation: Refuse annotation generation inside the
        ontology condition.
    :param frozen_annotation_sha256: Expected canonical annotation digest.
    """

    branch: str
    annotation_model: str
    annotation_guideline_version: str
    annotation_min_version: str | None
    annotation_top_n: int
    annotation_example_limit: int
    ontology_record_version: str
    ontology_context_version: str
    ontology_user_input: str
    ontology_min_example_version: str
    ontology_model_name: str
    ontology_context_mode: str
    ontology_example_limit: int
    max_output_tokens: int
    output_safety_margin_tokens: int
    require_exact_prompt_tokens: bool
    require_finish_reason: bool
    include_annotations: bool
    use_only_existing_ontology_terms: bool
    allow_text_interpretation: bool
    existing_data_policy: str
    require_existing_annotation: bool = False
    frozen_annotation_sha256: str | None = None


class DatamodelClient:
    """Small authenticated client for datamodel-workflow.

    :param base_url: Backend API base URL.
    :param login: Username or email accepted by ``/auth/login``.
    :param password: Password accepted by ``/auth/login``.
    :param timeout_seconds: Request timeout.
    """

    def __init__(
        self,
        *,
        base_url: str,
        login: str,
        password: str,
        timeout_seconds: float,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._login = login
        self._password = password
        self._client = httpx.Client(timeout=timeout_seconds)
        self._access_token: str | None = None

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def authenticate(self) -> str:
        """Authenticate and cache a bearer token.

        :return: Access token.
        """
        response = self._client.post(
            f"{self._base_url}/auth/login",
            json={"login": self._login, "password": self._password},
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Authentication failed ({response.status_code}): {response.text}"
            )
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Authentication response missing access_token")
        self._access_token = str(token)
        return self._access_token

    def _headers(self) -> dict[str, str]:
        token = self._access_token or self.authenticate()
        return {"Authorization": f"Bearer {token}"}

    def get_regest_payload(self, regest_id: str) -> dict[str, Any]:
        """Fetch one regest payload from datamodel-workflow.

        :param regest_id: Datamodel regest identifier.
        :return: Decoded JSON payload.
        """
        encoded_id = urllib.parse.quote(regest_id, safe="")
        response = self._client.get(
            f"{self._base_url}/api/regest/{encoded_id}",
            headers=self._headers(),
        )
        if response.status_code == 401:
            self.authenticate()
            response = self._client.get(
                f"{self._base_url}/api/regest/{encoded_id}",
                headers=self._headers(),
            )
        if response.status_code == 404:
            raise RegestNotFoundError(
                regest_id, response.status_code, response.text
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"Regest fetch failed for {regest_id} "
                f"({response.status_code}): {response.text}"
            )
        return response.json()

    def get_model_catalog(self, *, use_case: str) -> dict[str, Any]:
        """Fetch DMW's effective model capabilities and generation settings.

        :param use_case: Catalog filter such as ``ontology`` or ``ner``.
        :return: Decoded model catalog.
        """
        response = self._client.get(
            f"{self._base_url}/api/models/catalog",
            params={"use_case": use_case},
            headers=self._headers(),
        )
        if response.status_code == 401:
            self.authenticate()
            response = self._client.get(
                f"{self._base_url}/api/models/catalog",
                params={"use_case": use_case},
                headers=self._headers(),
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"Model catalog fetch failed for {use_case} "
                f"({response.status_code}): {response.text}"
            )
        payload = response.json()
        if not payload.get("success"):
            raise RuntimeError(
                f"Model catalog for {use_case} was not successful."
            )
        return payload

    def get_ontology_branches(self) -> list[dict[str, Any]]:
        """Fetch DMW's live database-branch identities.

        :return: Branch registry records exposed by the authenticated API.
        :raises RuntimeError: If the response is unsuccessful or malformed.
        """
        response = self._client.get(
            f"{self._base_url}/api/github_ontology/branches",
            headers=self._headers(),
        )
        if response.status_code == 401:
            self.authenticate()
            response = self._client.get(
                f"{self._base_url}/api/github_ontology/branches",
                headers=self._headers(),
            )
        if response.status_code != 200:
            raise RuntimeError(
                "DMW branch-catalogue fetch failed "
                f"({response.status_code}): {response.text}"
            )
        payload = response.json()
        branches = payload.get("branches")
        if not payload.get("success") or not isinstance(branches, list):
            raise RuntimeError("DMW branch-catalogue response is malformed.")
        if not all(isinstance(branch, dict) for branch in branches):
            raise RuntimeError(
                "DMW branch catalogue contains an invalid record."
            )
        return branches

    def has_completed_annotation(
        self,
        *,
        regest_id: str,
        version: str,
        branch: str,
    ) -> bool:
        """Check whether DMW can supply the shared annotation for a pair.

        The explicit annotated-regest route distinguishes an accepted
        annotation from the raw-regest fallback returned by the unversioned
        route. Generation placeholders are incomplete and therefore do not
        satisfy the paired-condition precondition.

        :param regest_id: Datamodel regest identifier.
        :param version: Exact annotation guideline version.
        :param branch: Branch containing the annotation.
        :return: Whether a non-placeholder annotation exists.
        """
        encoded_id = urllib.parse.quote(regest_id, safe="")
        encoded_version = urllib.parse.quote(version, safe="")
        url = f"{self._base_url}/api/regest/{encoded_id}/{encoded_version}"
        params = {"regest_type": "annotated", "branch": branch}
        response = self._client.get(
            url,
            params=params,
            headers=self._headers(),
        )
        if response.status_code == 401:
            self.authenticate()
            response = self._client.get(
                url,
                params=params,
                headers=self._headers(),
            )
        if response.status_code == 404:
            return False
        if response.status_code != 200:
            raise RuntimeError(
                f"Annotation availability check failed for {regest_id} "
                f"({response.status_code}): {response.text}"
            )
        payload = response.json()
        data = payload.get("data")
        if not payload.get("success") or not isinstance(data, dict):
            raise RuntimeError(
                f"Annotation availability response for {regest_id} "
                "is malformed."
            )
        annotation_delta = data.get("annotation_guideline_delta")
        returned_version = (
            annotation_delta.get("version")
            if isinstance(annotation_delta, dict)
            else None
        )
        return (
            payload.get("type") in {"annotated", "ontology"}
            and returned_version == version
            and not bool(data.get("generation_placeholder"))
        )

    def get_regest_text(self, regest_id: str) -> RegestText:
        """Fetch and normalize one raw-only regest text.

        :param regest_id: Datamodel regest identifier.
        :return: Header and ordered subentry texts.
        """
        return regest_text_from_payload(
            regest_id, self.get_regest_payload(regest_id)
        )

    def run_workflow(
        self, *, regest_id: str, config: WorkflowRequestConfig
    ) -> tuple[int, dict[str, Any]]:
        """Run one datamodel E2E request.

        :param regest_id: Datamodel regest identifier.
        :param config: Workflow request settings.
        :return: HTTP status and decoded response payload.
        """
        payload = build_workflow_payload(regest_id=regest_id, config=config)
        response = self._client.post(
            f"{self._base_url}/api/workflow/e2e/run",
            json=payload,
            headers=self._headers(),
        )
        if response.status_code == 401:
            self.authenticate()
            response = self._client.post(
                f"{self._base_url}/api/workflow/e2e/run",
                json=payload,
                headers=self._headers(),
            )
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}
        return response.status_code, body

    def get_annotation_review(
        self,
        *,
        regest_id: str,
        version: str,
        branch: str,
    ) -> tuple[int, dict[str, Any]]:
        """Fetch the exact annotation content stored by DMW.

        :param regest_id: Datamodel regest identifier.
        :param version: Annotation guideline version.
        :param branch: DMW ontology branch.
        :return: HTTP status and decoded response body.
        """
        return self._request_json(
            "POST",
            "/api/ner/review",
            json={
                "regest_id": regest_id,
                "version": version,
                "branch": branch,
            },
        )

    def start_annotation_generation(
        self,
        *,
        regest_id: str,
        config: WorkflowRequestConfig,
    ) -> tuple[int, dict[str, Any]]:
        """Start annotation generation without entering ontology generation.

        :param regest_id: Datamodel regest identifier.
        :param config: Shared annotation and branch settings.
        :return: HTTP status and decoded response body.
        """
        return self._request_json(
            "POST",
            "/api/ner/generate",
            json={
                "model": config.annotation_model,
                "guideline_version": config.annotation_guideline_version,
                "regest_ids": [regest_id],
                "branch": config.branch,
                "min_version": config.annotation_min_version,
                "top_n": config.annotation_top_n,
                "example_limit": config.annotation_example_limit,
            },
        )

    def get_annotation_progress(
        self,
        *,
        session_id: str,
    ) -> tuple[int, dict[str, Any]]:
        """Fetch one annotation-generation progress checkpoint.

        :param session_id: DMW progress-session identifier.
        :return: HTTP status and decoded response body.
        """
        encoded_id = urllib.parse.quote(session_id, safe="")
        return self._request_json(
            "GET",
            f"/api/ner/progress/{encoded_id}",
        )

    def accept_annotation(
        self,
        *,
        regest_id: str,
        version: str,
        branch: str,
        header_entities: list[dict[str, Any]],
        subentry_entities: list[dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        """Accept the reviewed annotation without changing its content.

        :param regest_id: Datamodel regest identifier.
        :param version: Annotation guideline version.
        :param branch: DMW ontology branch.
        :param header_entities: Reviewed header annotations.
        :param subentry_entities: Reviewed subentry annotations.
        :return: HTTP status and decoded response body.
        """
        return self._request_json(
            "POST",
            "/api/ner/accept",
            json={
                "regest_id": regest_id,
                "version": version,
                "branch": branch,
                "header_entities": header_entities,
                "subentry_entities": subentry_entities,
            },
        )

    def reject_annotation(
        self,
        *,
        regest_id: str,
        version: str,
        branch: str,
    ) -> tuple[int, dict[str, Any]]:
        """Delete an incomplete annotation before a preparation retry.

        :param regest_id: Datamodel regest identifier.
        :param version: Annotation guideline version.
        :param branch: DMW ontology branch.
        :return: HTTP status and decoded response body.
        """
        return self._request_json(
            "POST",
            "/api/ner/reject",
            json={
                "regest_id": regest_id,
                "version": version,
                "branch": branch,
            },
        )

    def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Send one authenticated request and decode an object response.

        :param method: HTTP method.
        :param endpoint: API path beginning with ``/``.
        :param json: Optional JSON request body.
        :return: HTTP status and an object-shaped response body.
        """
        response = self._client.request(
            method,
            f"{self._base_url}{endpoint}",
            json=json,
            headers=self._headers(),
        )
        if response.status_code == 401:
            self.authenticate()
            response = self._client.request(
                method,
                f"{self._base_url}{endpoint}",
                json=json,
                headers=self._headers(),
            )
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}
        if not isinstance(body, dict):
            body = {"raw": body}
        return response.status_code, body


def _ordered_subentry_texts(value: Any) -> tuple[str, ...]:
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda item: int(str(item[0])))
        return tuple(str(item[1].get("text") or "") for item in items)
    if isinstance(value, list):
        return tuple(str(item.get("text") or "") for item in value)
    return ()


def regest_text_from_payload(
    regest_id: str, payload: dict[str, Any]
) -> RegestText:
    """Normalize datamodel's regest response into raw text only.

    :param regest_id: Datamodel regest identifier.
    :param payload: Response from ``GET /api/regest/{regest_id}``.
    :return: Raw-only regest text.
    :raises ValueError: If the response is not successful or lacks text.
    """
    if not payload.get("success"):
        raise ValueError(f"Regest payload for {regest_id} is not successful.")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"Regest payload for {regest_id} is missing data.")
    header = data.get("header")
    header_text = (
        str(header.get("text") or "") if isinstance(header, dict) else ""
    )
    subentries = _ordered_subentry_texts(data.get("subentries"))
    if not header_text.strip() and not any(item.strip() for item in subentries):
        raise ValueError(f"Regest payload for {regest_id} contains no text.")
    if any(
        token in text
        for text in (header_text, *subentries)
        for token in _LEGACY_REGEST_FORMATTING_TOKENS
    ):
        raise ValueError(
            f"Regest payload for {regest_id} contains a legacy formatting "
            "token; refresh the RG_raw source data before running the "
            "experiment."
        )
    return RegestText(
        regest_id=regest_id,
        header=header_text,
        subentries=tuple(item for item in subentries if item.strip()),
    )


def build_workflow_payload(
    *, regest_id: str, config: WorkflowRequestConfig
) -> dict[str, Any]:
    """Build the datamodel E2E request body.

    :param regest_id: Datamodel regest identifier.
    :param config: Workflow request settings.
    :return: JSON-serializable request body.
    """
    return {
        "regest_id": regest_id,
        "branch": config.branch,
        "annotation": {
            "model": config.annotation_model,
            "guideline_version": config.annotation_guideline_version,
            "min_version": config.annotation_min_version,
            "top_n": config.annotation_top_n,
            "example_limit": config.annotation_example_limit,
        },
        "ontology": {
            "version": config.ontology_record_version,
            "ontology_version": config.ontology_context_version,
            "user_input": config.ontology_user_input,
            "min_example_version": config.ontology_min_example_version,
            "model_name": config.ontology_model_name,
            "context_mode": config.ontology_context_mode,
            "ontology_example_limit": config.ontology_example_limit,
            "max_output_tokens": config.max_output_tokens,
            "output_safety_margin_tokens": (config.output_safety_margin_tokens),
            "require_exact_prompt_tokens": (config.require_exact_prompt_tokens),
            "use_only_existing_ontology_terms": (
                config.use_only_existing_ontology_terms
            ),
            "allow_text_interpretation": config.allow_text_interpretation,
            "include_annotations": config.include_annotations,
        },
        "persist_debug_output": True,
        "existing_data_policy": config.existing_data_policy,
        "require_existing_annotation": config.require_existing_annotation,
    }
