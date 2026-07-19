import os
from dataclasses import dataclass

# Load .env file from project root
_env_loaded = False
def _ensure_env_loaded():
    global _env_loaded
    if _env_loaded:
        return
    env_paths = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]
    for env_path in env_paths:
        if os.path.isfile(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key and not os.environ.get(key):
                        os.environ[key] = val
            break
    _env_loaded = True


@dataclass
class Settings:
    host: str = "0.0.0.0"
    port: int = 8080
    gitlab_url: str = "http://gitlab:80"
    gitlab_api_token: str = ""
    webhook_secret: str = ""
    engines_secrets_enabled: bool = True
    engines_sast_enabled: bool = True
    engines_iac_enabled: bool = True
    engines_best_practice_enabled: bool = True
    database_url: str = "sqlite+aiosqlite:///./data/guard.db"
    work_dir: str = "/tmp/pr-codeguard"
    ai_enabled: bool = False
    ai_api_key: str = ""
    ai_api_base: str = "https://api.deepseek.com"
    ai_model: str = "deepseek-v4-flash"
    ai_max_tokens: int = 1024
    ai_request_timeout: int = 60
    knowledge_enabled: bool = True
    knowledge_db_path: str = "./data/knowledge.db"
    chroma_persist_dir: str = "./data/chroma"
    auto_discovery_enabled: bool = True

    # Alert / Notification settings
    alert_enabled: bool = True
    alert_severity_threshold: str = "critical"
    alert_dingtalk_webhook: str = ""
    alert_dingtalk_secret: str = ""
    alert_slack_webhook: str = ""
    alert_smtp_host: str = ""
    alert_smtp_port: int = 587
    alert_smtp_user: str = ""
    alert_smtp_password: str = ""
    alert_smtp_use_tls: bool = True
    alert_email_from: str = ""
    alert_email_to: list[str] | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        _ensure_env_loaded()
        return cls(
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8080")),
            gitlab_url=os.getenv("GITLAB_URL", "http://gitlab:80"),
            gitlab_api_token=os.getenv("GITLAB_API_TOKEN", ""),
            webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
            engines_secrets_enabled=os.getenv("ENGINES_SECRETS_ENABLED", "true").lower() == "true",
            engines_sast_enabled=os.getenv("ENGINES_SAST_ENABLED", "true").lower() == "true",
            engines_iac_enabled=os.getenv("ENGINES_IAC_ENABLED", "true").lower() == "true",
            engines_best_practice_enabled=os.getenv("ENGINES_BEST_PRACTICE_ENABLED", "true").lower() == "true",
            database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/guard.db"),
            work_dir=os.getenv("WORK_DIR", "/tmp/pr-codeguard"),
            ai_enabled=os.getenv("AI_ENABLED", "false").lower() == "true",
            ai_api_key=os.getenv("AI_API_KEY", ""),
            ai_api_base=os.getenv("AI_API_BASE", "https://api.deepseek.com"),
            ai_model=os.getenv("AI_MODEL", "deepseek-v4-flash"),
            ai_max_tokens=int(os.getenv("AI_MAX_TOKENS", "1024")),
            ai_request_timeout=int(os.getenv("AI_REQUEST_TIMEOUT", "60")),
            knowledge_enabled=os.getenv("KNOWLEDGE_ENABLED", "true").lower() in ("true", "1"),
            knowledge_db_path=os.getenv("KNOWLEDGE_DB_PATH", "./data/knowledge.db"),
            chroma_persist_dir=os.getenv("CHROMA_PERSIST_DIR", "./data/chroma"),
            auto_discovery_enabled=os.getenv("AUTO_DISCOVERY_ENABLED", "true").lower() in ("true", "1"),
            alert_enabled=os.getenv("ALERT_ENABLED", "true").lower() in ("true", "1"),
            alert_severity_threshold=os.getenv("ALERT_SEVERITY_THRESHOLD", "critical"),
            alert_dingtalk_webhook=os.getenv("ALERT_DINGTALK_WEBHOOK", ""),
            alert_dingtalk_secret=os.getenv("ALERT_DINGTALK_SECRET", ""),
            alert_slack_webhook=os.getenv("ALERT_SLACK_WEBHOOK", ""),
            alert_smtp_host=os.getenv("ALERT_SMTP_HOST", ""),
            alert_smtp_port=int(os.getenv("ALERT_SMTP_PORT", "587")),
            alert_smtp_user=os.getenv("ALERT_SMTP_USER", ""),
            alert_smtp_password=os.getenv("ALERT_SMTP_PASSWORD", ""),
            alert_smtp_use_tls=os.getenv("ALERT_SMTP_USE_TLS", "true").lower() in ("true", "1"),
            alert_email_from=os.getenv("ALERT_EMAIL_FROM", ""),
            alert_email_to=os.getenv("ALERT_EMAIL_TO", "").split(",") if os.getenv("ALERT_EMAIL_TO") else [],
        )


settings = Settings.from_env()
