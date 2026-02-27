# "stakanyasher" Discord server bot

This bot is a multifunctional Discord bot featuring moderation tools, logging, slowmode control, anti-spam protection, and YouTube API integration.
It uses SQLite for persistent storage and is designed to run as a single-file bot.

Created for using on my Discord server.

---

## Features

- Moderation commands:

  - warn
  - mute
  - unmute
  - kick
  - ban (with optional message deletion)
- Anti-spam filter
- Custom slowmode system with super-admin bypass
- Action logging
- SQLite database
- Embed-based notifications
- Random response utilities
- YouTube API integration

---

## Requirements

- Python 3.11 or newer
- pip

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/stakanyash/discord_stakan_bot.git
cd discord_stakan_bot
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # Linux
venv\Scripts\activate     # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## requirements.txt

Make sure your `requirements.txt` contains:

```
discord.py
python-dotenv
google-api-python-client
```

---

## Environment Configuration

This repository includes an `env_example` file.

1. Copy it:

```bash
cp env_example .env
```

2. Edit `.env` and replace all placeholder values.

---

### Environment Variables Overview

#### Main

- `DISCORD_TOKEN` — Discord bot token
- `GUILD_ID` — Target server ID

#### Roles

- `MUTE_ROLE_ID`
- `YOUR_ADMIN_ROLE_ID`
- `MODERATOR_ROLE_ID`
- `YT_SUBSCRIBER_ROLE_ID`
- `SEC_YT_SUBSCRIBER_ROLE_ID`

#### Channels

- `LOG_CHANNEL_ID`
- `NOTIFICATION_CHANNEL_ID`
- `ANTISPAM_CHANNEL_ID`

#### YouTube

- `YOUTUBE_API_KEYS` — Comma-separated API keys
- `YOUTUBE_CHANNEL_ID_1`
- `YOUTUBE_CHANNEL_ID_2`

#### Other

- `USER_ID` — Main administrator user ID
- `DB_FILE` — SQLite database file name

#### Anti-spam Settings

- `SPAM_TIME_WINDOW` — Time window in seconds
- `SPAM_CHANNELS_THRESHOLD` — Number of channels triggering spam detection

---

## Running the Bot

```bash
python bot.py
```

---

## Project Structure

```
discord_stakan_bot/
│
├── bot.py
├── randomlist.py
├── requirements.txt
├── env_example
├── .env
└── README.md
```

---

## Database

The SQLite database file is created automatically on first launch.
The file name is defined by the `DB_FILE` environment variable.

---

## Required Discord Permissions

The bot must have:

- Manage Messages
- Manage Roles
- Ban Members
- Kick Members
- Read Message History
- Send Messages
- Embed Links

The bot role must be placed above the roles it needs to manage.

---

## Notes

- Make sure privileged intents are enabled in the Discord Developer Portal.
- If roles are not assigned properly, check role hierarchy.
- If YouTube integration stops working, verify your API keys and quota usage.
