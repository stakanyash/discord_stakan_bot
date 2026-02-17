import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import asyncio
import collections
from datetime import datetime, timedelta
import random
import googleapiclient.discovery
import googleapiclient.errors
from dotenv import load_dotenv
import os
import logging
import sqlite3
import sys
from randomlist import mr_carsen_messages, gold_fund_messages

log_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_filename = f"stakandiscordbot_{log_timestamp}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

bot.remove_command('help')

bomb_info = {}

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MUTE_ROLE_ID = int(os.getenv("MUTE_ROLE_ID"))
YOUR_ADMIN_ROLE_ID = int(os.getenv("YOUR_ADMIN_ROLE_ID"))
NOTIFICATION_CHANNEL_ID = int(os.getenv("NOTIFICATION_CHANNEL_ID"))
YOUTUBE_API_KEYS = [key.strip('"') for key in os.getenv("YOUTUBE_API_KEYS").split(',')]
YOUTUBE_CHANNEL_ID_1 = os.getenv("YOUTUBE_CHANNEL_ID_1")
YOUTUBE_CHANNEL_ID_2 = os.getenv("YOUTUBE_CHANNEL_ID_2")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
YT_SUBSCRIBER_ROLE_ID = int(os.getenv("YT_SUBSCRIBER_ROLE_ID"))
SEC_YT_SUBSCRIBER_ROLE_ID = int(os.getenv("SEC_YT_SUBSCRIBER_ROLE_ID"))
USER_ID = int(os.getenv("USER_ID"))
MODERATOR_ROLE_ID = int(os.getenv("MODERATOR_ROLE_ID"))
ANTISPAM_CHANNEL_ID = int(os.getenv("ANTISPAM_CHANNEL_ID"))

def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.manage_messages

def is_moderator(member: discord.Member) -> bool:
    return any(role.id == MODERATOR_ROLE_ID for role in member.roles)

def is_admin_or_moderator(member: discord.Member) -> bool:
    return is_admin(member) or is_moderator(member)

def has_protected_role(member: discord.Member) -> bool:
    return is_admin(member) or is_moderator(member)

def admin_or_mod():
    async def predicate(ctx):
        if is_admin_or_moderator(ctx.author):
            return True
        raise commands.CheckFailure("no_permission")
    return commands.check(predicate)

def admin_only():
    async def predicate(ctx):
        if is_admin(ctx.author):
            return True
        raise commands.CheckFailure("no_permission")
    return commands.check(predicate)

def _no_permission_message(ctx) -> str:
    if is_moderator(ctx.author):
        return "Вы не можете применить это действие к другому модератору или администратору."
    return "У вас нет прав для этой команды."

SPAM_TIME_WINDOW = int(os.getenv("SPAM_TIME_WINDOW", 120))
SPAM_CHANNELS_THRESHOLD = int(os.getenv("SPAM_CHANNELS_THRESHOLD", 3))
SPAM_ALERT_COOLDOWN = 300

user_message_log: dict[int, collections.deque] = collections.defaultdict(lambda: collections.deque())
last_spam_alert: dict[int, datetime] = {}

