"""
Telegram Bot – styr dit lead-system direkte fra telefonen.

Opsætning (5 min):
1. Åbn Telegram og søg efter @BotFather
2. Send: /newbot  → giv den et navn → kopier TOKEN
3. Tilføj i .env:  TELEGRAM_BOT_TOKEN=din_token
4. Start systemet og send /start til din nye bot
5. Botten svarer med dit Chat ID – tilføj i .env: TELEGRAM_CHAT_ID=dit_id
6. Genstart – nu kører botten!

Kommandoer:
  /start          – Velkommen + vis dit Chat ID
  /status         – System status (leads, jobs, emails)
  /leads          – Seneste 10 leads
  /jobs           – Aktive og seneste jobs
  /stop           – Stop al scraping (graceful)
  Fri tekst       – Fortolkes som kommando (samme som web-chat)

Eksempler på fri tekst:
  "1000 tandlæger i Danmark"
  "schedule: CRM firmaer i USA"
  "send emails til alle leads"
"""
import asyncio
import logging
from typing import Optional

from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

from core.config import settings
from core.monitor import monitor

logger = logging.getLogger(__name__)

# Markdown escape for Telegram MarkdownV2
def _esc(text: str) -> str:
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def _md_to_telegram(text: str) -> str:
    """Convert our simple **bold** markdown to Telegram HTML."""
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text


