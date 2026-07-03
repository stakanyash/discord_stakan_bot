"""Stakan Discord Bot — точка входа."""

import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

import discord
from discord.ext import commands

# ─── Конфиг ───────────────────────────────────────────────────────────────
from config import DISCORD_TOKEN, DB_FILE, GUILD_ID

# ─── БД ───────────────────────────────────────────────────────────────────
from database import create_tables

# ─── Logger ───────────────────────────────────────────────────────────────

def setup_logger() -> logging.Logger:
    log_filename = f"stakandiscordbot_{datetime.now().strftime('%Y.%m.%d_%H.%M.%S')}.log"
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '[%(levelname)s] %(asctime)s [%(filename)s:%(lineno)d] - %(message)s',
        '%Y-%m-%d %H:%M:%S'
    )
    logger.handlers.clear()
    file_handler = RotatingFileHandler(log_filename, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger

logger = setup_logger()

# ─── Intents & Bot ────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, log_handler=None)
bot.remove_command('help')

# ─── Register modules ────────────────────────────────────────────────────

def register_all():
    from commands import moderation as mod_cmds
    from commands import fun
    from commands import admin
    from commands import subscribe
    from commands import help as help_cmd
    from events import register as register_events
    from tasks import check_mutes

    mod_cmds.register(bot)
    fun.register(bot)
    admin.register(bot)
    subscribe.register(bot)
    help_cmd.register(bot)
    register_events(bot)

    # Сохраняем ссылку на задачу для запуска в on_ready
    bot._check_mutes_task = check_mutes

# ─── On ready ─────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    logger.info(f"{bot.user} is online and ready")

    # Синхронизация по конкретной гильдии применяется мгновенно.
    # Глобальная bot.tree.sync() (без guild=...) может доходить до
    # Discord и клиентов до часа — в течение этого окна клиент может
    # присылать интеракции со СТАРОЙ сигнатурой команды, что приводит
    # к "The application did not respond", т.к. эти ошибки не долетают
    # до on_command_error (см. on_app_command_error ниже).
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    logger.info(f"Slash commands synced to guild {GUILD_ID}: {len(synced)} команд")

    if not bot._check_mutes_task.is_running():
        bot._check_mutes_task.start(bot)


# ─── Global app-commands error handler ───────────────────────────────────
# Ошибки уровня CommandTree (сбой конвертации параметра, рассинхрон
# сигнатуры команды с тем, что закэшировано у Discord, ошибки check()
# для чистых app_commands и т.д.) НЕ попадают в on_command_error —
# у них отдельный пайплайн. Без этого обработчика такие ошибки просто
# логировались бы в stderr, а пользователь видел бы вечное
# "The application did not respond".

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    from embeds import e_err

    logger.error(f"App command error in /{interaction.command.name if interaction.command else '?'}: {error!r}", exc_info=error)

    if isinstance(error, discord.app_commands.CheckFailure):
        message = "У вас нет прав для этой команды."
    elif isinstance(error, discord.app_commands.CommandSignatureMismatch):
        message = "Команда была недавно обновлена. Подождите синхронизации с Discord (обычно до пары минут) и попробуйте снова."
    else:
        message = "Произошла ошибка при выполнении команды. Об этом уже записано в лог."

    embed = e_err("Ошибка", message)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException:
        pass

# ─── Startup ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    create_tables()
    register_all()
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_TOKEN not found in .env!")
    else:
        bot.run(DISCORD_TOKEN)
