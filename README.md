# Telegram Channel Search Bot

This project is a Python Telegram bot for group chats. When a member sends a plain-text name, the bot searches the indexed text of every readable post in a configured Telegram channel and replies with links to matching posts.

The project uses `python-telegram-bot` for the Bot API update loop and Telethon for reading channel history. A **Telethon user session** is intentional: the Bot API is designed for bot interaction, while Telethon exposes the Telegram client API needed to iterate through a channel's message history using `iter_messages` [1] [2].

## Features

The bot performs a complete channel sync at startup, stores the searchable index in JSON, periodically refreshes the index, and adds new channel posts as they arrive. Searches are case-insensitive and punctuation-insensitive. Unicode compatibility normalization and accent removal are also applied before comparison, so examples such as `hello`, `h.e.l.l.o`, and `【hello】` are treated as the same searchable base name. When no match is found, it replies with `Movie မတွေ့သေးပါ။ Admin မှ ရှာပီးတင်ပေးပါ့မယ်` and attempts to pin that reply so administrators can review requested movies.

The default behavior is intentionally conservative: commands are ignored, queries shorter than two normalized characters are ignored, and at most ten matching links are returned. Every setting can be changed through environment variables.

## Project files

| File | Purpose |
|---|---|
| `bot.py` | Main bot, Telethon indexer, normalizer, cache, and group handler. |
| `generate_session.py` | Local helper for generating a Telethon `StringSession`. |
| `requirements.txt` | Pinned Python dependencies. |
| `Procfile` | Render worker command. |
| `render.yaml` | Optional Render Blueprint configuration. |
| `.env.example` | Configuration template. |
| `README.md` | Setup and deployment instructions. |
| `.gitignore` | Prevents secrets, sessions, caches, and Python artifacts from being committed. |

## Telegram credentials and permissions

Create the bot with [@BotFather](https://t.me/BotFather) and copy its token into `BOT_TOKEN`. Then obtain `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org). These credentials belong to the Telegram client API and are separate from the bot token.

The Telethon account used to generate `TELETHON_SESSION` must be able to open the configured channel. For a private channel, that account must be a member. The bot itself must be added to the group where users will search. To receive ordinary, non-command group messages, disable the bot's privacy mode in @BotFather with `/setprivacy`, or make the bot an administrator in the group. Telegram may also require the bot to have permission to send messages. To pin not-found replies, make the bot a group administrator with permission to pin messages; if that permission is unavailable, the bot still sends the reply and logs the pinning failure.

> **Security warning:** `TELETHON_SESSION`, `API_HASH`, and `BOT_TOKEN` are secrets. Do not commit them, paste them into public issue trackers, or place them in source code. Revoke and regenerate credentials if they are exposed.

## Local setup

Use Python 3.11 or newer. From this directory, create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Copy the configuration template and fill in the values:

```bash
cp .env.example .env
```

Generate the Telethon session locally. The helper asks for your Telegram API credentials and the login code sent by Telegram:

```bash
python generate_session.py
```

Copy the printed value into `.env` as `TELETHON_SESSION`. The generated session is used for the channel-reading client, so the bot can run on Render without an interactive login prompt.

Run the bot locally with:

```bash
set -a; . ./.env; set +a
python bot.py
```

The first startup performs a full history scan. The time required depends on the number of channel posts and Telegram rate limits. The JSON cache is recreated automatically if it is missing or invalid.

## Configuration

| Variable | Required | Description |
|---|---:|---|
| `BOT_TOKEN` | Yes | Token created by @BotFather. |
| `API_ID` | Yes | Numeric Telegram client API ID. |
| `API_HASH` | Yes | Telegram client API hash. |
| `TELETHON_SESSION` | Yes | String session generated locally by `generate_session.py`. |
| `CHANNEL_ID` | Yes | Numeric channel ID such as `-100123...`, or a public username. |
| `CACHE_FILE` | No | JSON cache path; defaults to `data/channel_posts.json`. |
| `REFRESH_INTERVAL_SECONDS` | No | Full refresh interval; defaults to 900 seconds. |
| `MAX_RESULTS` | No | Maximum links per reply, capped at 50; defaults to 10. |
| `MIN_QUERY_LENGTH` | No | Minimum normalized query length; defaults to 2. |
| `LOG_LEVEL` | No | Python logging level; defaults to `INFO`. |

For private channels, use the numeric `CHANNEL_ID`. A public username can be written as `@channel_username` or without the `@` prefix.

## Deploying to Render

Create a new **Background Worker** in Render from this repository. Render will install dependencies with `pip install -r requirements.txt` and run `python bot.py`; these commands are also declared in `Procfile` and `render.yaml` [3]. Add the required secret environment variables in the Render dashboard:

```text
BOT_TOKEN
API_ID
API_HASH
TELETHON_SESSION
CHANNEL_ID
```

You can either configure the optional variables manually or use the defaults from `render.yaml`. Do not commit a populated `.env` file.

Render's default filesystem is suitable because the bot performs a startup sync, but a cache written there is not intended to be durable across every redeploy. If preserving the cache matters, attach a Render persistent disk, uncomment the disk block in `render.yaml`, and set `CACHE_FILE=/var/data/channel_posts.json`. The bot remains correct without a preserved cache; it simply rebuilds the index on startup.

After deployment, inspect the worker logs for `Full sync completed` and `Bot is running`. Add the bot to the target group, disable privacy mode if needed, and send a test name that occurs in a channel post.

## Matching behavior

The normalizer applies Unicode NFKC/NFKD normalization, case folding, accent removal, and removal of all non-alphanumeric characters. Matching is substring-based against the normalized full post text. For example:

| Group query | Channel text | Result |
|---|---|---|
| `hello` | `h.e.l.l.o` | Match |
| `hello` | `【hello】` | Match |
| `cafe` | `Café` | Match |
| `alpha beta` | `alpha-beta` | Match, because both values normalize to `alphabeta`. |

## Operational notes

The index stores post text and links, not media files. Posts without text or captions are skipped because there is no searchable title/text. If a channel post is edited, the next periodic full refresh updates its cached text. If a post is deleted, the next full refresh removes it from the index.

The Telethon account should be dedicated to this automation where practical. Telegram rate limits can affect very large channel scans; the client is configured with bounded retries and automatic handling for shorter flood waits. Keep the Render worker running as a single instance to avoid duplicate polling and unnecessary Telegram sessions.

## References

[1]: https://docs.telethon.dev/en/stable/modules/client.html "Telethon TelegramClient documentation"

[2]: https://core.telegram.org/bots/api "Telegram Bot API documentation"

[3]: https://render.com/docs/background-workers "Render Background Workers documentation"