def create_tables():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS warnings (
                  user_id INTEGER, timestamp TEXT, reason TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mutes (
                  user_id INTEGER, end_time TEXT, reason TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS bomb_cooldowns (
                  guild_id INTEGER PRIMARY KEY, end_time TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS last_video_ids (
                  channel_id TEXT PRIMARY KEY, video_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS role_users (
                  user_id INTEGER PRIMARY KEY, role_id INTEGER)''')
    conn.commit()
    conn.close()

create_tables()

def get_warnings(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, reason FROM warnings WHERE user_id = ?", (user_id,))
    warnings = c.fetchall()
    conn.close()
    return [{'timestamp': w[0], 'reason': w[1]} for w in warnings]

def add_warning(user_id, reason):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO warnings (user_id, timestamp, reason) VALUES (?, ?, ?)",
              (user_id, datetime.now().isoformat(), reason))
    conn.commit()
    conn.close()

def remove_warnings(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_mutes():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT user_id, end_time, reason FROM mutes")
    mutes = c.fetchall()
    conn.close()
    return {m[0]: {'end_time': m[1], 'reason': m[2]} for m in mutes}

def add_mute(user_id, end_time, reason):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO mutes (user_id, end_time, reason) VALUES (?, ?, ?)",
              (user_id, end_time.isoformat(), reason))
    conn.commit()
    conn.close()

def remove_mute(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("DELETE FROM mutes WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_bomb_cooldown(guild_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT end_time FROM bomb_cooldowns WHERE guild_id = ?", (guild_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def set_bomb_cooldown(guild_id, end_time):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO bomb_cooldowns (guild_id, end_time) VALUES (?, ?)",
              (guild_id, end_time.isoformat()))
    conn.commit()
    conn.close()

def remove_bomb_cooldown(guild_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("DELETE FROM bomb_cooldowns WHERE guild_id = ?", (guild_id,))
    conn.commit()
    conn.close()

def get_last_video_id(channel_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT video_id FROM last_video_ids WHERE channel_id = ?", (channel_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def set_last_video_id(channel_id, video_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO last_video_ids (channel_id, video_id) VALUES (?, ?)",
              (channel_id, video_id))
    conn.commit()
    conn.close()

def get_role_users(role_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM role_users WHERE role_id = ?", (role_id,))
    users = c.fetchall()
    conn.close()
    return [u[0] for u in users]

def parse_duration(duration: str) -> int:
    if duration.endswith('d'):
        return int(duration[:-1]) * 86400
    elif duration.endswith('h'):
        return int(duration[:-1]) * 3600
    elif duration.endswith('m'):
        return int(duration[:-1]) * 60
    elif duration.endswith('s'):
        return int(duration[:-1])
    return None

def get_youtube_service(api_key):
    return googleapiclient.discovery.build('youtube', 'v3', developerKey=api_key)

async def send_spam_alert(user: discord.Member, reason: str, details: str):
    user_id = user.id
    now = datetime.now()
    last_alert = last_spam_alert.get(user_id)
    if last_alert and (now - last_alert).total_seconds() < SPAM_ALERT_COOLDOWN:
        return
    last_spam_alert[user_id] = now

    alert_text = (
        f"<@&{YOUR_ADMIN_ROLE_ID}> <@&{MODERATOR_ROLE_ID}>\n"
        f"\n"
        f"**Антиспам: подозрительная активность!**\n"
        f"Пользователь: {user.mention} (`{user}` | ID: `{user_id}`)\n"
        f"Причина: **{reason}**\n"
        f"\n"
        f"{details}"
    )
    log_channel = bot.get_channel(ANTISPAM_CHANNEL_ID)
    if log_channel:
        await log_channel.send(alert_text)
        logging.warning(f"[SPAM ALERT] [{reason}] {user} ({user_id}). {details}")
    else:
        logging.error(f"Spam alert: log channel {ANTISPAM_CHANNEL_ID} not found.")


async def check_spam(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    user_id = message.author.id
    member = message.author
    now = datetime.now()

    if "@everyone" in message.content or "@here" in message.content:
        if not member.guild_permissions.mention_everyone:
            preview = message.content[:300].replace("```", "")
            await send_spam_alert(
                user=member,
                reason="Попытка использовать @everyone / @here без прав",
                details=f"Канал: {message.channel.mention}\nТекст сообщения:\n```{preview}```"
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
            details=f"Каналы: {channel_mentions}\nСообщений в окне наблюдения: `{len(log)}`"
        )

@bot.event
async def on_ready():
    logging.info(f'Logged in as {bot.user}')
    bot.add_view(SubscribeView(YT_SUBSCRIBER_ROLE_ID))
    bot.add_view(SubscribeView(SEC_YT_SUBSCRIBER_ROLE_ID))
    if not check_mutes.is_running():
        check_mutes.start()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if isinstance(message.channel, discord.DMChannel):
        await message.author.send(
            "Данный бот может работать только на сервере \"стакан\". "
            "Взаимодействие через личные сообщения не предусмотрено."
        )
    await check_spam(message)
    await bot.process_commands(message)

async def send_log_message(message):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        for part in [message[i:i+4000] for i in range(0, len(message), 4000)]:
            await channel.send(part)
    else:
        logging.error(f"Log channel with ID {LOG_CHANNEL_ID} not found.")

@bot.event
async def on_member_update(before, after):
    if before.roles != after.roles:
        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added:
            msg = f"Roles added to {after.name}: {', '.join(r.name for r in added)}"
            await send_log_message(msg)
            logging.info(msg)
        if removed:
            msg = f"Roles removed from {after.name}: {', '.join(r.name for r in removed)}"
            await send_log_message(msg)
            logging.info(msg)

@bot.event
async def on_member_join(member):
    msg = f"{member.name} has joined the server."
    await send_log_message(msg)
    logging.info(msg)

@bot.event
async def on_member_remove(member):
    msg = f"{member.name} has left the server."
    await send_log_message(msg)
    logging.info(msg)

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel != after.channel:
        if before.channel is None:
            msg = f"{member.name} has joined the voice channel {after.channel.name}."
        elif after.channel is None:
            msg = f"{member.name} has left the voice channel {before.channel.name}."
        else:
            msg = f"{member.name} has moved from {before.channel.name} to {after.channel.name}."
        await send_log_message(msg)
        logging.info(msg)

@bot.event
async def on_message_edit(before, after):
    if before.content != after.content:
        msg = f"Message edited by {after.author.name} in {after.channel.name}:\n\nBefore: {before.content}\n\nAfter: {after.content}"
        await send_log_message(msg)
        logging.info(msg)

@bot.event
async def on_message_delete(message):
    if isinstance(message.channel, discord.DMChannel):
        msg = f"Message deleted by {message.author.name} in DM:\n\n{message.content}"
    else:
        msg = f"Message deleted by {message.author.name} in {message.channel.name}:\n\n{message.content}"
    await send_log_message(msg)
    logging.info(msg)

@bot.command()
@admin_or_mod()
async def mute(ctx, member: discord.Member, duration: str, *, reason: str = "Не указано"):
    if is_moderator(ctx.author) and has_protected_role(member):
        await ctx.send("Вы не можете замьютить другого модератора или администратора.")
        logging.warning(f"Moderator {ctx.author} tried to mute protected user {member}")
        return

    role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if not role:
        await ctx.send("Роль мьюта не обнаружена. Убедитесь, что ID роли выставлен корректно.")
        return

    duration_seconds = parse_duration(duration)
    if duration_seconds is None:
        await ctx.send("Неверный формат длительности. Используйте формат: 1d, 2h, 30m, 60s.")
        return

    await member.add_roles(role, reason=reason)
    await ctx.send(f'{member.mention} замьючен на {duration}. Причина: {reason}')
    logging.info(f"Muted {member} ({member.id}) for {duration} by {ctx.author} ({ctx.author.id}). Reason: {reason}")
    add_mute(member.id, datetime.now() + timedelta(seconds=duration_seconds), reason)

@mute.error
async def mute_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(_no_permission_message(ctx))
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Неверный аргумент. Использование: `!mute @username длительность причина`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Неверный аргумент. Убедитесь, что верно отмечен пользователь и указано время мьюта.")
    else:
        await ctx.send("Возникла ошибка при мьюте пользователя.")
        logging.error(f"Error in mute command: {error}")


@bot.command()
@admin_or_mod()
async def unmute(ctx, member: discord.Member):
    if is_moderator(ctx.author) and has_protected_role(member):
        await ctx.send("Вы не можете размьютить другого модератора или администратора.")
        return

    role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if role in member.roles:
        await member.remove_roles(role, reason="Ручной анмьют")
        await ctx.send(f'{member.mention} был размьючен.')
        logging.info(f"Unmuted {member} ({member.id}) by {ctx.author} ({ctx.author.id})")
        remove_mute(member.id)
    else:
        await ctx.send(f'{member.mention} не замьючен.')

@unmute.error
async def unmute_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(_no_permission_message(ctx))
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Неверный аргумент. Использование: `!unmute @username`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Неверный аргумент. Убедитесь, что упомянут валидный пользователь.")
    else:
        await ctx.send("Произошла ошибка при попытке анмьюта пользователя.")
        logging.error(f"Error in unmute command: {error}")


@bot.command()
@admin_or_mod()
async def warn(ctx, member: discord.Member, *, reason: str = "Не указано"):
    if is_moderator(ctx.author) and has_protected_role(member):
        await ctx.send("Вы не можете выдать предупреждение другому модератору или администратору.")
        logging.warning(f"Moderator {ctx.author} tried to warn protected user {member}")
        return

    warnings_list = get_warnings(member.id)
    warnings_list = [w for w in warnings_list
                     if datetime.fromisoformat(w['timestamp']) > datetime.now() - timedelta(days=1)]
    add_warning(member.id, reason)
    warnings_list.append({'timestamp': datetime.now().isoformat(), 'reason': reason})

    recent = [w for w in warnings_list
              if datetime.fromisoformat(w['timestamp']) > datetime.now() - timedelta(days=1)]
    if len(recent) >= 3:
        await mute(ctx, member, '24h', reason="3 предупреждения за 24 часа")
        remove_warnings(member.id)
    else:
        await ctx.send(f'{member.mention} получил предупреждение. Причина: {reason}.')
        logging.info(f"Warned {member} ({member.id}) by {ctx.author} ({ctx.author.id}). Reason: {reason}")

@warn.error
async def warn_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(_no_permission_message(ctx))
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Неверный аргумент. Использование: `!warn @username причина`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Неверный аргумент. Убедитесь, что верно отмечен пользователь.")
    else:
        await ctx.send("Возникла ошибка при предупреждении пользователя.")
        logging.error(f"Error in warn command: {error}")


@bot.command()
@admin_or_mod()
async def warnremove(ctx, member: discord.Member):
    if is_moderator(ctx.author) and has_protected_role(member):
        await ctx.send("Вы не можете снять предупреждения с другого модератора или администратора.")
        return

    if get_warnings(member.id):
        remove_warnings(member.id)
        await ctx.send(f'Все предупреждения {member.mention} были удалены.')
        logging.info(f"Removed all warnings for {member} ({member.id}) by {ctx.author} ({ctx.author.id})")
    else:
        await ctx.send(f'У пользователя {member.mention} нет действующих предупреждений.')

@warnremove.error
async def warnremove_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(_no_permission_message(ctx))
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Неверный аргумент. Использование: `!warnremove @username`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Неверный аргумент. Убедитесь, что упомянут валидный пользователь.")
    else:
        await ctx.send("Произошла ошибка при попытке снятия предупреждений пользователя.")
        logging.error(f"Error in warnremove command: {error}")


@bot.command()
@admin_or_mod()
async def warnings(ctx, member: discord.Member):
    warnings_list = get_warnings(member.id)
    if warnings_list:
        warn_messages = [
            f"{datetime.fromisoformat(w['timestamp']).strftime('%d-%m-%Y %H-%M')}: {w['reason']}"
            for w in reversed(warnings_list)
        ]
        await ctx.send(f"Предупреждения для {member.mention}:\n" + "\n".join(warn_messages))
        logging.info(f"Listed warnings for {member.id}")
    else:
        await ctx.send(f'У пользователя {member.mention} нет предупреждений.')

@warnings.error
async def warnings_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(_no_permission_message(ctx))
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Неверный аргумент. Использование: `!warnings @username`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Неверный аргумент. Убедитесь, что упомянут валидный пользователь.")
    else:
        await ctx.send("Произошла ошибка при попытке отображения предупреждений пользователя.")
        logging.error(f"Error in warnings command: {error}")

@bot.command()
@admin_only()
async def mute_all(ctx, *, reason=None):
    role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if not role:
        await ctx.send("Роль мьюта не обнаружена. Убедитесь, что ID роли выставлен корректно.")
        return
    members = ctx.channel.members
    await asyncio.gather(*[m.add_roles(role) for m in members if m != ctx.guild.me])
    await asyncio.sleep(3600)
    await asyncio.gather(*[m.remove_roles(role, reason="Mute time expires") for m in members if m != ctx.guild.me])
    logging.info("Everyone is unmuted.")
    await ctx.send("Все участники канала были размучены.")


@bot.command()
@admin_only()
async def adminmenu(ctx):
    embed = discord.Embed(
        title="Панель администратора",
        description=(
            "**Функции управления ботом:**\n"
            "Проверить YouTube каналы — вручную запустить проверку новых видео.\n"
            "Обновить ID последних видео — обновляет сохранённые ID последних роликов.\n"
            "Перезагрузить бота — безопасно перезапускает процесс (если поддерживается средой).\n"
        ),
        color=discord.Color.gold()
    )
    view = AdminMenuView(ctx)
    await ctx.send(embed=embed, view=view)
    logging.info(f"Admin menu opened by {ctx.author}")

@adminmenu.error
async def adminmenu_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ Эта команда доступна только администраторам.")
    else:
        logging.error(f"Error in adminmenu command: {error}")


@bot.command(name="spamtest")
@admin_only()
async def spamtest(ctx, trigger: str = "multichannel"):
    trigger = trigger.lower().strip()

    if trigger in ("multichannel", "channels"):
        fake_channels = list(range(SPAM_CHANNELS_THRESHOLD))
        now = datetime.now()
        log = user_message_log[ctx.author.id]
        for ch_id in fake_channels:
            log.append((now, ch_id))
        last_spam_alert.pop(ctx.author.id, None)

        await send_spam_alert(
            user=ctx.author,
            reason=f"[ТЕСТ] Сообщения в {len(fake_channels)} каналах за {SPAM_TIME_WINDOW // 60} мин.",
            details=(
                f"Каналы (симуляция): {', '.join(f'`fake_channel_{c}`' for c in fake_channels)}\n"
                f"Сообщений в окне: `{len(fake_channels)}`\n"
                f"*Тестовый вызов командой `!spamtest`.*"
            )
        )
        await ctx.send("Тест **multichannel** выполнен.")
        logging.info(f"[SPAMTEST] multichannel triggered by {ctx.author} ({ctx.author.id})")

    elif trigger == "everyone":
        last_spam_alert.pop(ctx.author.id, None)
        await send_spam_alert(
            user=ctx.author,
            reason="[ТЕСТ] Попытка использовать @everyone / @here без прав",
            details=(
                f"Канал: {ctx.channel.mention}\n"
                f"Текст сообщения:\n```@everyone тестовое сообщение```\n"
                f"*Тестовый вызов командой `!spamtest everyone`.*"
            )
        )
        await ctx.send("Тест **everyone** выполнен.")
        logging.info(f"[SPAMTEST] everyone triggered by {ctx.author} ({ctx.author.id})")

    else:
        await ctx.send(
            "Неизвестный тип теста. Используй:\n"
            "`!spamtest multichannel` — тест мультиканального спама\n"
            "`!spamtest everyone` — тест попытки @everyone"
        )

@spamtest.error
async def spamtest_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("Эта команда доступна только администраторам.")
    else:
        await ctx.send("Произошла ошибка при выполнении теста.")
        logging.error(f"Error in spamtest command: {error}")


@bot.command()
@admin_only()
async def getvideosid(ctx):
    for api_key in YOUTUBE_API_KEYS:
        youtube = get_youtube_service(api_key)
        try:
            for ch_id in (YOUTUBE_CHANNEL_ID_1, YOUTUBE_CHANNEL_ID_2):
                req = youtube.search().list(part="snippet", channelId=ch_id, order="date", maxResults=1)
                resp = req.execute()
                if 'items' in resp and resp['items']:
                    video_id = resp['items'][0]['id']['videoId']
                    if video_id != get_last_video_id(ch_id):
                        logging.info(f"Updated last video ID for {ch_id}: {video_id}")
                        set_last_video_id(ch_id, video_id)
            break
        except googleapiclient.errors.HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e):
                logging.warning(f"Quota exceeded for API key: {api_key}")
            else:
                await ctx.send("An error occurred! Check admin console for more information!")
                logging.error(f"An error occurred (getvideosid): {e}")
                raise e


@bot.command()
@admin_only()
async def check_yt(ctx):
    await check_youtube_channels_manual(ctx)


@bot.command()
@admin_only()
async def send_to_channel(ctx, channel: discord.TextChannel, *, message):
    if ctx.message.attachments:
        for attachment in ctx.message.attachments:
            await attachment.save(attachment.filename)
            await send_message_to_channel(channel, message, attachment.filename)
            os.remove(attachment.filename)
    else:
        await send_message_to_channel(channel, message)

@bot.command()
async def MrCarsen(ctx):
    await ctx.reply(random.choice(mr_carsen_messages))
    logging.info(f"Sent MrCarsen message to {ctx.author.id}")

@bot.command()
async def золотойфонд(ctx):
    await ctx.reply(random.choice(gold_fund_messages))
    logging.info(f"Sent gold fund message to {ctx.author.id}")

@bot.command()
async def неумничай(ctx):
    await ctx.reply('Да пошёл ты нахуй!')

@bot.command()
async def аможетбытьты(ctx):
    await ctx.reply('КТО?! Я?!')

@bot.command()
@admin_only()
async def ахуйтебе(ctx):
    await ctx.reply('Сукпыздыц((9(((')

@bot.command()
async def пошёлтынахуй(ctx):
    await ctx.reply('Та за що, плять?..')

@bot.command()
async def рулетка(ctx):
    died = random.randint(1, 6)
    if died == 6:
        await ctx.reply("БАБАХ! You are dead. Not a big surprise. ☠️")
        role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
        if role:
            await ctx.author.add_roles(role, reason="Русская рулетка")
            logging.info(f"{ctx.author.id} lost the roulette and was muted for 1 minute")
            await asyncio.sleep(60)
            await ctx.author.remove_roles(role, reason="Время мьюта истекло")
    else:
        await ctx.reply("**·щёлк·**\nФартовый однако! 🤔")
        logging.info(f"{ctx.author.id} won the roulette")

@bot.command()
async def ХУЯБЛЯ(ctx):
    await ctx.reply("БАН!")
    role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if role:
        await ctx.author.add_roles(role, reason="Допизделся, дядя!")
        await asyncio.sleep(60)
        await ctx.author.remove_roles(role, reason="Время мьюта истекло")
    logging.info(f"{ctx.author.id} triggered the ХУЯБЛЯ command and was muted for 1 minute")

@bot.command(name='help', aliases=['помощь'])
async def помощь(ctx):
    await ctx.send(
        "**Здарова, салаги!**\n"
        "Данный бот может много чего. Прислать уведомление о новом видео, замутить вас или же позабавить своими командами!\n"
        "\n"
        "Доступные команды:\n"
        "\n"
        "- `!MrCarsen` - содержит все так называемые \"Цытаты виликих\" из модификаций данного товарища.\n"
        "\n"
        "- `!золотойфонд` - выдаёт случайное сообщение из золотого фонда.\n"
        "\n"
        "- `!неумничай` - если кто-то слишком сильно умничает. В ответ на неё бот пошлёт вас на три буквы.\n"
        "Однако вы можете ответить ему командой `!аможетбытьты`, получив в ответ \"КТО?! Я?!\".\n"
        "Написав команду `!ХУЯБЛЯ` бот включает режим Глада Валакаса и отправляет вас в бан. На целую минуту.\n"
        "\n"
        "- `!пошёлтынахуй` - позволяет послать собеседника куда подальше, но бот воспримет это на свой счёт, учтите.\n"
        "||на самом деле ничего не будет и он просто спросит за что вы так с ним||\n"
        "\n"
        "- `!рулетка` - своеобразная 'Русская рулетка'. Либо жив, либо умер. В случае \"смерти\" получаете мьют на минуту.\n"
        "\n"
        "- `!bomb` - своеобразная бомба. Участникам чата даётся 1 час на её разминирование. Если никто не успеет - все участники чата получают мьют на 1 час.\n"
        "Команду можно использовать 1 раз в 7 дней.\n"
        "\n"
        "- `!defuse` - разминирование запущенной \"бомбы\". После команды нужно ввести ваш вариант в виде 4-ёх числового кода.\n"
        "Пример: `!defuse 1432`\n"
        "\n"
        "В будущем планируется расширение функционала по части команд, так что следите за обновлениями!"
    )
    logging.info(f"Sent help message to {ctx.author.id}")

@bot.command()
async def bomb(ctx):
    cooldown_end_time = get_bomb_cooldown(ctx.guild.id)
    if cooldown_end_time:
        cooldown_end_time = datetime.fromisoformat(cooldown_end_time)
        if cooldown_end_time > datetime.now():
            retry_after = (cooldown_end_time - datetime.now()).total_seconds()
            days, rem = divmod(int(retry_after), 86400)
            hours, rem = divmod(rem, 3600)
            minutes = rem // 60
            parts = []
            if days: parts.append(f"{days} дней")
            if hours: parts.append(f"{hours} часов")
            if minutes: parts.append(f"{minutes} минут")
            await ctx.send(f"Команда недоступна! Попробуйте ещё раз через {' '.join(parts)}.")
            return

    view = ConfirmView(ctx)
    confirmation_message = await ctx.send(f"{ctx.author.mention}, подтвердите действие:", view=view)
    view.message = confirmation_message
    await view.wait()

    if view.value is False:
        await ctx.send("Действие отменено.")
        remove_bomb_cooldown(ctx.guild.id)
        await confirmation_message.delete()
        return
    elif view.value is None:
        await ctx.send("Время вышло. Действие отменено.")
        remove_bomb_cooldown(ctx.guild.id)
        await confirmation_message.delete()
        return

    number = random.randint(1000, 2000)
    number_str = str(number)
    masked_number = f"{number_str[0]}X{number_str[2]}X"

    bomb_info[ctx.guild.id] = {'number': number, 'end_time': datetime.now() + timedelta(hours=1)}

    await ctx.send(
        f"**Bomb has been planted.**\nПользователь {ctx.author.mention} заложил бомбу в чате!\n\n"
        f"Для разминирования нужно вписать команду `!defuse` и ваш вариант. Например: `!defuse 1723`.\n"
        f"**На разминирование даётся 60 минут!**\n\nПодсказка: {masked_number}."
    )
    logging.info(f"Bomb planted by {ctx.author}. Mask: {masked_number}. Password: {number}")
    set_bomb_cooldown(ctx.guild.id, datetime.now() + timedelta(days=7))

    await asyncio.sleep(3600)
    if ctx.guild.id in bomb_info and bomb_info[ctx.guild.id]['end_time'] <= datetime.now():
        await ctx.send("Terrorist win! Время вышло! Все участники чата были замьючены на 1 час.")
        await mute_all(ctx, reason="Bomb exploded")

@bot.command()
async def defuse(ctx, guess: int):
    if ctx.guild.id in bomb_info:
        number = bomb_info[ctx.guild.id]['number']
        if guess == number:
            await ctx.send(f"Bomb has been defused! Пользователь {ctx.author.mention} угадал код и спас чат!")
            logging.info(f"Bomb defused by {ctx.author}. Number: {number}")
            del bomb_info[ctx.guild.id]
        else:
            await ctx.send("Неверно! Попробуйте ещё раз!")
    else:
        await ctx.send("No bomb has been planted.")

class ConfirmView(View):
    def __init__(self, ctx):
        super().__init__(timeout=15)
        self.ctx = ctx
        self.value = None

    @discord.ui.button(label="✅", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user == self.ctx.author:
            self.value = True
            self.stop()
            await self.message.delete()

    @discord.ui.button(label="🚫", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user == self.ctx.author:
            self.value = False
            self.stop()


class AdminMenuView(View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="Проверить YouTube каналы", style=discord.ButtonStyle.blurple, custom_id="check_yt_btn")
    async def check_yt_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("Проверяю YouTube каналы...", ephemeral=True)
            await check_youtube_channels_manual(interaction)
        else:
            await interaction.response.send_message("У вас нет прав для этого действия.", ephemeral=True)

    @discord.ui.button(label="Обновить ID последних видео", style=discord.ButtonStyle.green, custom_id="update_ids_btn")
    async def update_ids_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("Обновляю ID последних видео...", ephemeral=True)
            ctx = await bot.get_context(interaction.message)
            await getvideosid(ctx)
        else:
            await interaction.response.send_message("У вас нет прав для этого действия.", ephemeral=True)

    @discord.ui.button(label="Перезагрузить бота", style=discord.ButtonStyle.red, custom_id="restart_btn")
    async def restart_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("Перезагрузка бота...", ephemeral=True)
            logging.info(f"Bot restarting by {interaction.user}")
            await asyncio.sleep(2)
            os.execv(sys.executable, ['python'] + sys.argv)
        else:
            await interaction.response.send_message("У вас нет прав для этого действия.", ephemeral=True)


class SubscribeView(View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.role_id = role_id
        self.add_role_button = Button(label="Получить роль", style=discord.ButtonStyle.green,
                                      custom_id=f"subscribe_add_{role_id}")
        self.add_role_button.callback = self.add_role_callback
        self.remove_role_button = Button(label="Отказаться от роли", style=discord.ButtonStyle.red,
                                         custom_id=f"subscribe_remove_{role_id}")
        self.remove_role_button.callback = self.remove_role_callback
        self.add_item(self.add_role_button)
        self.add_item(self.remove_role_button)

    async def add_role_callback(self, interaction: discord.Interaction):
        await self.update_role(interaction, add=True)

    async def remove_role_callback(self, interaction: discord.Interaction):
        await self.update_role(interaction, add=False)

    async def update_role(self, interaction: discord.Interaction, add: bool):
        try:
            role = discord.utils.get(interaction.guild.roles, id=self.role_id)
            if role is None:
                await interaction.response.send_message("Роль не найдена!", ephemeral=True)
                return
            if add:
                if role not in interaction.user.roles:
                    await interaction.user.add_roles(role)
                    self._add_user_to_db(interaction.user.id, self.role_id)
                    await interaction.response.send_message(f"Вам выдана роль {role.name}!", ephemeral=True)
                    logging.info(f"Added role {role.id} to user {interaction.user.id}")
                else:
                    await interaction.response.send_message(f"У вас уже есть роль {role.name}.", ephemeral=True)
            else:
                if role in interaction.user.roles:
                    await interaction.user.remove_roles(role)
                    self._remove_user_from_db(interaction.user.id)
                    await interaction.response.send_message(f"Роль {role.name} удалена.", ephemeral=True)
                    logging.info(f"Removed role {role.id} from user {interaction.user.id}")
                else:
                    await interaction.response.send_message(f"У вас нет роли {role.name}.", ephemeral=True)
        except Exception as e:
            logging.error(f"Error in SubscribeView: {e}", exc_info=True)
            await interaction.response.send_message("Произошла ошибка!", ephemeral=True)

    def _add_user_to_db(self, user_id, role_id):
        conn = sqlite3.connect('bot_data.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO role_users (user_id, role_id) VALUES (?, ?)", (user_id, role_id))
        conn.commit()
        conn.close()

    def _remove_user_from_db(self, user_id):
        conn = sqlite3.connect('bot_data.db')
        c = conn.cursor()
        c.execute("DELETE FROM role_users WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()


@bot.command()
@commands.has_permissions(manage_roles=True)
async def subscribe(ctx):
    role = discord.utils.get(ctx.guild.roles, id=YT_SUBSCRIBER_ROLE_ID)
    if not role:
        await ctx.send("Роль для подписки не найдена!")
        return
    view = SubscribeView(YT_SUBSCRIBER_ROLE_ID)
    embed = discord.Embed(
        title=f"Подписка на уведомления {role.name}",
        description=f"Нажмите кнопку ниже, чтобы получать или отключить уведомления для роли {role.mention}\n\n",
        color=role.color
    )
    await ctx.send(embed=embed, view=view)

@bot.command()
@commands.has_permissions(manage_roles=True)
async def subscribesecond(ctx):
    role = discord.utils.get(ctx.guild.roles, id=SEC_YT_SUBSCRIBER_ROLE_ID)
    if not role:
        await ctx.send("Роль для подписки не найдена!")
        return
    view = SubscribeView(SEC_YT_SUBSCRIBER_ROLE_ID)
    embed = discord.Embed(
        title=f"Подписка на уведомления {role.name}",
        description=f"Нажмите кнопку ниже, чтобы получать или отключить уведомления для роли {role.mention}\n\n",
        color=role.color
    )
    await ctx.send(embed=embed, view=view)

async def send_message_to_channel(channel, message, file_path=None):
    try:
        if file_path:
            await channel.send(message, file=discord.File(file_path))
        else:
            await channel.send(message)
    except Exception as e:
        logging.error(f"Ошибка при отправке сообщения: {e}")

async def check_youtube_channels_manual(ctx):
    channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
    if not channel:
        await ctx.send("Notification channel not found.")
        logging.error("Notification channel not found")
        return

    for api_key in YOUTUBE_API_KEYS:
        youtube = get_youtube_service(api_key)
        try:
            req = youtube.search().list(part="snippet", channelId=YOUTUBE_CHANNEL_ID_1, order="date", maxResults=1)
            resp = req.execute()
            if 'items' in resp and resp['items']:
                video_id = resp['items'][0]['id']['videoId']
                if video_id != get_last_video_id(YOUTUBE_CHANNEL_ID_1):
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    await channel.send(f"<@&1104385788797534228>\nНа канале какая-то движуха. А ну-ка глянем: {video_url}")
                    set_last_video_id(YOUTUBE_CHANNEL_ID_1, video_id)
                    logging.info(f"New video on channel 1: {video_url}")

            req = youtube.search().list(part="snippet", channelId=YOUTUBE_CHANNEL_ID_2, order="date", maxResults=1)
            resp = req.execute()
            if 'items' in resp and resp['items']:
                video_id = resp['items'][0]['id']['videoId']
                if video_id != get_last_video_id(YOUTUBE_CHANNEL_ID_2):
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    await channel.send(f"<@&1265571159601319989>\nНа втором канале что-то появилось. Давайте-ка заценим: {video_url}")
                    set_last_video_id(YOUTUBE_CHANNEL_ID_2, video_id)
                    logging.info(f"New video on channel 2: {video_url}")

            await ctx.send("YouTube channels checked successfully.")
            logging.info("YouTube channels checked successfully")
            break
        except googleapiclient.errors.HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e):
                logging.warning(f"Quota exceeded for API key: {api_key}")
            else:
                await ctx.send("An error occurred! Check admin console for more information!")
                logging.error(f"An error occurred (check_youtube_channels_manual): {e}")
                raise e

@tasks.loop(minutes=1)
async def check_mutes():
    current_time = datetime.now()
    for user_id, mute_info in list(get_mutes().items()):
        if current_time >= datetime.fromisoformat(mute_info['end_time']):
            guild = bot.get_guild(YOUR_ADMIN_ROLE_ID)
            member = guild.get_member(user_id)
            if member:
                role = discord.utils.get(guild.roles, id=MUTE_ROLE_ID)
                if role in member.roles:
                    await member.remove_roles(role, reason="Длительность мьюта вышла.")
                    remove_mute(user_id)
                    logging.info(f"Unmuted {user_id} as mute duration expired")


bot.run(DISCORD_TOKEN)