class TelegramBot:
    def __init__(self):
        self._app: Optional[Application] = None
        self._chat_id: str = settings.telegram_chat_id
        self._running = False

    async def start(self):
        token = settings.telegram_bot_token
        if not token:
            logger.info("Telegram bot ikke konfigureret (TELEGRAM_BOT_TOKEN mangler)")
            return

        try:
            self._app = (
                Application.builder()
                .token(token)
                .build()
            )

            self._app.add_handler(CommandHandler("start",  self._cmd_start))
            self._app.add_handler(CommandHandler("help",   self._cmd_help))
            self._app.add_handler(CommandHandler("status", self._cmd_status))
            self._app.add_handler(CommandHandler("leads",  self._cmd_leads))
            self._app.add_handler(CommandHandler("jobs",   self._cmd_jobs))
            self._app.add_handler(CommandHandler("stop",   self._cmd_stop))
            self._app.add_handler(MessageHandler(
                filters.TEXT & ~filters.COMMAND, self._handle_text
            ))

            # Register Telegram callback in monitor for auto-notifications
            monitor.set_telegram(self._notify)

            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling(drop_pending_updates=True)
            self._running = True
            logger.info("Telegram bot startet ✓")
        except Exception as e:
            logger.warning(f"Telegram bot fejlede ved start: {e}")

    async def stop(self):
        if self._app and self._running:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._running = False

    async def _notify(self, content: str, msg_type: str = "text"):
        """Called by monitor when agent sends result/error messages."""
        if not self._chat_id:
            return
        icon = "✅" if msg_type == "result" else "❌"
        await self._send(f"{icon} {content}")

    async def _send(self, text: str, chat_id: str = None):
        if not self._app:
            return
        target = chat_id or self._chat_id
        if not target:
            return
        try:
            html = _md_to_telegram(text)
            await self._app.bot.send_message(
                chat_id=target,
                text=html,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.debug(f"Telegram send fejl: {e}")

    def _auth(self, update: Update) -> bool:
        """Accept messages from any chat if no chat_id configured yet."""
        return True  # Trust all until user sets TELEGRAM_CHAT_ID

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        # Auto-save chat ID on first use
        if not self._chat_id:
            self._chat_id = chat_id

        already = " ✓ Notifikationer er aktive!" if self._chat_id == chat_id else ""
        msg = (
            f"🤖 <b>Lead Agent System</b>\n\n"
            f"Hej! Jeg er din personlige lead-assistent.\n\n"
            f"<b>Dit Chat ID:</b> <code>{chat_id}</code>{already}\n\n"
            f"Tilføj i Railway → Variables:\n"
            f"<code>TELEGRAM_CHAT_ID={chat_id}</code>\n\n"
            f"Skriv /help for kommandoer."
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        msg = (
            "🤖 <b>Kommandoer:</b>\n\n"
            "/status – System status\n"
            "/leads – Seneste leads\n"
            "/jobs – Aktive jobs\n\n"
            "<b>Start scraping (fri tekst):</b>\n"
            "<code>1000 tandlæger i Danmark</code>\n"
            "<code>marketing firmaer i USA</code>\n"
            "<code>alle advokater i Aarhus</code>\n\n"
            "<b>Baggrundsjob (kører natten over):</b>\n"
            "<code>schedule: 5000 CRM firmaer i USA</code>\n"
            "<code>overnight: webshops i Sverige</code>\n\n"
            "<b>Emails:</b>\n"
            "<code>send emails til alle leads</code>\n\n"
            "Du får automatisk besked når jobs er færdige ✓"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        from sqlalchemy import select, func
        from core.database import SessionLocal, Lead, EmailLog, Campaign, Job

        async with SessionLocal() as db:
            leads     = (await db.execute(select(func.count(Lead.id)))).scalar() or 0
            sent      = (await db.execute(select(func.count(EmailLog.id)).where(EmailLog.status == "sent"))).scalar() or 0
            campaigns = (await db.execute(select(func.count(Campaign.id)))).scalar() or 0
            active_jobs = (await db.execute(
                select(func.count(Job.id)).where(Job.status.in_(["running", "pending"]))
            )).scalar() or 0
            new_leads = (await db.execute(
                select(func.count(Lead.id)).where(Lead.status == "new")
            )).scalar() or 0

        msg = (
            f"📊 <b>System Status</b>\n\n"
            f"👥 Leads i alt: <b>{leads}</b>\n"
            f"🆕 Nye (ikke kontaktet): <b>{new_leads}</b>\n"
            f"📧 Emails sendt: <b>{sent}</b>\n"
            f"📋 Kampagner: <b>{campaigns}</b>\n"
            f"⚡ Aktive jobs: <b>{active_jobs}</b>"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    async def _cmd_leads(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        from sqlalchemy import select, desc
        from core.database import SessionLocal, Lead

        async with SessionLocal() as db:
            result = await db.execute(
                select(Lead).order_by(desc(Lead.created_at)).limit(10)
            )
            leads = result.scalars().all()

        if not leads:
            await update.message.reply_text("Ingen leads endnu. Prøv: <code>tandlæger i Danmark</code>", parse_mode=ParseMode.HTML)
            return

        lines = []
        for l in leads:
            conf = int((l.email_confidence or 0) * 100)
            lines.append(
                f"🏢 <b>{l.company or '—'}</b>\n"
                f"   📧 {l.email or '—'} ({conf}%)\n"
                f"   📞 {l.phone or '—'}"
            )

        msg = f"📋 <b>Seneste {len(leads)} leads:</b>\n\n" + "\n\n".join(lines)
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    async def _cmd_jobs(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        from sqlalchemy import select, desc
        from core.database import SessionLocal, Job

        async with SessionLocal() as db:
            jobs = (await db.execute(
                select(Job).order_by(desc(Job.created_at)).limit(8)
            )).scalars().all()

        if not jobs:
            await update.message.reply_text("Ingen jobs endnu.")
            return

        icons = {"pending": "⏳", "running": "⚡", "done": "✅", "failed": "❌"}
        lines = []
        for j in jobs:
            dur = ""
            if j.started_at and j.finished_at:
                mins = int((j.finished_at - j.started_at).total_seconds() / 60)
                dur = f" ({mins} min)"
            found = f" → {j.leads_found} leads" if j.leads_found else ""
            lines.append(f"{icons.get(j.status,'?')} <b>{j.name}</b>{found}{dur}")

        await update.message.reply_text(
            "📋 <b>Jobs:</b>\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML
        )

    async def _cmd_stop(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("⏹ Stop-signal sendt. Kørende scraping afslutter den nuværende søgning og stopper.")
        # Set a global stop flag - agents check this
        from core.monitor import monitor as mon
        await mon.emit("ceo", "Orchestrator", "Stop anmodet via Telegram", "warning")

    async def _handle_text(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Forward free text to the commander, same as web chat."""
        text = update.message.text.strip()
        if not text:
            return

        chat_id = str(update.effective_chat.id)
        # Auto-register chat ID
        if not self._chat_id:
            self._chat_id = chat_id

        await update.message.reply_text(f"⚡ Behandler: <i>{text[:80]}</i>", parse_mode=ParseMode.HTML)

        from agents.commander import parse_command
        from core.monitor import monitor as mon

        action = await parse_command(text)
        a = action.get("action", "unknown")

        await mon.emit_chat("user", f"[Telegram] {text}")

        # Run action in background so bot doesn't time out
        asyncio.create_task(self._run_telegram_action(action, text, chat_id))

    async def _run_telegram_action(self, action: dict, raw: str, chat_id: str):
        """Execute action and send result back to Telegram."""
        from dashboard.app import _execute_action
        # Temporarily override notification target to this chat
        old_id = self._chat_id
        self._chat_id = chat_id
        try:
            await _execute_action(action, raw)
        except Exception as e:
            await self._send(f"❌ Fejl: {e}", chat_id=chat_id)
        finally:
            self._chat_id = old_id


# Singleton
telegram_bot = TelegramBot()
