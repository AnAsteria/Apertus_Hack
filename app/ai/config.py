"""Server-side inference configuration (CONTRACTS section 6, T05).

Read from environment variables only. The API key never leaves this process:
it is excluded from repr/str and must not be logged or sent to the client.
No key configured means inference is disabled; keyword search must still work.
"""
import os
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://gateway.keera.ch/api/v1"
# Architecture step 4: 8B for bulk extraction. 70B only where a measured gain justifies it.
DEFAULT_MODEL = "apertus-v1-5-8b"
DEFAULT_QUALITY_MODEL = "apertus-v1-5-70b"


class ConfigError(ValueError):
    pass


def _num(env: dict, name: str, default, cast):
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        return cast(raw)
    except ValueError as e:
        raise ConfigError(f"{name} must be a {cast.__name__}") from e


@dataclass(frozen=True)
class InferenceConfig:
    base_url: str = DEFAULT_BASE_URL
    api_key: str | None = field(default=None, repr=False)
    model: str = DEFAULT_MODEL
    quality_model: str = DEFAULT_QUALITY_MODEL
    timeout_s: float = 30.0
    max_retries: int = 2
    backoff_base_s: float = 0.5
    backoff_max_s: float = 8.0
    max_concurrency: int = 4

    def __post_init__(self):
        if self.timeout_s <= 0 or self.max_concurrency < 1 or self.max_retries < 0 or self.backoff_base_s < 0:
            raise ConfigError("timeout_s > 0, max_concurrency >= 1, max_retries >= 0, backoff_base_s >= 0")
        if not self.base_url.startswith(("https://", "http://")):
            raise ConfigError("APERTUS_BASE_URL must be an http(s) URL")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def is_local(self) -> bool:
        """A replacement endpoint on this machine (e.g. llama.cpp for the offline proof)."""
        host = self.base_url.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
        return host in ("localhost", "127.0.0.1", "[::1]")

    def redacted(self) -> dict:
        """Safe for logs and probe reports."""
        return {
            "base_url": self.base_url,
            "api_key": "set" if self.api_key else "missing",
            "model": self.model,
            "quality_model": self.quality_model,
            "timeout_s": self.timeout_s,
            "max_retries": self.max_retries,
            "max_concurrency": self.max_concurrency,
        }

    @classmethod
    def from_env(cls, env: dict | None = None) -> "InferenceConfig":
        env = os.environ if env is None else env
        return cls(
            base_url=(env.get("APERTUS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
            api_key=env.get("APERTUS_API_KEY") or None,
            model=env.get("APERTUS_MODEL") or DEFAULT_MODEL,
            quality_model=env.get("APERTUS_QUALITY_MODEL") or DEFAULT_QUALITY_MODEL,
            timeout_s=_num(env, "APERTUS_TIMEOUT_S", 30.0, float),
            max_retries=_num(env, "APERTUS_MAX_RETRIES", 2, int),
            backoff_base_s=_num(env, "APERTUS_BACKOFF_BASE_S", 0.5, float),
            max_concurrency=_num(env, "APERTUS_MAX_CONCURRENCY", 4, int),
        )
