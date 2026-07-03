"""Команды модерации: mute, unmute, ban, warn, warnings, warnremove, mute_all."""

import asyncio
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from config import MUTE_ROLE_ID
from moderation_core import (
    is_admin_or_moderator,
    is_admin,
    _can_moderate,
    parse_duration,
    apply_mute,
    apply_warn,
)
from database import (
    remove_mute,
    get_warnings,
    remove_warnings,
)
from embeds import e_err, e_ok, e_warn, e_info, send_mod_log, LOG_COLORS


def register(bot):

    @bot.hybrid_command(with_app_command=True)
    @commands.check(lambda ctx: is_admin_or_moderator(ctx.author))
    async def mute(ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = "Не указана"):
        """Замьютить участника на указанное время."""
        can, why = _can_moderate(ctx.author, member)
        if not can:
            await ctx.send(embed=e_err("Нет прав", why))
            return
        duration_seconds = parse_duration(duration)
        if duration_seconds is None:
            await ctx.send(embed=e_err("Неверный формат", "Используйте: `60s`, `30m`, `2h`, `1d`."))
            return
        await apply_mute(ctx, member, duration_seconds, reason)

    @bot.hybrid_command(with_app_command=True)
    @commands.check(lambda ctx: is_admin_or_moderator(ctx.author))
    async def unmute(ctx: commands.Context, member: discord.Member):
        """Снять мут с участника."""
        can, why = _can_moderate(ctx.author, member)
        if not can:
            await ctx.send(embed=e_err("Нет прав", why))
            return
        role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
        if role and role in member.roles:
            await member.remove_roles(role, reason="Ручной анмьют")
            remove_mute(member.id)
            embed = e_ok("Мут снят", f"{member.mention} был размьючен модератором {ctx.author.mention}.")
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"ID: {member.id}")
            await ctx.send(embed=embed)
            await send_mod_log("Мут снят", LOG_COLORS["join"], member, moderator=ctx.author, bot=ctx.bot)
        else:
            await ctx.send(embed=e_warn("Не замьючен", f"{member.mention} не имеет роли мьюта."))

    @bot.hybrid_command(name="sban", with_app_command=True)
    @commands.check(lambda ctx: is_admin_or_moderator(ctx.author))
    @app_commands.describe(member="Участник для бана", delete_message_period="Период удаления сообщений", reason="Причина бана")
    @app_commands.choices(delete_message_period=[
        app_commands.Choice(name="Не удалять", value=0),
        app_commands.Choice(name="Последний час", value=1),
        app_commands.Choice(name="Последние 6 часов", value=6),
        app_commands.Choice(name="Последние 12 часов", value=12),
        app_commands.Choice(name="Последний день", value=24),
        app_commands.Choice(name="Последние 3 дня", value=72),
        app_commands.Choice(name="Последнюю неделю", value=168),
    ])
    async def sban(ctx: commands.Context, member: discord.Member, delete_message_period: app_commands.Choice[int], *, reason: str = "Не указана"):
        """Забанить участника с удалением сообщений за указанный период."""
        # Подтверждаем interaction сразу же, до любой другой логики —
        # чтобы не упереться в 3-секундное окно Discord ни при каких
        # обстоятельствах.
        await ctx.defer()

        can, why = _can_moderate(ctx.author, member)
        if not can:
            await ctx.send(embed=e_err("Нет прав", why))
            return

        # Значение хранится в часах (макс. 168ч = 7 дней — предел Discord).
        seconds = delete_message_period.value * 3600
        try:
            await ctx.guild.ban(member, reason=f"{ctx.author} ({ctx.author.id}): {reason}", delete_message_seconds=seconds)
        except discord.Forbidden:
            await ctx.send(embed=e_err("Нет прав", "У меня недостаточно прав для бана."))
            return
        except discord.HTTPException as e:
            await ctx.send(embed=e_err("Ошибка", f"Не удалось забанить участника: {e}"))
            return
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Неожиданная ошибка в /sban: {e!r}", exc_info=e)
            await ctx.send(embed=e_err("Ошибка", "Непредвиденная ошибка при бане. Об этом записано в лог."))
            return

        period_label = delete_message_period.name
        embed = e_ok("Бан выдан", f"{member.mention} забанен модератором {ctx.author.mention}.")
        embed.add_field(name="Причина", value=reason, inline=False)
        embed.add_field(name="Удаление сообщений", value=period_label, inline=True)
        embed.set_footer(text=f"ID: {member.id}")
        await ctx.send(embed=embed)
        await send_mod_log(
            "Бан выдан", LOG_COLORS["mod"], member,
            moderator=ctx.author, reason=reason,
            extra_fields=[("Удаление сообщений", period_label, True)],
            bot=ctx.bot,
        )

    @bot.hybrid_command(with_app_command=True)
    @commands.check(lambda ctx: is_admin_or_moderator(ctx.author))
    async def warn(ctx: commands.Context, member: discord.Member, *, reason: str = "Не указана"):
        """Выдать предупреждение участнику."""
        can, why = _can_moderate(ctx.author, member)
        if not can:
            await ctx.send(embed=e_err("Нет прав", why))
            return
        await apply_warn(ctx, member, reason)

    @bot.hybrid_command(with_app_command=True)
    @commands.check(lambda ctx: is_admin_or_moderator(ctx.author))
    async def warnremove(ctx: commands.Context, member: discord.Member):
        """Удалить все предупреждения участника."""
        can, why = _can_moderate(ctx.author, member)
        if not can:
            await ctx.send(embed=e_err("Нет прав", why))
            return
        if get_warnings(member.id):
            remove_warnings(member.id)
            embed = e_ok("Предупреждения сняты", f"Все предупреждения {member.mention} удалены.")
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
            embed.set_footer(text=f"ID: {member.id}")
            await ctx.send(embed=embed)
        else:
            await ctx.send(embed=e_info("Нет предупреждений", f"У {member.mention} нет предупреждений."))

    @bot.hybrid_command(with_app_command=True)
    @commands.check(lambda ctx: is_admin_or_moderator(ctx.author))
    async def warnings(ctx: commands.Context, member: discord.Member):
        """Показать предупреждения участника."""
        warnings_list = get_warnings(member.id)
        if warnings_list:
            embed = e_warn(
                f"Предупреждения — {member.display_name}",
                f"Всего: **{len(warnings_list)}**"
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"ID: {member.id}")
            for i, w in enumerate(reversed(warnings_list), 1):
                ts = datetime.fromisoformat(w['timestamp']).strftime('%d.%m.%Y %H:%M UTC')
                embed.add_field(name=f"#{i} · {ts}", value=w['reason'], inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(embed=e_ok("Нет предупреждений", f"У {member.mention} нет предупреждений."))

    @bot.hybrid_command(with_app_command=True)
    @commands.check(lambda ctx: is_admin(ctx.author))
    async def mute_all(ctx: commands.Context, *, reason: str = "Массовый мут"):
        """Замьютить всех участников текущего канала на 1 час."""
        role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
        if not role:
            await ctx.send(embed=e_err("Роль мьюта не найдена"))
            return
        members = [m for m in ctx.channel.members if m != ctx.guild.me and not m.guild_permissions.administrator and m.id != ctx.author.id]
        await asyncio.gather(*[m.add_roles(role, reason=reason) for m in members])
        await ctx.send(embed=e_warn("Массовый мут", f"Замьючено участников: **{len(members)}**. Мут снимется через 1 час."))
        await asyncio.sleep(3600)
        await asyncio.gather(*[m.remove_roles(role, reason="Время мьюта истекло") for m in members])
        await ctx.send(embed=e_ok("Массовый мут снят", "Все участники размьючены."))
