import os
from typing import List, Optional
from pydantic_settings import BaseSettings


class SmtpAccount:
    """
    Format i .env:
      user@gmail.com:app_password@smtp.gmail.com:587
    Flere konti adskilles med komma.
    """
    def __init__(self, raw: str):
        raw = raw.strip()
        at_idx = raw.index("@")
        user = raw[:at_idx]
        rest = raw[at_idx + 1:]
        # rest = "password@smtp.host:port"  or "password@smtp.host"
        at2 = rest.index("@")
        password = rest[:at2]
        host_port = rest[at2 + 1:]
        if ":" in host_port:
            host, port_str = host_port.rsplit(":", 1)
            port = int(port_str)
        else:
            host = host_port
            port = 587
        self.user = user
        self.password = password
        self.host = host
        self.port = port

    def __repr__(self):
        return f"SmtpAccount({self.user} @ {self.host}:{self.port})"


class Settings(BaseSettings):
    # ── AI providers (all free, choose one) ──────────────────────────────────
    # Groq: gratis signup på console.groq.com – hurtigst
    groq_api_key: str = ""
    groq_model: str = "llama3-8b-8192"

    # Ollama: lokal AI, ingen signup – kør: ollama pull llama3
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    ollama_enabled: bool = False

    # ── Email sending ─────────────────────────────────────────────────────────
    # Format: user@gmail.com:app_password@smtp.gmail.com:587
    # Gmail guide: https://myaccount.google.com → Security → App Passwords
    # Brevo guide: app.brevo.com → SMTP & API → SMTP
    smtp_accounts_raw: str = ""

    # ── Email tracking ────────────────────────────────────────────────────────
    # Offentlig URL til dit system (for åbnings-tracking, valgfri)
    public_url: str = ""

    # ── Telegram Bot ──────────────────────────────────────────────────────────
    # Opret via @BotFather på Telegram: /newbot  → kopier token herind
    telegram_bot_token: str = ""
    # Din personlige chat ID – skriv /start til botten for at se den automatisk
    telegram_chat_id: str = ""

    # ── App ───────────────────────────────────────────────────────────────────
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

    @property
    def ai_provider(self) -> str:
        if self.groq_api_key:
            return "groq"
        if self.ollama_enabled:
            return "ollama"
        return "template"


settings = Settings()
