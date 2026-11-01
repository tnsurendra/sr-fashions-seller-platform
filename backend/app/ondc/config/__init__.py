"""Lazy ONDC settings: importing the admin application requires no ONDC secrets."""
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from pydantic import AfterValidator, Field, SecretStr, StringConstraints, model_validator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.ondc.utils.validation import http_url

Url = Annotated[str, StringConstraints(min_length=1), AfterValidator(http_url)]
Identity = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RouteSettings(BaseSettings):
    """Only nonsecret routing is loaded during seller/admin startup."""
    model_config = SettingsConfigDict(env_prefix="ONDC_", env_file=Path(__file__).resolve().parents[3] / ".env", extra="ignore")
    route_prefix: str = ""

    @field_validator("route_prefix")
    @classmethod
    def safe_prefix(cls, value):
        import re
        value = value.rstrip("/")
        if value and not re.fullmatch(r"/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", value):
            raise ValueError("Invalid ONDC route prefix")
        return value


class ONDCSettings(RouteSettings):
    model_config = SettingsConfigDict(
        env_prefix="ONDC_", env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True,
    )
    environment: Literal["local", "staging", "preprod", "production"] = "local"
    domain: Literal["ONDC:RET12"] = "ONDC:RET12"
    network_role: Literal["Seller"] = "Seller"
    node_type: Literal["ISN"] = "ISN"
    subscriber_id: Identity
    subscriber_url: Url
    callback_url: Url
    unique_key_id: Identity
    country: Literal["IND"] = "IND"
    city: Annotated[str, StringConstraints(pattern=r"^std:[0-9]+$")]
    supported_cities: list[Annotated[str, StringConstraints(pattern=r"^std:[0-9]+$")]] = []
    protocol_version: Literal["1.2.5"] = "1.2.5"
    external_network_enabled: bool = False
    registry_url: Url | None = None
    http_timeout: float = Field(default=5, gt=0, le=60)
    registry_cache_seconds: int = Field(default=60, ge=0, le=300)
    replay_retention_seconds: int = Field(default=86400, ge=3600)
    catalog_sync_interval_seconds: int = Field(default=300, ge=60, le=1800)
    allow_local_peer_search: bool = False
    allow_local_callbacks: bool = False
    signing_private_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    signing_public_key: str | None = None
    encryption_private_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    encryption_public_key: str | None = None
    onboarding_request_id: Identity | None = None
    registry_public_key: str | None = None

    @model_validator(mode="after")
    def identity_urls(self):
        if not self.supported_cities:
            self.supported_cities = [self.city]
        if self.city not in self.supported_cities:
            raise ValueError("Primary city must be included in supported cities")
        # Subscriber identity is a hostname, not a URL.
        if urlsplit(self.subscriber_url).hostname != self.subscriber_id:
            raise ValueError("subscriber_url hostname must match subscriber_id")
        if urlsplit(self.callback_url).hostname != self.subscriber_id:
            raise ValueError("callback_url hostname must match subscriber_id")
        if self.environment != "local" and any(urlsplit(url).scheme != "https" for url in [self.subscriber_url, self.callback_url]):
            raise ValueError("Non-local configuration requires HTTPS")
        if self.environment != "local" and (self.allow_local_peer_search or self.allow_local_callbacks):
            raise ValueError("Development options require local environment")
        if self.environment == "production":
            raise ValueError("Production discovery is outside the supported development scope")
        if self.environment == "preprod":
            required = {
                "signing_private_key": self.signing_private_key,
                "signing_public_key": self.signing_public_key,
                "encryption_private_key": self.encryption_private_key,
                "encryption_public_key": self.encryption_public_key,
                "onboarding_request_id": self.onboarding_request_id,
                "registry_public_key": self.registry_public_key,
                "registry_url": self.registry_url,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError("Incomplete PreProd configuration: " + ", ".join(missing))
            if self.registry_url != "https://preprod.registry.ondc.org/v2.0/lookup":
                raise ValueError("PreProd Registry lookup URL must use the official v2.0 endpoint")
            if not self.external_network_enabled:
                raise ValueError("PreProd requires explicit ONDC_EXTERNAL_NETWORK_ENABLED=true")
        return self


@lru_cache
def get_ondc_settings() -> ONDCSettings:
    return ONDCSettings()
