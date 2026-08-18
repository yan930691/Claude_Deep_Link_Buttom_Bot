"""Telegram group bot that searches the history of a Telegram channel.

The bot uses python-telegram-bot for Bot API updates and Telethon with a
user-session string for reading channel history. A user session is required
because the Bot API does not expose arbitrary channel history search.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.error import TelegramError
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError


LOG = logging.getLogger(__name__)
load_dotenv()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


BOT_TOKEN = required_env("BOT_TOKEN")
API_ID = parse_int_env("API_ID", 0)
API_HASH = required_env("API_HASH")
TELETHON_SESSION = required_env("TELETHON_SESSION")
CHANNEL_ID_RAW = required_env("CHANNEL_ID")
CACHE_FILE = Path(os.getenv("CACHE_FILE", "data/channel_posts.json"))
REFRESH_INTERVAL = parse_int_env("REFRESH_INTERVAL_SECONDS", 900)
MAX_RESULTS = max(1, min(parse_int_env("MAX_RESULTS", 10), 50))
MIN_QUERY_LENGTH = max(1, parse_int_env("MIN_QUERY_LENGTH", 2))

if API_ID <= 0:
    raise RuntimeError("API_ID must be a positive integer")


@dataclass(slots=True)
class CachedPost:
    message_id: int
    date: str
    text: str
    normalized_text: str
    link: str


class PostIndex:
    """In-memory searchable index backed by a small JSON cache file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._posts: dict[int, CachedPost] = {}
        self._lock = asyncio.Lock()

    async def load(self) -> None:
        if not self.path.exists():
            LOG.info("No cache found at %s; a full channel sync will run", self.path)
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            posts = payload.get("posts", [])
            self._posts = {int(item["message_id"]): CachedPost(**item) for item in posts}
            LOG.info("Loaded %d posts from cache", len(self._posts))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            LOG.warning("Ignoring invalid cache at %s: %s", self.path, exc)
            self._posts = {}

    async def replace(self, posts: list[CachedPost]) -> None:
        async with self._lock:
            self._posts = {post.message_id: post for post in posts}
            await self._persist_locked()

    async def upsert(self, post: CachedPost) -> None:
        async with self._lock:
            self._posts[post.message_id] = post
            await self._persist_locked()

    async def search(self, normalized_query: str, limit: int) -> list[CachedPost]:
        async with self._lock:
            matches = [
                post for post in self._posts.values()
                if normalized_query in post.normalized_text
            ]
        matches.sort(key=lambda post: post.message_id, reverse=True)
        return matches[:limit]

    async def _persist_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "posts": [asdict(post) for post in sorted(self._posts.values(), key=lambda p: p.message_id)],
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)


def normalize_for_search(value: str) -> str:
    """Case-fold and remove formatting/punctuation while retaining letters/digits.

    NFKC handles compatibility forms such as full-width characters. Combining
    marks are removed so accents compare naturally, and all non-alphanumeric
    characters are discarded. Therefore ``h.e.l.l.o`` and ``【hello】`` both
    normalize to ``hello``.
    """
    normalized = unicodedata.normalize("NFKC", value).casefold()
    decomposed = unicodedata.normalize("NFKD", normalized)
    return "".join(char for char in decomposed if char.isalnum())


def channel_reference() -> int | str:
    raw = CHANNEL_ID_RAW
    if raw.startswith("-") or raw.isdigit():
        try:
            return int(raw)
        except ValueError:
            pass
    return raw if raw.startswith("@") else f"@{raw}"


def make_post_link(entity: Any, message_id: int) -> str:
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"
    channel_id = str(getattr(entity, "id", ""))
    return f"https://t.me/c/{channel_id}/{message_id}"


def message_text(message: Any) -> str:
    text = getattr(message, "message", None) or ""
    return text.strip()


class ChannelIndexer:
    def __init__(self, client: TelegramClient, index: PostIndex) -> None:
        self.client = client
        self.index = index
        self.entity: Any = None
        self.sync_lock = asyncio.Lock()

    async def full_sync(self) -> None:
        async with self.sync_lock:
            LOG.info("Starting full sync for channel %s", CHANNEL_ID_RAW)
            entity = await self.client.get_entity(channel_reference())
            posts: list[CachedPost] = []
            async for message in self.client.iter_messages(entity, reverse=True):
                text = message_text(message)
                if not text:
                    continue
                posts.append(CachedPost(
                    message_id=message.id,
                    date=message.date.isoformat() if message.date else "",
                    text=text,
                    normalized_text=normalize_for_search(text),
                    link=make_post_link(entity, message.id),
                ))
            self.entity = entity
            await self.index.replace(posts)
            LOG.info("Full sync completed: indexed %d text posts", len(posts))

    async def refresh_loop(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=REFRESH_INTERVAL)
            except asyncio.TimeoutError:
                try:
                    await self.full_sync()
                except Exception:
                    LOG.exception("Scheduled channel refresh failed")

    async def on_new_message(self, event: events.NewMessage.Event) -> None:
        message = event.message
        text = message_text(message)
        if not text:
            return
        entity = self.entity or await self.client.get_entity(channel_reference())
        await self.index.upsert(CachedPost(
            message_id=message.id,
            date=message.date.isoformat() if message.date else "",
            text=text,
            normalized_text=normalize_for_search(text),
            link=make_post_link(entity, message.id),
        ))


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    query = (message.text or message.caption or "").strip()
    if not query or query.startswith("/"):
        return
    normalized_query = normalize_for_search(query)
    if len(normalized_query) < MIN_QUERY_LENGTH:
        return

    index: PostIndex = context.application.bot_data["post_index"]
    matches = await index.search(normalized_query, MAX_RESULTS)
    if not matches:
        not_found_message = await message.reply_text(
            "Movie မတွေ့သေးပါ။ Admin မှ ရှာပီးတင်ပေးပါ့မယ်"
        )
        try:
            # Pin the bot's request notice so group admins can review it.
            # The bot must be an administrator with pin-message permission.
            await not_found_message.pin(disable_notification=True)
        except TelegramError as exc:
            LOG.warning(
                "Could not pin not-found message in chat %s; "
                "ensure the bot has pin-message permission: %s",
                chat.id,
                exc,
            )
        return

    lines = [f"Found {len(matches)} matching post(s):"]
    lines.extend(f"• {post.link}" for post in matches)
    await message.reply_text("\n".join(lines), disable_web_page_preview=True)


async def run() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    index = PostIndex(CACHE_FILE)
    await index.load()

    user_client = TelegramClient(
        StringSession(TELETHON_SESSION),
        API_ID,
        API_HASH,
        request_retries=5,
        connection_retries=5,
        flood_sleep_threshold=60,
    )
    await user_client.start()
    indexer = ChannelIndexer(user_client, index)
    await indexer.full_sync()
    user_client.add_event_handler(indexer.on_new_message, events.NewMessage(chats=indexer.entity))

    application = Application.builder().token(BOT_TOKEN).build()
    application.bot_data["post_index"] = index
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_message))

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop_event.set)
        except NotImplementedError:
            pass

    refresh_task = asyncio.create_task(indexer.refresh_loop(stop_event))
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    LOG.info("Bot is running")

    await stop_event.wait()
    LOG.info("Shutdown requested")
    await application.updater.stop()
    await application.stop()
    await application.shutdown()
    refresh_task.cancel()
    await user_client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except FloodWaitError as exc:
        LOG.error("Telegram requested a flood-wait of %s seconds", exc.seconds)
        raise
