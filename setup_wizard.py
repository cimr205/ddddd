#!/usr/bin/env python3
"""
Interaktiv setup-guide – konfigurerer systemet 100% gratis.
Kør: python setup_wizard.py
"""
import os
import sys
import subprocess
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich import print as rprint
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "rich", "-q"])
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm

console = Console()


def header():
    console.print(Panel.fit(
        "[bold cyan]Lead Generation System – Setup Wizard[/bold cyan]\n"
        "[dim]Konfigurerer dit system 100% gratis[/dim]",
        border_style="cyan"
    ))
    console.print()


def section(title: str):
    console.print(f"\n[bold yellow]━━ {title} ━━[/bold yellow]")


def success(msg: str):
    console.print(f"[green]✓[/green] {msg}")


def info(msg: str):
    console.print(f"[cyan]ℹ[/cyan] {msg}")


def warn(msg: str):
    console.print(f"[yellow]⚠[/yellow] {msg}")


def setup_ai() -> dict:
    section("AI Email Writing (vælg én gratis mulighed)")

    console.print("""
[bold]Mulighed 1: Groq API[/bold] [green](Anbefalet)[/green]
  • 100% gratis – kun email-signup kræves
  • Ingen kreditkort
  • Hurtigt: Llama 3 model
  • Signup: [link]https://console.groq.com[/link]

[bold]Mulighed 2: Ollama (lokal AI)[/bold]
  • Kører på din computer – helt offline
  • Ingen signup, ingen internet til AI
  • Kræver ca. 4 GB RAM
  • Installer: [link]https://ollama.ai[/link]

[bold]Mulighed 3: Smart templates[/bold]
  • Virker altid uden noget
  • Professionelle email-skabeloner
  • Ingen AI, men fungerer fint
""")

    choice = Prompt.ask("Vælg mulighed", choices=["1", "2", "3"], default="3")

    config = {}

    if choice == "1":
        console.print("\n[dim]Gå til console.groq.com → API Keys → Create API Key[/dim]")
        key = Prompt.ask("Indsæt din Groq API key (gratis)")
        if key.startswith("gsk_"):
            config["GROQ_API_KEY"] = key
            success("Groq API key gemt")
        else:
            warn("Nøglen ser ikke rigtig ud – tjek at den starter med 'gsk_'")
            config["GROQ_API_KEY"] = key

    elif choice == "2":
        console.print("\n[dim]Installer Ollama: curl -fsSL https://ollama.ai/install.sh | sh[/dim]")
        console.print("[dim]Pull model: ollama pull llama3[/dim]\n")
        url = Prompt.ask("Ollama URL", default="http://localhost:11434")
        model = Prompt.ask("Model navn", default="llama3")
        config["OLLAMA_ENABLED"] = "true"
        config["OLLAMA_URL"] = url
        config["OLLAMA_MODEL"] = model
        success("Ollama konfigureret")

    else:
        success("Bruger smart templates – ingen AI-key nødvendig")

    return config


