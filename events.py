"""Обработчики событий Discord."""

import discord

from embeds import LOG_COLORS, _now_dt, send_log_embed
from antispam import check_spam, check_new_account


def register(bot):

    @bot.event
    async def on_message(message: discord.Message):
        if message.author == bot.user:
            return
        if isinstance(message.channel, discord.DMChannel):
            await message.author.send(
                "Данный бот может работать только на сервере «стакан». "
                "Взаимодействие через личные сообщения не предусмотрено."
            )
            return
        await check_spam(message, bot=bot)
        await bot.process_commands(message)

    @bot.event
    async def on_member_update(before: discord.Member, after: discord.Member):
        if before.roles == after.roles:
            return
        added = [r for r in after.roles if r not in before.roles and r.id != __import__('config').MUTE_ROLE_ID]
        removed = [r for r in before.roles if r not in after.roles and r.id != __import__('config').MUTE_ROLE_ID]

        if added:
            embed = discord.Embed(title="Роли добавлены", color=LOG_COLORS["role_add"], timestamp=_now_dt())
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            embed.add_field(name="Участник", value=after.mention, inline=True)
            embed.add_field(name="Роли", value=" ".join(r.mention for r in added), inline=True)
            embed.set_footer(text=f"ID: {after.id}")
            await send_log_embed(embed, bot=bot)

        if removed:
            embed = discord.Embed(title="Роли удалены", color=LOG_COLORS["role_remove"], timestamp=_now_dt())
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            embed.add_field(name="Участник", value=after.mention, inline=True)
            embed.add_field(name="Роли", value=" ".join(r.mention for r in removed), inline=True)
            embed.set_footer(text=f"ID: {after.id}")
            await send_log_embed(embed, bot=bot)

    @bot.event
    async def on_member_join(member: discord.Member):
        embed = discord.Embed(title="Участник вошёл", color=LOG_COLORS["join"], timestamp=_now_dt())
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="Упоминание", value=member.mention, inline=True)
        embed.add_field(name="Аккаунт создан", value=discord.utils.format_dt(member.created_at, style="R"), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"ID: {member.id}")
        await send_log_embed(embed, bot=bot)
        await check_new_account(member, bot=bot)

    @bot.event
    async def on_member_remove(member: discord.Member):
        embed = discord.Embed(title="Участник вышел", color=LOG_COLORS["leave"], timestamp=_now_dt())
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="Упоминание", value=member.mention, inline=True)
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        if roles:
            embed.add_field(name="Роли", value=" ".join(roles), inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"ID: {member.id}")
        await send_log_embed(embed, bot=bot)

    @bot.event
    async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return
        if before.channel is None:
            embed = discord.Embed(title="Вошёл в голосовой канал", color=LOG_COLORS["voice"], timestamp=_now_dt())
            embed.add_field(name="Канал", value=after.channel.mention, inline=True)
        elif after.channel is None:
            embed = discord.Embed(title="Вышел из голосового канала", color=LOG_COLORS["voice"], timestamp=_now_dt())
            embed.add_field(name="Канал", value=before.channel.mention, inline=True)
        else:
            embed = discord.Embed(title="Сменил голосовой канал", color=LOG_COLORS["voice"], timestamp=_now_dt())
            embed.add_field(name="Откуда", value=before.channel.mention, inline=True)
            embed.add_field(name="Куда", value=after.channel.mention, inline=True)
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="Участник", value=member.mention, inline=True)
        embed.set_footer(text=f"ID: {member.id}")
        await send_log_embed(embed, bot=bot)

    @bot.event
    async def on_message_edit(before: discord.Message, after: discord.Message):
        if before.content == after.content:
            return

        def trim(text: str) -> str:
            return text[:1021] + "..." if len(text) > 1024 else (text or "*пусто*")

        embed = discord.Embed(
            title="Сообщение отредактировано",
            color=LOG_COLORS["msg_edit"],
            timestamp=_now_dt(),
            url=after.jump_url,
        )
        embed.set_author(name=str(after.author), icon_url=after.author.display_avatar.url)
        embed.add_field(name="Канал", value=after.channel.mention, inline=True)
        embed.add_field(name="Перейти", value=f"[к сообщению]({after.jump_url})", inline=True)
        embed.add_field(name="До", value=trim(before.content), inline=False)
        embed.add_field(name="После", value=trim(after.content), inline=False)
        embed.set_footer(text=f"ID автора: {after.author.id}")
        await send_log_embed(embed, bot=bot)

    @bot.event
    async def on_message_delete(message: discord.Message):
        if message.author == bot.user or isinstance(message.channel, discord.DMChannel):
            return

        def trim(text: str) -> str:
            return text[:1021] + "..." if len(text) > 1024 else (text or "*пусто*")

        embed = discord.Embed(title="Сообщение удалено", color=LOG_COLORS["msg_delete"], timestamp=_now_dt())
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name="Автор", value=message.author.mention, inline=True)
        embed.add_field(name="Канал", value=message.channel.mention, inline=True)
        embed.add_field(name="Текст", value=trim(message.content), inline=False)
        if message.attachments:
            embed.add_field(
                name=f"Вложения ({len(message.attachments)})",
                value="\n".join(a.filename for a in message.attachments),
                inline=False,
            )
        embed.set_footer(text=f"ID автора: {message.author.id}")
        await send_log_embed(embed, bot=bot)

    @bot.event
    async def on_command_error(ctx, error):
        from discord.ext import commands
        from embeds import e_err
        import logging

        if isinstance(error, commands.CheckFailure):
            await ctx.send(embed=e_err("Нет прав", "У вас нет прав для этой команды."))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=e_err("Неверные аргументы", f"Пропущен аргумент: `{error.param.name}`"))
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=e_err("Неверный аргумент", str(error)))
        elif isinstance(error, commands.CommandNotFound):
            pass
        else:
            # Раньше здесь стоял только "pass" — любая непредвиденная
            # ошибка (например, исключение внутри самой команды) уходила
            # в никуда: ни лога, ни ответа пользователю, что снаружи
            # выглядело как "The application did not respond".
            original = getattr(error, "original", error)
            logging.getLogger(__name__).error(
                f"Необработанная ошибка в команде {getattr(ctx, 'command', None)}: {original!r}",
                exc_info=original,
            )
            try:
                await ctx.send(embed=e_err("Ошибка", "Что-то пошло не так при выполнении команды. Об этом записано в лог."))
            except discord.HTTPException:
                pass
