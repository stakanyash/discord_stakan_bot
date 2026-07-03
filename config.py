"""Конфигурация бота — загрузка переменных окружения и константы."""

import os
from dotenv import load_dotenv

load_dotenv()

# Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MUTE_ROLE_ID = int(os.getenv("MUTE_ROLE_ID"))
YOUR_ADMIN_ROLE_ID = int(os.getenv("YOUR_ADMIN_ROLE_ID"))
NOTIFICATION_CHANNEL_ID = int(os.getenv("NOTIFICATION_CHANNEL_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
YT_SUBSCRIBER_ROLE_ID = int(os.getenv("YT_SUBSCRIBER_ROLE_ID"))
SEC_YT_SUBSCRIBER_ROLE_ID = int(os.getenv("SEC_YT_SUBSCRIBER_ROLE_ID"))
USER_ID = int(os.getenv("USER_ID"))
MODERATOR_ROLE_ID = int(os.getenv("MODERATOR_ROLE_ID"))
ANTISPAM_CHANNEL_ID = int(os.getenv("ANTISPAM_CHANNEL_ID"))
GUILD_ID = int(os.getenv("GUILD_ID"))

# YouTube
YOUTUBE_API_KEYS = [k.strip('"') for k in os.getenv("YOUTUBE_API_KEYS").split(',')]
YOUTUBE_CHANNEL_ID_1 = os.getenv("YOUTUBE_CHANNEL_ID_1")
YOUTUBE_CHANNEL_ID_2 = os.getenv("YOUTUBE_CHANNEL_ID_2")

# Anti-spam
SPAM_TIME_WINDOW = int(os.getenv("SPAM_TIME_WINDOW", "120"))
SPAM_CHANNELS_THRESHOLD = int(os.getenv("SPAM_CHANNELS_THRESHOLD", "3"))
SPAM_ALERT_COOLDOWN = 300
NEW_ACCOUNT_DAYS_THRESHOLD = int(os.getenv("NEW_ACCOUNT_DAYS_THRESHOLD", "14"))

# Database
DB_FILE = os.getenv("DB_FILE", "bot_data.db")
