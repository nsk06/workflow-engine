from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:////data/workflow.db"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    auth_disabled: bool = False
    jwt_secret: str = "workflow-demo-secret-change-in-prod"
    jwt_expire_hours: int = 24
    # username:password pairs, comma-separated
    demo_users: str = "demo:demo,alice:alice"

    otel_exporter_endpoint: str = "http://otel-collector.observability.svc.cluster.local:4317"
    otel_enabled: bool = True

    worker_poll_interval_ms: int = 200
    worker_lease_seconds: int = 60
    worker_id: str = "worker-1"
    worker_metrics_port: int = 0

    log_level: str = "INFO"

    def user_credentials(self) -> dict[str, str]:
        users: dict[str, str] = {}
        for pair in self.demo_users.split(","):
            pair = pair.strip()
            if ":" in pair:
                username, password = pair.split(":", 1)
                users[username.strip()] = password.strip()
        return users


settings = Settings()