def setup_smtp() -> dict:
    section("Email Sending (vælg gratis SMTP)")

    console.print("""
[bold]Mulighed 1: Gmail[/bold] [green](Anbefalet)[/green]
  • 500 emails/dag gratis
  • Kræver: Gmail-konto + App Password
  • Guide: Google Account → Security → 2-Step Verification → App Passwords

[bold]Mulighed 2: Brevo (sendinblue)[/bold]
  • 300 emails/dag gratis
  • Signup: [link]https://app.brevo.com[/link]
  • Gå til: SMTP & API → SMTP

[bold]Mulighed 3: Mailersend[/bold]
  • 100 emails/dag gratis
  • Signup: [link]https://app.mailersend.com[/link]

[bold]Spring over[/bold] – kan konfigureres senere i .env
""")

    choice = Prompt.ask("Vælg mulighed", choices=["1", "2", "3", "skip"], default="skip")
    config = {}
    accounts = []

    if choice == "1":
        console.print("\n[bold]Gmail App Password guide:[/bold]")
        console.print("1. Gå til [link]https://myaccount.google.com/security[/link]")
        console.print("2. Slå '2-Step Verification' til")
        console.print("3. Søg efter 'App passwords' på samme side")
        console.print("4. Opret ny → vælg 'Mail' → kopiér den 16-tegns kode\n")

        while True:
            email = Prompt.ask("Gmail adresse")
            password = Prompt.ask("App Password (16 tegn, ingen mellemrum)")
            password = password.replace(" ", "")
            accounts.append(f"{email}:{password}@smtp.gmail.com:587")
            success(f"Konto tilføjet: {email}")

            if not Confirm.ask("Tilføj endnu en Gmail-konto? (flere = højere volumen)", default=False):
                break

    elif choice == "2":
        console.print("\n[dim]Gå til app.brevo.com → SMTP & API → SMTP[/dim]")
        smtp_user = Prompt.ask("Brevo SMTP login (din email)")
        smtp_key = Prompt.ask("Brevo SMTP key")
        accounts.append(f"{smtp_user}:{smtp_key}@smtp-relay.brevo.com:587")
        success("Brevo konfigureret")

    elif choice == "3":
        console.print("\n[dim]Gå til app.mailersend.com → Email → Domains → SMTP[/dim]")
        smtp_user = Prompt.ask("Mailersend SMTP bruger")
        smtp_pass = Prompt.ask("Mailersend SMTP password")
        accounts.append(f"{smtp_user}:{smtp_pass}@smtp.mailersend.net:587")
        success("Mailersend konfigureret")

    if accounts:
        config["SMTP_ACCOUNTS"] = ",".join(accounts)

    return config


def setup_playwright():
    section("Browser til Scraping (Playwright Chromium)")
    info("Playwright bruger en lokal Chromium-browser til at tilgå Google Maps.")
    info("Browseren downloader sig selv – kun internet-forbindelsen på din maskine bruges.")
    console.print()

    if Confirm.ask("Installer Playwright Chromium nu?", default=True):
        console.print("[dim]Downloader Chromium (~120 MB)...[/dim]")
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=False,
        )
        if result.returncode == 0:
            success("Chromium installeret – klar til scraping")
        else:
            warn("Fejl under installation – prøv manuelt: playwright install chromium")
    else:
        warn("Husk at køre: playwright install chromium")


def write_env(config: dict):
    section("Gemmer konfiguration")

    env_path = Path(".env")
    lines = []

    # Read existing if any
    existing = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    existing.update(config)

    for k, v in existing.items():
        lines.append(f"{k}={v}")

    env_path.write_text("\n".join(lines) + "\n")
    success(f".env gemt med {len(config)} indstillinger")


def verify_install():
    section("Tjekker installation")
    try:
        import fastapi
        success("FastAPI ✓")
    except ImportError:
        warn("FastAPI mangler – kør: pip install -r requirements.txt")

    try:
        import playwright
        success("Playwright ✓")
    except ImportError:
        warn("Playwright mangler – kør: pip install playwright")

    try:
        import groq
        success("Groq SDK ✓")
    except ImportError:
        warn("Groq SDK mangler – kør: pip install groq")


def main():
    header()

    # Check requirements installed
    verify_install()

    config = {}

    # AI
    ai_config = setup_ai()
    config.update(ai_config)

    # SMTP
    smtp_config = setup_smtp()
    config.update(smtp_config)

    # Playwright
    setup_playwright()

    # Write .env
    write_env(config)

    # Done
    console.print()
    console.print(Panel.fit(
        "[bold green]Setup komplet![/bold green]\n\n"
        "Start systemet med:\n"
        "[bold cyan]python main.py[/bold cyan]\n\n"
        "Åbn dashboard:\n"
        "[bold cyan]http://localhost:8000[/bold cyan]",
        border_style="green"
    ))


if __name__ == "__main__":
    main()
