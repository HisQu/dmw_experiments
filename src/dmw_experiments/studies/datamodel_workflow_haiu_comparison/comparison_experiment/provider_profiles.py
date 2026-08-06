"""Pinned provider profiles for the publication comparison runs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    """Describe one reproducible Qwen 3.6 27B execution environment.

    :param name: Stable command-line and manifest identifier.
    :param logical_generation_model: Model family shared by both replications.
    :param provider_generation_model: Exact identifier sent to the provider.
    :param quantization: Weight quantization used for the served model weights.
    :param weight_artifact: Published model artifact or local model-file identity.
    :param chat_provider: Human-readable generation provider label.
    :param embedding_provider: Human-readable retrieval embedding provider label.
    """

    name: str
    logical_generation_model: str
    provider_generation_model: str
    quantization: str
    weight_artifact: str
    chat_provider: str
    embedding_provider: str = "academiccloud"

    def manifest_entry(self) -> dict[str, str | None]:
        """Return non-secret provenance stored in the immutable manifest.

        :return: JSON-compatible provider-profile description.
        """
        return {
            "name": self.name,
            "logical_generation_model": self.logical_generation_model,
            "provider_generation_model": self.provider_generation_model,
            "quantization": self.quantization,
            "weight_artifact": self.weight_artifact,
            "chat_provider": self.chat_provider,
            "embedding_provider": self.embedding_provider,
            "embedding_model": "qwen3-embedding-4b",
        }


ACADEMICCLOUD_QWEN36 = ProviderProfile(
    name="academiccloud-qwen36",
    logical_generation_model="qwen3.6-27b",
    provider_generation_model="qwen3.6-27b",
    quantization="FP8",
    weight_artifact="Qwen/Qwen3.6-27B-FP8",
    chat_provider="academiccloud",
)

LMSTUDIO_QWEN36_Q6 = ProviderProfile(
    name="lmstudio-qwen36-q6",
    logical_generation_model="qwen3.6-27b",
    # > DMW/GTA advertises this exact input name. The LM Studio proxy maps it
    # > to the loaded RTX Q6 variant at HTTP time.
    provider_generation_model="qwen/qwen3.6-27b",
    quantization="Q6",
    weight_artifact="record exact local Q6 model-file SHA-256 in environment_lock",
    chat_provider="lmstudio",
)

PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    profile.name: profile
    for profile in (ACADEMICCLOUD_QWEN36, LMSTUDIO_QWEN36_Q6)
}


def provider_profile(name: str) -> ProviderProfile:
    """Resolve one supported publication provider profile.

    :param name: Stable profile identifier.
    :return: Profile with exact generation and embedding provenance.
    :raises ValueError: If the requested profile is not part of this protocol.
    """
    try:
        return PROVIDER_PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown provider profile: {name}") from exc
