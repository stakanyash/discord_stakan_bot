"""Антиспам: отслеживание сообщений и оповещения."""

import collections
from datetime import datetime, timedelta, timezone

import discord

from config import (
    ANTISPAM_CHANNEL_ID,
    YOUR_ADMIN_ROLE_ID,
    MODERATOR_ROLE_ID,
    SPAM_TIME_WINDOW,
    SPAM_CHANNELS_THRESHOLD,
    SPAM_ALERT_COOLDOWN,
    NEW_ACCOUNT_DAYS_THRESHOLD,
)
from embeds import LOG_COLORS, _utcnow


user_message_log: dict[int, collections.deque] = collections.defaultdict(
    lambda: collections.deque()
)
last_spam_alert: dict[int, datetime] = {}


async def send_spam_alert(
    user: discord.Member,
    reason: str,
    details: str,
    bot = None,
    ping_admins: bool = True,
    title: str = "Антиспам: подозрительная активность!",
    color: int = None,
):
    user_id = user.id
    now = _utcnow()
    last_alert = last_spam_alert.get(user_id)
    if last_alert and (now - last_alert).total_seconds() < SPAM_ALERT_COOLDOWN:
        return
    last_spam_alert[user_id] = now

    channel = bot.get_channel(ANTISPAM_CHANNEL_ID) if bot else None
    if not channel:
        from logging import getLogger
        getLogger(__name__).error(f"Antispam channel {ANTISPAM_CHANNEL_ID} not found.")
        return

    embed = discord.Embed(
        title=title,
        color=color if color is not None else LOG_COLORS["spam"],
        timestamp=now,
    )
    embed.set_author(name=str(user), icon_url=user.display_avatar.url)
    embed.add_field(name="Пользователь", value=f"{user.mention} (`{user}` | ID: `{user_id}`)", inline=False)
    embed.add_field(name="Причина", value=reason, inline=False)
    embed.add_field(name="Детали", value=details, inline=False)
    embed.set_footer(text=f"ID: {user_id}")

    mention_text = f"<@&{YOUR_ADMIN_ROLE_ID}> <@&{MODERATOR_ROLE_ID}>" if ping_admins else ""
    await channel.send(mention_text or None, embed=embed)


async def check_new_account(member: discord.Member, bot = None):
    """Проверяет возраст аккаунта нового участника и оповещает антиспам-канал без пинга ролей."""
    now = _utcnow()
    account_age = now - member.created_at
    if account_age >= timedelta(days=NEW_ACCOUNT_DAYS_THRESHOLD):
        return

    created_str = discord.utils.format_dt(member.created_at, style="R")
    await send_spam_alert(
        user=member,
        reason=f"Новый участник с молодым аккаунтом (< {NEW_ACCOUNT_DAYS_THRESHOLD} дн.)",
        details=f"Аккаунт создан: {created_str}\nВозраст аккаунта: `{account_age.days}` дн.",
        bot=bot,
        ping_admins=False,
        title="Антиспам: предупреждение о новом аккаунте",
        color=LOG_COLORS["warn"],
    )


async def check_spam(message: discord.Message, bot = None):
    if message.author.bot or not message.guild:
        return

    member = message.author
    user_id = member.id
    now = _utcnow()

    if "@everyone" in message.content or "@here" in message.content:
        if not member.guild_permissions.mention_everyone:
            preview = message.content[:300].replace("```", "")
            await send_spam_alert(
                user=member,
                reason="Попытка использовать @everyone / @here без прав",
                details=f"Канал: {message.channel.mention}\nТекст:\n```{preview}```",
                bot=bot,
            )
            return

    cutoff = now - timedelta(seconds=SPAM_TIME_WINDOW)
    log = user_message_log[user_id]
    log.append((now, message.channel.id))
    while log and log[0][0] < cutoff:
        log.popleft()

    unique_channels = {entry[1] for entry in log}
    if len(unique_channels) >= SPAM_CHANNELS_THRESHOLD:
        channel_mentions = ", ".join(f"<#{ch_id}>" for ch_id in unique_channels)
        window_minutes = SPAM_TIME_WINDOW // 60
        await send_spam_alert(
            user=member,
            reason=f"Сообщения в {len(unique_channels)} каналах за {window_minutes} мин.",
            details=f"Каналы: {channel_mentions}\nСообщений в окне: `{len(log)}`",
            bot=bot,
        )
