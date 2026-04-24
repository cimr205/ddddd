"""
Bulk email sender med multi-konto rotation.
Gratis muligheder:
  - Gmail App Password (smtp.gmail.com:587)  → 500 emails/dag
  - Brevo gratis tier (smtp-relay.brevo.com:587) → 300 emails/dag
  - Mailersend gratis tier (smtp.mailersend.net:587) → 100 emails/dag
"""
import asyncio
import itertools
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable, List, Optional

import aiosmtplib

from core.config import settings, SmtpAccount


class BulkEmailSender:
    # Sikker rate: 45s mellem emails per konto = ~80/time
    # Med 2 konti = ~160/time, 3 konti = ~240/time
    DELAY_SECONDS = 45

    def __init__(self):
        self._accounts = settings.smtp_accounts
        self._cycle = itertools.cycle(self._accounts) if self._accounts else None

    def has_accounts(self) -> bool:
        return bool(self._accounts)

    def _next(self) -> Optional[SmtpAccount]:
        return next(self._cycle) if self._cycle else None

    async def send_one(
        self,
        to_email: str,
        subject: str,
        body: str,
        from_name: str = "Lead System",
    ) -> bool:
        acc = self._next()
        if not acc:
            raise RuntimeError(
                "Ingen SMTP-konti konfigureret.\n"
                "Tilføj SMTP_ACCOUNTS til din .env fil.\n"
                "Se SETUP.md for Gmail-guide."
            )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{acc.user}>"
        msg["To"] = to_email

        plain = body
        html = "<html><body>" + body.replace("\n", "<br>") + "</body></html>"
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=acc.host,
            port=acc.port,
            username=acc.user,
            password=acc.password,
            start_tls=True,
            timeout=30,
        )
        return True

    async def send_bulk(
        self,
        emails: List[dict],
        from_name: str = "Lead System",
        on_sent: Optional[Callable] = None,
        on_failed: Optional[Callable] = None,
    ):
        for i, email in enumerate(emails):
            try:
                await self.send_one(
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

            if i < len(emails) - 1:
                await asyncio.sleep(self.DELAY_SECONDS)


sender = BulkEmailSender()
