"""Telegram alerts for bot activity.

The server owner creates one Telegram bot (via @BotFather) and sets TELEGRAM_BOT_TOKEN. Each user
links their own chat from the Bots page, so alerts for a user's bots only go to that user.
Alerts are queued on the database session and sent after the change is committed, so a trade
that gets rolled back never produces a message.
"""
import logging
import os
import secrets

import httpx
from sqlalchemy.orm import Session

from . import models

log = logging.getLogger("moneyfx.alerts")


class TelegramError(Exception):
    pass


class Telegram:
    def __init__(self, token: str, transport=None, base_url: str = "https://api.telegram.org"):
        self.http = httpx.Client(base_url=f"{base_url}/bot{token}", timeout=10, transport=transport)
        self._username: str | None = None

    def _call(self, method: str, **params) -> dict | list:
        try:
            r = self.http.post(f"/{method}", json=params)
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise TelegramError(f"Could not reach Telegram: {e}") from e
        if not data.get("ok"):
            raise TelegramError(f"Telegram: {data.get('description', r.status_code)}")
        return data["result"]

    def username(self) -> str:
        if self._username is None:
            self._username = self._call("getMe")["username"]
        return self._username

    def send(self, chat_id: str, text: str):
        self._call("sendMessage", chat_id=chat_id, text=text[:4000], disable_web_page_preview=True)

    def find_chat(self, code: str) -> str | None:
        """The chat that sent "/start <code>" to the bot (Telegram keeps updates for 24 hours)."""
        for u in reversed(self._call("getUpdates", allowed_updates=["message"])):
            msg = u.get("message") or {}
            if msg.get("text", "").strip() == f"/start {code}":
                return str(msg["chat"]["id"])
        return None


_client: Telegram | None = None


def telegram() -> Telegram | None:
    global _client
    if _client is None and os.getenv("TELEGRAM_BOT_TOKEN"):
        _client = Telegram(os.environ["TELEGRAM_BOT_TOKEN"], base_url=os.getenv("TELEGRAM_API_URL", "https://api.telegram.org"))
    return _client


def set_telegram(client: Telegram | None):
    """Used by tests to inject a client with a fake transport."""
    global _client
    _client = client


def new_link_code() -> str:
    return "mfx" + secrets.token_hex(6)


def notify(db: Session, bot: models.Bot, text: str):
    db.info.setdefault("alerts", []).append((bot.account_id, f"{bot.name} · {bot.symbol}\n{text}"))


def discard(db: Session):
    db.info.pop("alerts", None)


def send_pending(db: Session):
    """Send the alerts queued on this session. Call it right after a commit."""
    pending = db.info.pop("alerts", [])
    client = telegram()
    if not pending or client is None:
        return
    chats = {}
    for account_id, text in pending:
        if account_id not in chats:
            account = db.get(models.Account, account_id)
            chats[account_id] = account.telegram_chat_id if account else None
        if chats[account_id]:
            try:
                client.send(chats[account_id], text)
            except TelegramError as e:
                log.warning("telegram alert failed: %s", e)
