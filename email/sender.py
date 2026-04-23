import asyncio
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional
from core.config import settings, SmtpAccount
import itertools


class BulkEmailSender:
    RATE_LIMIT_PER_HOUR = 80
    DELAY_BETWEEN_EMAILS = 45  # seconds – stay safe from spam filters

    def __init__(self):
        self._accounts = settings.smtp_accounts
        self._account_cycle = itertools.cycle(self._accounts) if self._accounts else None
        self._sent_counts: dict = {}

    def _next_account(self) -> Optional[SmtpAccount]:
        if not self._account_cycle:
            return None
        return next(self._account_cycle)

    async def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        from_name: str = "Lead System",
        reply_to: str = "",
    ) -> bool:
        account = self._next_account()
        if not account:
            raise RuntimeError("No SMTP accounts configured. Add SMTP_ACCOUNTS to .env")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{account.user}>"
        msg["To"] = to_email
        if reply_to:
            msg["Reply-To"] = reply_to

        html_body = body.replace("\n", "<br>")
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(f"<html><body><p>{html_body}</p></body></html>", "html"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=account.host,
                port=account.port,
                username=account.user,
                password=account.password,
                start_tls=True,
                timeout=30,
            )
            return True
        except Exception as e:
            raise RuntimeError(f"SMTP error ({account.user}): {e}")

    async def send_bulk(
        self,
        emails: List[dict],
        from_name: str = "Lead System",
        on_sent=None,
        on_failed=None,
    ):
        for i, email in enumerate(emails):
            try:
                await self.send(
                    to_email=email["to"],
                    subject=email["subject"],
                    body=email["body"],
                    from_name=from_name,
                )
                if on_sent:
                    await on_sent(email, i)
            except Exception as e:
                if on_failed:
                    await on_failed(email, str(e))

            # Throttle to avoid spam filters and per-hour limits
            if i < len(emails) - 1:
                await asyncio.sleep(self.DELAY_BETWEEN_EMAILS)


sender = BulkEmailSender()
