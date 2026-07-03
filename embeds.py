"""Вспомогательные функции для создания embed-ов и константы цветов."""

import discord
from datetime import datetime, timezone

from config import LOG_CHANNEL_ID


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _now_dt() -> datetime:
    return _utcnow()


# ─── Embed builders ───────────────────────────────────────────────────────

def e_ok(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=0x57F287, timestamp=_now_dt())


def e_err(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=0xED4245, timestamp=_now_dt())


def e_info(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=0x5865F2, timestamp=_now_dt())


def e_warn(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=0xFEE75C, timestamp=_now_dt())


# ─── Log colors ───────────────────────────────────────────────────────────

LOG_COLORS = {
    "join":        0x57F287,
    "leave":       0xED4245,
    "role_add":    0x5865F2,
    "role_remove": 0xEB459E,
    "voice":       0x9B59B6,
    "msg_edit":    0xFEE75C,
    "msg_delete":  0xE67E22,
    "mod":         0xED4245,
    "spam":        0xFF6B35,
    "warn":        0xFEE75C,
    "yt":          0xFF0000,
}


# ─── Action embeds ────────────────────────────────────────────────────────

def make_action_embed(
    action: str,
    member: discord.Member,
    moderator: discord.Member,
    reason: str,
    color: discord.Color,
    *,
    duration: str = None,
    until: datetime = None,
) -> discord.Embed:
    embed = discord.Embed(color=color, timestamp=_now_dt())
    embed.set_author(name=f"Участник {member} {action}.", icon_url=member.display_avatar.url)
    embed.add_field(name="Причина",   value=reason,            inline=False)
    embed.add_field(name="Модератор", value=moderator.mention, inline=True)
    if duration:
        embed.add_field(name="Длительность", value=duration, inline=True)
    if until:
        embed.add_field(name="Заглушён до", value=discord.utils.format_dt(until, style="f"), inline=True)
    embed.set_footer(text=f"ID: {member.id}")
    return embed


# ─── Send log helpers ─────────────────────────────────────────────────────

async def send_log_embed(embed: discord.Embed, bot=None):
    """Отправляет embed в лог-канал."""
    if bot is None:
        # Lazy import чтобы избежать циклических зависимостей
        import bot as bot_module
        bot = bot_module.bot
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)
    else:
        from logging import getLogger
        getLogger(__name__).error(f"Log channel {LOG_CHANNEL_ID} not found")


async def send_mod_log(
    title: str,
    color: int,
    member: discord.User | discord.Member,
    *,
    moderator: discord.Member = None,
    reason: str = None,
    duration: str = None,
    until: datetime = None,
    extra_fields: list[tuple[str, str, bool]] = None,
    bot = None,
):
    embed = discord.Embed(title=title, color=color, timestamp=_now_dt())
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    embed.add_field(name="Участник", value=member.mention, inline=True)
    if moderator:
        embed.add_field(name="Модератор", value=moderator.mention, inline=True)
    if duration:
        embed.add_field(name="Длительность", value=duration, inline=True)
    if until:
        embed.add_field(name="До", value=discord.utils.format_dt(until, style="f"), inline=True)
    if reason:
        embed.add_field(name="Причина", value=reason, inline=False)
    if extra_fields:
        for name, value, inline in extra_fields:
            embed.add_field(name=name, value=value, inline=inline)
    embed.set_footer(text=f"ID: {member.id}")
    await send_log_embed(embed, bot=bot)
