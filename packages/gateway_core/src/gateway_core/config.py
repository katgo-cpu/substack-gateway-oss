from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SUBSTACK_GATEWAY_")

    substack_base_url: str = "https://substack.com"
    substack_timeout_sec: float = Field(default=120.0, gt=0)
    substack_connect_timeout_sec: float = Field(default=120.0, gt=0)
    substack_max_connections: int = Field(default=20, ge=1)
    substack_max_keepalive_connections: int = Field(default=5, ge=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG"
    # No default on purpose. This gates administrative surfaces that an
    # extension may expose, so a built-in value would be a published
    # credential: anyone reading this repository would hold it. Unset means
    # "no admin token configured", and a consumer must refuse the request
    # rather than compare against nothing.
    admin_token: str | None = None

    # Exact hostnames (comma separated, no scheme) that session cookies may be
    # sent to as a publication. When set it is the ONLY allow-list; when unset
    # only single-label *.substack.com hosts are accepted. Production should
    # always set this to the BI publication host.
    allowed_publication_hosts: str | None = None

    # Publication analytics timeseries rows are append-only; this many trailing
    # days are treated as still maturing and re-fetched rather than served from
    # a cache, regardless of whether an extension installs one.
    stats_timeseries_watermark_lag_days: int = Field(default=2, ge=0)

    @field_validator("substack_base_url")
    @classmethod
    def _validate_base_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(
                f"substack_base_url must be a valid HTTP or HTTPS URL, got {v!r}"
            )
        return v

    @model_validator(mode="after")
    def _validate_connection_limits(self) -> Settings:
        if self.substack_max_keepalive_connections > self.substack_max_connections:
            raise ValueError(
                "substack_max_keepalive_connections must be less than or equal to "
                "substack_max_connections"
            )
        return self


settings = Settings()
