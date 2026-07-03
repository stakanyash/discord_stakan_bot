"""Периодические задачи: автоматическое снятие мутов."""

from discord.ext import tasks

from config import GUILD_ID, MUTE_ROLE_ID
from database import get_mutes, remove_mute
from embeds import send_mod_log, LOG_COLORS
from moderation_core import _utcnow


@tasks.loop(minutes=1)
async def check_mutes(bot):
    try:
        now = _utcnow()
        for user_id, mute_info in list(get_mutes().items()):
            try:
                from database import dt_from_iso
                end_time = dt_from_iso(mute_info['end_time'])
                if now < end_time:
                    continue
                guild = bot.get_guild(GUILD_ID)
                if not guild:
                    continue
                member = guild.get_member(user_id)
                if not member:
                    remove_mute(user_id)
                    continue
                import discord
                role = discord.utils.get(guild.roles, id=MUTE_ROLE_ID)
                if role and role in member.roles:
                    await member.remove_roles(role, reason="Время мьюта истекло")
                remove_mute(user_id)
                await send_mod_log("Мут истёк", LOG_COLORS["join"], member, bot=bot)
            except Exception as e:
                from logging import getLogger
                getLogger(__name__).error(f"Auto-unmute error for user {user_id}: {e}")
    except Exception as e:
        from logging import getLogger
        getLogger(__name__).error(f"check_mutes task fatal error: {e}")


@check_mutes.before_loop
async def before_tasks(bot):
    await bot.wait_until_ready()
