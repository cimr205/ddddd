import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import field_validator


class SmtpAccount:
    def __init__(self, raw: str):
        # Format: user@domain.com:password@smtp.host.com:port
        parts = raw.strip().split("@")
        self.user = parts[0]
        rest = parts[1].rsplit(":", 1)
        host_pass = rest[0].split(":", 1)
        self.password = host_pass[0]
        self.host = host_pass[1] if len(host_pass) > 1 else "smtp.gmail.com"
        self.port = int(rest[1]) if len(rest) > 1 else 587

    def __repr__(self):
        return f"SmtpAccount({self.user} @ {self.host}:{self.port})"


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    smtp_accounts_raw: str = ""
    hunter_api_key: str = ""
    scrapingbee_api_key: str = ""
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    database_url: str = "sqlite+aiosqlite:///data/leads.db"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def smtp_accounts(self) -> List[SmtpAccount]:
        if not self.smtp_accounts_raw:
            return []
        return [SmtpAccount(a) for a in self.smtp_accounts_raw.split(",") if a.strip()]


settings = Settings()
