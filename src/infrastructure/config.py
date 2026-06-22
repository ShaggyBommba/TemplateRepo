
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from typing import Literal


PACKAGE_ROOT = Path(__file__).resolve().parents[2]


class LoggingSettings(BaseModel):
    level: str = "INFO"
    json_output: bool = False
    file_handler_enabled: bool = True
    file_path_pattern: str = ".logs/{date}.log"
    stream_handler_enabled: bool = True
    stream_format: str = "[%(asctime)s] %(levelname)-8s [%(threadName)s] %(message)s"
    stream_date_format: str = "%H:%M:%S"


class DatabaseSettings(BaseModel):
    """Configuration for the database used by repositories."""

    provider: str = "sqlite"
    host: str = "localhost"
    port: int = 5432
    user: str = "app"
    password: SecretStr = SecretStr("app")
    database: str = "app"
    ssl_mode: str | None = None

    @property
    def dsn(self) -> str:
        match self.provider:
            case "sqlite":
                return f"sqlite:///{PACKAGE_ROOT / self.database}.db"
            case "postgresql":
                return (
                    f"postgresql://{self.user}:{self.password.get_secret_value()}"
                    f"@{self.host}:{self.port}/{self.database}"
                )
            case _:
                raise ValueError(f"Unsupported database provider: {self.provider}")


class OutboxSettings(BaseModel):
    """Configuration for durable outbox processing policy."""

    default_max_attempts: int = Field(default=3, ge=1)
    claim_timeout_seconds: int = Field(default=300, ge=1)


class KeycloakSettings(BaseModel):
    """Configuration for validating Keycloak-issued access tokens."""

    base_url: str = "http://localhost:8080"
    realm: str = "template"
    client_id: str = "template"
    client_secret: SecretStr = SecretStr("template-secret")
    audience: str | None = None
    algorithms: tuple[str, ...] = ("RS256",)
    timeout_seconds: float = Field(default=5.0, gt=0)

    @property
    def issuer(self) -> str:
        return f"{self.base_url.rstrip('/')}/realms/{self.realm}"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/certs"

    @property
    def authorization_url(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/auth"

    @property
    def token_url(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/token"

    @property
    def userinfo_url(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/userinfo"

    @property
    def logout_url(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/logout"


class SessionSettings(BaseModel):
    """Configuration for signed browser session cookies."""

    secret_key: SecretStr = SecretStr("development-session-secret")
    cookie_name: str = "template_session"
    state_cookie_name: str = "template_oauth_state"
    max_age_seconds: int = Field(default=28800, ge=60)
    secure: bool = False
    same_site: Literal["lax", "strict", "none"] = "lax"


class Settings(BaseSettings):
    env: str = "development"
    name: str = "app"
    version: str = "0.1.0"
    debug: bool = False
    api_host: str = "localhost"
    api_port: int = 8002
    htmx_host: str = "localhost"
    htmx_port: int = 8034
    mcp_host: str = "localhost"
    mcp_port: int = 8035
    worker_poll_interval: int = Field(default=3, ge=1)
    worker_batch_limit: int = Field(default=100, ge=1)

    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    outbox: OutboxSettings = Field(default_factory=OutboxSettings)
    keycloak: KeycloakSettings = Field(default_factory=KeycloakSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
