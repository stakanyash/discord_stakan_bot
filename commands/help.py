"""Команда help."""

import discord
from discord import app_commands
from embeds import _now_dt


def register(bot):

    @bot.tree.command(name="help", description="Показать справку по командам бота (видно только вам)")
    async def help_command(interaction: discord.Interaction):
        embeds_list = []

        overview = discord.Embed(
            title="Справка по командам бота",
            description=(
                "Административные команды доступны как `/команда`, так и `!команда`.\n"
                "Развлекательные команды — только через префикс `!`.\n\n"
                "**Разделы:** Мут / Анмьют | Предупреждения | Развлечения"
            ),
            color=0x5865F2,
        )
        embeds_list.append(overview)

        mute_embed = discord.Embed(title="Мут / Анмьют / Бан", color=0xFFA500)
        mute_embed.add_field(name="/mute участник длительность [причина]",
                             value="Выдаёт мут. Форматы: `60s`, `30m`, `2h`, `1d`.", inline=False)
        mute_embed.add_field(name="/unmute участник",
                             value="Снимает мут немедленно.", inline=False)
        mute_embed.add_field(name="/sban участник период [причина]",
                             value="Бан с удалением сообщений. Период: от 0 (не удалять) до 7 дней.", inline=False)
        mute_embed.add_field(name="/mute_all [причина]",
                             value="Мьютит всех в канале на 1 час (только администраторы).", inline=False)
        embeds_list.append(mute_embed)

        warn_embed = discord.Embed(title="Предупреждения", color=0xFEE75C)
        warn_embed.add_field(name="/warn участник [причина]",
                             value="Выдаёт предупреждение. При 3 варнах за 24ч — автомут на 24ч.", inline=False)
        warn_embed.add_field(name="/warnings участник", value="Показывает предупреждения.", inline=False)
        warn_embed.add_field(name="/warnremove участник", value="Удаляет все предупреждения.", inline=False)
        embeds_list.append(warn_embed)

        fun_embed = discord.Embed(title="Развлечения (только !)", color=0x57F287)
        fun_embed.add_field(name="!рулетка", value="Русская рулетка. Проигравший получает мут на 1 мин.", inline=False)
        fun_embed.add_field(name="!bomb", value="Заложить бомбу. 60 мин на разминирование командой `!defuse`.", inline=False)
        fun_embed.add_field(name="!defuse <код>", value="Ввести код разминирования бомбы.", inline=False)
        fun_embed.add_field(name="!MrCarsen", value="Случайная цитата МрКарсена.", inline=False)
        fun_embed.add_field(name="!золотойфонд", value="Случайное сообщение из золотого фонда.", inline=False)
        fun_embed.add_field(name="!неумничай", value="Послать умника.", inline=False)
        fun_embed.add_field(name="!аможетбытьты", value="КТО?! Я?!", inline=False)
        fun_embed.add_field(name="!пошёлтынахуй", value="Та за шо, плять?..", inline=False)
        fun_embed.add_field(name="!ХУЯБЛЯ", value="БАН! Мут на 1 минуту.", inline=False)
        embeds_list.append(fun_embed)

        await interaction.response.send_message(embeds=embeds_list, ephemeral=True)
