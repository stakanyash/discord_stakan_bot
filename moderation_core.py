"""Ядро модерации: применение мута и варнов, проверка прав."""

import discord
from datetime import datetime, timedelta, timezone

from config import MUTE_ROLE_ID, MODERATOR_ROLE_ID
from database import add_mute, add_warning, get_recent_warnings, remove_warnings
from embeds import e_err, e_warn, make_action_embed, send_mod_log, LOG_COLORS
from views import UnmuteView


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def seconds_to_human(seconds: int) -> str:
    parts = []
    weeks, seconds = divmod(seconds, 604800)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    mins, seconds = divmod(seconds, 60)
    if weeks:
        parts.append(f"{weeks} нед.")
    if days:
        parts.append(f"{days} дн.")
    if hours:
        parts.append(f"{hours} ч.")
    if mins:
        parts.append(f"{mins} мин.")
    if seconds or not parts:
        parts.append(f"{seconds} сек.")
    return " ".join(parts)


def parse_duration(duration: str) -> int | None:
    duration = duration.strip()
    try:
        if duration.endswith('d'):
            return int(duration[:-1]) * 86400
        if duration.endswith('h'):
            return int(duration[:-1]) * 3600
        if duration.endswith('m'):
            return int(duration[:-1]) * 60
        if duration.endswith('s'):
            return int(duration[:-1])
    except ValueError:
        pass
    return None


def is_moderator(member: discord.Member) -> bool:
    return any(role.id == MODERATOR_ROLE_ID for role in member.roles)


def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.manage_messages


def is_admin_or_moderator(member: discord.Member) -> bool:
    return is_admin(member) or is_moderator(member)


def _can_moderate(actor: discord.Member, target: discord.Member) -> tuple[bool, str]:
    if actor.id == target.id:
        return False, "Нельзя применить это действие к самому себе."
    if target.bot:
        return False, "Нельзя применять модерацию к ботам."
    if target.guild_permissions.administrator:
        return False, "Нельзя применить это действие к администратору сервера."
    if is_moderator(target) and not actor.guild_permissions.administrator:
        return False, "Нельзя применить это действие к другому модератору."
    if actor.top_role <= target.top_role and not actor.guild_permissions.administrator:
        return False, "Нельзя применить это действие к участнику с равной или более высокой ролью."
    return True, ""


async def apply_mute(ctx, member: discord.Member, duration_seconds: int, reason: str) -> bool:
    role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if not role:
        await ctx.send(embed=e_err("Роль мьюта не найдена", "Проверьте переменную `MUTE_ROLE_ID` в `.env`."))
        return False
    try:
        await member.add_roles(role, reason=reason)
    except discord.Forbidden:
        await ctx.send(embed=e_err("Нет прав", "У меня недостаточно прав для выдачи роли мьюта."))
        return False

    until = _utcnow() + timedelta(seconds=duration_seconds)
    human = seconds_to_human(duration_seconds)
    add_mute(member.id, until, reason)

    embed = make_action_embed(
        action="заглушён", member=member, moderator=ctx.author,
        reason=reason, color=discord.Color.orange(),
        duration=human, until=until,
    )
    await ctx.send(embed=embed, view=UnmuteView(member.id))
    await send_mod_log(
        "Мут выдан", LOG_COLORS["mod"], member,
        moderator=ctx.author, reason=reason,
        duration=human, until=until,
        bot=ctx.bot,
    )
    return True


async def apply_warn(ctx, member: discord.Member, reason: str):
    mute_role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if mute_role and mute_role in member.roles:
        await ctx.send(embed=e_warn("Уже замьючен", f"{member.mention} уже находится в муте — варн не выдан."))
        return

    add_warning(member.id, reason)
    recent = get_recent_warnings(member.id)

    if len(recent) >= 3:
        muted = await apply_mute(ctx, member, duration_seconds=86400,
                                  reason="3 предупреждения за 24 часа")
        if muted:
            remove_warnings(member.id)
    else:
        embed = make_action_embed(
            action="предупреждён", member=member, moderator=ctx.author,
            reason=reason, color=discord.Color.yellow(),
        )
        embed.add_field(name="Предупреждений (за 24ч)", value=f"{len(recent)}/3", inline=True)
        await ctx.send(embed=embed)
        await send_mod_log(
            "Предупреждение выдано", 0xFEE75C, member,
            moderator=ctx.author, reason=reason,
            extra_fields=[("Счётчик", f"{len(recent)}/3", True)],
            bot=ctx.bot,
        )
