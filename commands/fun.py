"""Развлекательные команды: MrCarsen, золотойфонд, рулетка, ХУЯБЛЯ и др."""

import asyncio
import random

import discord
from discord.ext import commands

from config import MUTE_ROLE_ID
from randomlist import mr_carsen_messages, gold_fund_messages


def register(bot):

    @bot.command(name="MrCarsen")
    async def mrcarsen(ctx: commands.Context):
        await ctx.reply(random.choice(mr_carsen_messages))

    @bot.command(name="золотойфонд")
    async def zolotoy_fond(ctx: commands.Context):
        await ctx.reply(random.choice(gold_fund_messages))

    @bot.command(name="неумничай")
    async def ne_umnichai(ctx: commands.Context):
        await ctx.reply('Да пошёл ты нахуй!')

    @bot.command(name="аможетбытьты")
    async def a_mozhet_byt_ty(ctx: commands.Context):
        await ctx.reply('КТО?! Я?!')

    @bot.command(name="пошёлтынахуй")
    async def poshel_ty(ctx: commands.Context):
        await ctx.reply('Та за що, плять?..')

    @bot.command(name="ХУЯБЛЯ")
    async def khuablya(ctx: commands.Context):
        await ctx.reply("БАН!")
        role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
        if role and not ctx.author.guild_permissions.administrator:
            await ctx.author.add_roles(role, reason="Допизделся, дядя!")
            await asyncio.sleep(60)
            await ctx.author.remove_roles(role, reason="Время мьюта истекло")

    @bot.command(name="рулетка")
    async def roulette(ctx: commands.Context):
        if random.randint(1, 6) == 6:
            await ctx.reply("БАБАХ! You are dead. Not a big surprise.")
            role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
            if role and not ctx.author.guild_permissions.administrator:
                await ctx.author.add_roles(role, reason="Русская рулетка")
                await asyncio.sleep(60)
                await ctx.author.remove_roles(role, reason="Время мьюта истекло")
            else:
                pass  # admin
        else:
            await ctx.reply("**·щёлк·**\nФартовый однако!")
