"""Команды подписки: subscribe, subscribesecond."""

import discord
from discord.ext import commands
from discord.ext.commands import has_permissions

from config import YT_SUBSCRIBER_ROLE_ID, SEC_YT_SUBSCRIBER_ROLE_ID
from views import SubscribeView
from embeds import e_err, _now_dt


def register(bot):

    @bot.hybrid_command(with_app_command=True)
    @has_permissions(manage_roles=True)
    async def subscribe(ctx: commands.Context):
        """Отправить кнопку подписки на уведомления (первый канал)."""
        role = discord.utils.get(ctx.guild.roles, id=YT_SUBSCRIBER_ROLE_ID)
        if not role:
            await ctx.send(embed=e_err("Роль не найдена"))
            return
        embed = discord.Embed(
            title="Подписка на уведомления",
            description=f"Нажмите кнопку ниже, чтобы получить или снять роль {role.mention}.",
            color=role.color,
        )
        await ctx.send(embed=embed, view=SubscribeView(YT_SUBSCRIBER_ROLE_ID))

    @bot.hybrid_command(with_app_command=True)
    @has_permissions(manage_roles=True)
    async def subscribesecond(ctx: commands.Context):
        """Отправить кнопку подписки на уведомления (второй канал)."""
        role = discord.utils.get(ctx.guild.roles, id=SEC_YT_SUBSCRIBER_ROLE_ID)
        if not role:
            await ctx.send(embed=e_err("Роль не найдена"))
            return
        embed = discord.Embed(
            title="Подписка на уведомления",
            description=f"Нажмите кнопку ниже, чтобы получить или снять роль {role.mention}.",
            color=role.color,
        )
        await ctx.send(embed=embed, view=SubscribeView(SEC_YT_SUBSCRIBER_ROLE_ID))
