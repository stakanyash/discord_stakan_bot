import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import asyncio
from datetime import datetime, timedelta
import random
import googleapiclient.discovery
import googleapiclient.errors
from dotenv import load_dotenv
import os
import logging
import sqlite3
import requests
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
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_CHANNEL_ID = int(os.getenv("TWITCH_CHANNEL_ID"))
USER_ID = int(os.getenv("USER_ID"))

def create_tables():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS warnings (
                  user_id INTEGER,
                  timestamp TEXT,
                  reason TEXT
               )''')
    c.execute('''CREATE TABLE IF NOT EXISTS mutes (
                  user_id INTEGER,
                  end_time TEXT,
                  reason TEXT
               )''')
    c.execute('''CREATE TABLE IF NOT EXISTS bomb_cooldowns (
                  guild_id INTEGER PRIMARY KEY,
                  end_time TEXT
               )''')
    c.execute('''CREATE TABLE IF NOT EXISTS last_video_ids (
                  channel_id TEXT PRIMARY KEY,
                  video_id TEXT
               )''')
    c.execute('''CREATE TABLE IF NOT EXISTS role_users (
                  user_id INTEGER PRIMARY KEY,
                  role_id INTEGER
               )''')
    c.execute('''CREATE TABLE IF NOT EXISTS active_streams (
                  channel_id TEXT PRIMARY KEY,
                  stream_url TEXT,
                  notification_sent BOOLEAN
               )''')

    c.execute("PRAGMA table_info(active_streams)")
    columns = c.fetchall()
    column_names = [column[1] for column in columns]

    if 'notification_sent' not in column_names:
        c.execute('''ALTER TABLE active_streams ADD COLUMN notification_sent BOOLEAN''')

    conn.commit()
    conn.close()

create_tables()

def get_warnings(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, reason FROM warnings WHERE user_id = ?", (user_id,))
    warnings = c.fetchall()
    conn.close()
    return [{'timestamp': warning[0], 'reason': warning[1]} for warning in warnings]

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
    return {mute[0]: {'end_time': mute[1], 'reason': mute[2]} for mute in mutes}

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
    c.execute("INSERT OR REPLACE INTO bomb_cooldowns (guild_id, end_time) VALUES (?, ?)", (guild_id, end_time.isoformat()))
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
    c.execute("INSERT OR REPLACE INTO last_video_ids (channel_id, video_id) VALUES (?, ?)", (channel_id, video_id))
    conn.commit()
    conn.close()

def get_role_users(role_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM role_users WHERE role_id = ?", (role_id,))
    users = c.fetchall()
    conn.close()
    return [user[0] for user in users]

def get_active_stream(channel_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT stream_url, notification_sent FROM active_streams WHERE channel_id = ?", (channel_id,))
    result = c.fetchone()
    conn.close()
    return result if result else (None, False)

def set_active_stream(channel_id, stream_url, notification_sent=False):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO active_streams (channel_id, stream_url, notification_sent) VALUES (?, ?, ?)", (channel_id, stream_url, notification_sent))
    conn.commit()
    conn.close()

def remove_active_stream(channel_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("DELETE FROM active_streams WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()

def get_twitch_access_token(client_id, client_secret):
    url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'client_credentials'
    }
    response = requests.post(url, params=params)
    response.raise_for_status()
    return response.json()['access_token']

async def send_dm_notification(user, ctx, role_id_1, role_id_2, stream_url):
    view = RoleSelectionView(ctx, role_id_1, role_id_2, stream_url)
    message = await user.send(
        "Обнаружен стрим на Twitch. Какую роль следует пинговать?",
        view=view
    )
    view.message = message

class RoleSelectionView(View):
    def __init__(self, ctx, role_id_1, role_id_2, stream_url):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.role_id_1 = role_id_1
        self.role_id_2 = role_id_2
        self.stream_url = stream_url
        self.value = None
        self.message = None
        self.notification_sent = False

    @discord.ui.button(label="YouTube Subscriber", style=discord.ButtonStyle.green)
    async def select_role_1(self, interaction: discord.Interaction, button: Button):
        await self.select_role(interaction, self.role_id_1)

    @discord.ui.button(label="Second YT Sub", style=discord.ButtonStyle.red)
    async def select_role_2(self, interaction: discord.Interaction, button: Button):
        await self.select_role(interaction, self.role_id_2)

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        self.value = None
        self.stop()
        await interaction.response.send_message(f"Отправка уведомления отменена.", ephemeral=True)
        if self.message:
            await self.message.delete()

    async def select_role(self, interaction: discord.Interaction, role_id):
        self.value = role_id
        self.stop()
        await interaction.response.send_message(f"Вы выбрали роль для уведомления.", ephemeral=True)
        if self.message:
            await self.message.delete()

async def check_twitch_streams(ctx, client_id, client_secret, twitch_channel_id, notification_channel_id, user_id):
    token = get_twitch_access_token(client_id, client_secret)
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {token}'
    }
    url = f'https://api.twitch.tv/helix/streams?user_id={twitch_channel_id}'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()

    if data['data']:
        stream = data['data'][0]
        stream_url = f"https://www.twitch.tv/{stream['user_name']}"
        active_stream, notification_sent = get_active_stream(twitch_channel_id)

        if not active_stream or active_stream != stream_url:
            user = bot.get_user(user_id)
            if user:
                view = RoleSelectionView(ctx, YT_SUBSCRIBER_ROLE_ID, SEC_YT_SUBSCRIBER_ROLE_ID, stream_url)
                await user.send(
                    "Обнаружен стрим на Twitch. Какую роль следует пинговать?",
                    view=view
                )
                await view.wait()
                if view.value:
                    channel = bot.get_channel(notification_channel_id)
                    if channel and not notification_sent:
                        await channel.send(f"<@&{view.value}>\n\nНачалась трансляция на Twitch!\nСмотрите здесь: {stream_url}")
                        logging.info(f"Live stream detected on Twitch: {stream_url}")
                        set_active_stream(twitch_channel_id, stream_url, notification_sent=True)
                    else:
                        logging.error("Notification channel not found")
                else:
                    logging.warning("No role selected for notification")
            else:
                logging.error("User not found")
    else:
        remove_active_stream(twitch_channel_id)
        logging.info("No live streams found on Twitch")

@tasks.loop(minutes=1)
async def check_twitch_streams_task():
    ctx = None
    await check_twitch_streams(ctx, TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, TWITCH_CHANNEL_ID, NOTIFICATION_CHANNEL_ID, USER_ID)

@bot.event
async def on_ready():
    logging.info(f'Logged in as {bot.user}')

    bot.add_view(SubscribeView(YT_SUBSCRIBER_ROLE_ID))
    bot.add_view(SubscribeView(SEC_YT_SUBSCRIBER_ROLE_ID))
    
    check_mutes.start()
#   check_twitch_streams_task.start()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if isinstance(message.channel, discord.DMChannel):
        response = ("Данный бот может работать только на сервере \"стакан\". "
                    "Взаимодействие через личные сообщения не предусмотрено.")
        await message.author.send(response)

    await bot.process_commands(message)

async def send_log_message(message):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        message_parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for part in message_parts:
            await channel.send(part)
    else:
        logging.error(f"Log channel with ID {LOG_CHANNEL_ID} not found.")

@bot.event
async def on_member_update(before, after):
    if before.roles != after.roles:
        added_roles = [role for role in after.roles if role not in before.roles]
        removed_roles = [role for role in before.roles if role not in after.roles]
        if added_roles:
            message = f"Roles added to {after.name}: {', '.join([role.name for role in added_roles])}"
            await send_log_message(message)
            logging.info(message)
        if removed_roles:
            message = f"Roles removed from {after.name}: {', '.join([role.name for role in removed_roles])}"
            await send_log_message(message)
            logging.info(message)

@bot.event
async def on_member_join(member):
    message = f"{member.name} has joined the server."
    await send_log_message(message)
    logging.info(message)

@bot.event
async def on_member_remove(member):
    message = f"{member.name} has left the server."
    await send_log_message(message)
    logging.info(message)

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel != after.channel:
        if before.channel is None:
            message = f"{member.name} has joined the voice channel {after.channel.name}."
            await send_log_message(message)
            logging.info(message)
        elif after.channel is None:
            message = f"{member.name} has left the voice channel {before.channel.name}."
            await send_log_message(message)
            logging.info(message)
        else:
            message = f"{member.name} has moved from {before.channel.name} to {after.channel.name}."
            await send_log_message(message)
            logging.info(message)

@bot.event
async def on_message_edit(before, after):
    if before.content != after.content:
        message = f"Message edited by {after.author.name} in {after.channel.name}:\n\nBefore: {before.content}\n\nAfter: {after.content}"
        await send_log_message(message)
        logging.info(message)

@bot.event
async def on_message_delete(message):
    if isinstance(message.channel, discord.DMChannel):
        message_content = f"Message deleted by {message.author.name} in DM:\n\n{message.content}"
    else:
        message_content = f"Message deleted by {message.author.name} in {message.channel.name}:\n\n{message.content}"

    await send_log_message(message_content)
    logging.info(message_content)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def mute(ctx, member: discord.Member, duration: str, *, reason: str = "Не указано"):
    role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if not role:
        await ctx.send("Роль мьюта не обнаружена. Убедитель, что ID роли выставлен корректно.")
        logging.warning(f"Mute role not found for guild {ctx.guild.id}")
        return

    duration_seconds = parse_duration(duration)
    if duration_seconds is None:
        await ctx.send("Неверный формат длительности. Используйте формат: 1d, 2h, 30m, 60s.")
        logging.warning(f"Invalid duration format: {duration}")
        return

    await member.add_roles(role, reason=reason)
    await ctx.send(f'{member.mention} замьючен на {duration}. Причина: {reason}')
    logging.info(f"Muted {member.id} for {duration}. Reason: {reason}")

    add_mute(member.id, datetime.now() + timedelta(seconds=duration_seconds), reason)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def unmute(ctx, member: discord.Member):
    role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if role in member.roles:
        await member.remove_roles(role, reason="Ручной анмьют")
        await ctx.send(f'{member.mention} был размьючен.')
        logging.info(f"Unmuted {member.id}")
        remove_mute(member.id)
    else:
        await ctx.send(f'{member.mention} не замьючен.')
        logging.warning(f"{member.id} is not muted")

@bot.command()
async def MrCarsen(ctx):
    message = random.choice(mr_carsen_messages)
    await ctx.reply(message)
    logging.info(f"Sent MrCarsen message to {ctx.author.id}")

@bot.command()
async def золотойфонд(ctx):
    message = random.choice(gold_fund_messages)
    await ctx.reply(message)
    logging.info(f"Sent gold fund message to {ctx.author.id}")

@bot.command()
async def неумничай(ctx):
    await ctx.reply('Да пошёл ты нахуй!')
    logging.info(f"Sent 'неумничай' message to {ctx.author.id}")

@bot.command()
async def аможетбытьты(ctx):
    await ctx.reply('КТО?! Я?!')
    logging.info(f"Sent 'аможетбытьты' message to {ctx.author.id}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def ахуйтебе(ctx):
    await ctx.reply('Сукпыздыц((9(((')
    logging.info(f"Sent 'ахуйтебе' message to {ctx.author.id}")

@bot.command()
async def пошёлтынахуй(ctx):
    await ctx.reply('Та за що, плять?..')
    logging.info(f"Sent 'пошёлтынахуй' message to {ctx.author.id}")

@bot.command()
async def рулетка(ctx):
    died = random.randint(1, 6)
    if died == 6:
        await ctx.reply("БАБАХ! You are dead. Not a big surprise. ☠️")
        role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
        if role:
            await ctx.author.add_roles(role, reason="Русская рулетка")
            logging.info(f"{ctx.author.id} lost the roulette and was muted for 1 minute")
            logging.info(f"Random number was: {died}")
            await asyncio.sleep(60)
            await ctx.author.remove_roles(role, reason="Время мьюта истекло")
    else:
        await ctx.reply("**·щёлк·**\nФартовый однако! 🤔")
        logging.info(f"{ctx.author.id} won the roulette")
        logging.info(f"Random number was: {died}")

@bot.command(name='help', aliases=['помощь'])
async def помощь(ctx):
    help_message = (
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
    await ctx.send(help_message)
    logging.info(f"Sent help message to {ctx.author.id}")

@bot.command()
async def ХУЯБЛЯ(ctx):
    await ctx.reply("БАН!")
    role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if role:
        await ctx.author.add_roles(role, reason="Допизделся, дядя!")
        await asyncio.sleep(60)
        await ctx.author.remove_roles(role, reason="Время мьюта истекло")
    logging.info(f"{ctx.author.id} triggered the ХУЯБЛЯ command and was muted for 1 minute")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def mute_all(ctx, *, reason=None):
    role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if not role:
        await ctx.send("Роль мьюта не обнаружена. Убедитель, что ID роли выставлен корректно.")
        logging.warning(f"Mute role not found for guild {ctx.guild.id}")
        return

    members = ctx.channel.members

    tasks = []
    for member in members:
        if member != ctx.guild.me:
            tasks.append(member.add_roles(role))

    await asyncio.gather(*tasks)
    await asyncio.sleep(3600)

    tasks = []
    for member in members:
        if member != ctx.guild.me:
            tasks.append(member.remove_roles(role, reason="Mute time expires"))
            logging.info(f"Everyone is unmuted.")

    await asyncio.gather(*tasks)
    await ctx.send("Все участники канала были размучены.")

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

@bot.command()
async def bomb(ctx):
    cooldown_end_time = get_bomb_cooldown(ctx.guild.id)
    if cooldown_end_time:
        cooldown_end_time = datetime.fromisoformat(cooldown_end_time)
        if cooldown_end_time > datetime.now():
            retry_after = (cooldown_end_time - datetime.now()).total_seconds()
            days = int(retry_after // 86400)
            remainder = retry_after % 86400
            hours = int(remainder // 3600)
            remainder %= 3600
            minutes = int(remainder // 60)

            time_parts = []
            if days > 0:
                time_parts.append(f"{days} дней")
            if hours > 0:
                time_parts.append(f"{hours} часов")
            if minutes > 0:
                time_parts.append(f"{minutes} минут")

            time_str = " ".join(time_parts)

            await ctx.send(f"Команда недоступна! Попробуйте ещё раз через {time_str}.")
            logging.warning(f"Command !bomb called on cooldown. Remaining cooldown: {time_str}")
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

    bomb_info[ctx.guild.id] = {
        'number': number,
        'end_time': datetime.now() + timedelta(hours=1)
    }

    await ctx.send(f"**Bomb has been planted.**\nПользователь {ctx.author.mention} заложил бомбу в чате!\n\n\nДля разминирования нужно вписать команду `!defuse` и ваш вариант. Например: `!defuse 1723`.\n**На разминирование даётся 60 минут!**\n\nПодсказка: {masked_number}.")
    logging.info(f"Bomb has been planted by {ctx.author}.\nMask: {masked_number}.\nPassword is: {number}")

    set_bomb_cooldown(ctx.guild.id, datetime.now() + timedelta(days=7))

    await asyncio.sleep(3600)

    if ctx.guild.id in bomb_info and bomb_info[ctx.guild.id]['end_time'] <= datetime.now():
        await ctx.send("Terrorist win! Время вышло! Все участники чата были замьючены на 1 час.")
        await mute_all(ctx, reason="Bomb exploded")
        logging.info(f"Time on !bomb command action expires. Everyone is muted for 1 hour.")

@bot.command()
async def defuse(ctx, guess: int):
    if ctx.guild.id in bomb_info:
        number = bomb_info[ctx.guild.id]['number']
        if guess == number:
            await ctx.send(f"Bomb has been defused! Пользователь {ctx.author.mention} угадал код и спас чат!")
            logging.info(f"Bomb has been defused by {ctx.author}.\nGenerated number: {number}")
            del bomb_info[ctx.guild.id]
        else:
            await ctx.send("Неверно! Попробуйте ещё раз!")
    else:
        await ctx.send("No bomb has been planted.")

class SubscribeView(View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.role_id = role_id

        self.add_role_button = Button(
            label="Получить роль",
            style=discord.ButtonStyle.green,
            custom_id=f"subscribe_add_{role_id}"
        )
        self.add_role_button.callback = self.add_role_callback

        self.remove_role_button = Button(
            label="Отказаться от роли",
            style=discord.ButtonStyle.red,
            custom_id=f"subscribe_remove_{role_id}"
        )
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
                await interaction.response.send_message(
                    "Роль не найдена!",
                    ephemeral=True
                )
                logging.error(f"Role {self.role_id} not found in guild {interaction.guild.id}")
                return

            if add:
                if role not in interaction.user.roles:
                    await interaction.user.add_roles(role)
                    self.add_user_to_db(interaction.user.id, self.role_id)
                    await interaction.response.send_message(
                        f"Вам выдана роль {role.name}!",
                        ephemeral=True
                    )
                    logging.info(f"Added role {role.id} to user {interaction.user.id}")
                else:
                    await interaction.response.send_message(
                        f"У вас уже есть роль {role.name}.",
                        ephemeral=True
                    )
            else:
                if role in interaction.user.roles:
                    await interaction.user.remove_roles(role)
                    self.remove_user_from_db(interaction.user.id)
                    await interaction.response.send_message(
                        f"Роль {role.name} удалена.",
                        ephemeral=True
                    )
                    logging.info(f"Removed role {role.id} from user {interaction.user.id}")
                else:
                    await interaction.response.send_message(
                        f"У вас нет роли {role.name}.",
                        ephemeral=True
                    )
        except Exception as e:
            logging.error(f"Error in SubscribeView: {str(e)}", exc_info=True)
            await interaction.response.send_message(
                "Произошла ошибка!",
                ephemeral=True
            )

    def add_user_to_db(self, user_id, role_id):
        conn = sqlite3.connect('bot_data.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO role_users (user_id, role_id) VALUES (?, ?)", (user_id, role_id))
        conn.commit()
        conn.close()

    def remove_user_from_db(self, user_id):
        conn = sqlite3.connect('bot_data.db')
        c = conn.cursor()
        c.execute("DELETE FROM role_users WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

@bot.command()
@commands.has_permissions(manage_roles=True)
async def subscribe(ctx):
    role_id = YT_SUBSCRIBER_ROLE_ID
    role = discord.utils.get(ctx.guild.roles, id=role_id)
    
    if not role:
        await ctx.send("Роль для подписки не найдена!")
        return

    view = SubscribeView(role_id)
    embed = discord.Embed(
        title=f"Подписка на уведомления {role.name}",
        description=(
            f"Нажмите кнопку ниже, чтобы получать или отключить уведомления "
            f"для роли {role.mention}\n\n"
        ),
        color=role.color
    )
    await ctx.send(embed=embed, view=view)

@bot.command()
@commands.has_permissions(manage_roles=True)
async def subscribesecond(ctx):
    role_id = SEC_YT_SUBSCRIBER_ROLE_ID
    role = discord.utils.get(ctx.guild.roles, id=role_id)
    
    if not role:
        await ctx.send("❌ Роль для подписки не найдена!")
        return

    view = SubscribeView(role_id)
    embed = discord.Embed(
        title=f"Подписка на уведомления {role.name}",
        description=(
            f"Нажмите кнопку ниже, чтобы получать или отключить уведомления "
            f"для роли {role.mention}\n\n"
        ),
        color=role.color
    )
    await ctx.send(embed=embed, view=view)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason: str = "Не указано"):
    warnings_list = get_warnings(member.id)
    warnings_list = [w for w in warnings_list if datetime.fromisoformat(w['timestamp']) > datetime.now() - timedelta(days=1)]

    add_warning(member.id, reason)
    warnings_list.append({'timestamp': datetime.now().isoformat(), 'reason': reason})

    recent_warnings = [w for w in warnings_list if datetime.fromisoformat(w['timestamp']) > datetime.now() - timedelta(days=1)]
    if len(recent_warnings) >= 3:
        await mute(ctx, member, '24h', reason="3 предупреждения за 24 часа")
        remove_warnings(member.id)
    else:
        await ctx.send(f'{member.mention} получил предупреждение. Причина: {reason}.')
        logging.info(f"Warned {member.id}. Reason: {reason}")

async def send_message_to_channel(channel, message, file_path=None):
    try:
        if file_path:
            file = discord.File(file_path)
            await channel.send(message, file=file)
            print(f"Сообщение с файлом успешно отправлено в канал {channel.name}")
        else:
            await channel.send(message)
            print(f"Сообщение успешно отправлено в канал {channel.name}")
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def send_to_channel(ctx, channel: discord.TextChannel, *, message):
    if ctx.message.attachments:
        for attachment in ctx.message.attachments:
            await attachment.save(attachment.filename)
            await send_message_to_channel(channel, message, attachment.filename)
            import os
            os.remove(attachment.filename)
    else:
        await send_message_to_channel(channel, message)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warnremove(ctx, member: discord.Member):
    if get_warnings(member.id):
        remove_warnings(member.id)
        await ctx.send(f'Все предупреждения {member.mention} были удалены.')
        logging.info(f"Removed all warnings for {member.id}")
    else:
        await ctx.send(f'У пользователя {member.mention} нет действующих предупреждений.')
        logging.warning(f"No active warnings for {member.id}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warnings(ctx, member: discord.Member):
    warnings_list = get_warnings(member.id)
    if warnings_list:
        warn_messages = [f"{datetime.fromisoformat(w['timestamp']).strftime('%d-%m-%Y %H-%M')}: {w['reason']}" for w in warnings_list]
        warn_messages.reverse()
        await ctx.send(f"Предупреждения для {member.mention}:\n" + "\n".join(warn_messages))
        logging.info(f"Listed warnings for {member.id}")
    else:
        await ctx.send(f'У пользователя {member.mention} нет предупреждений.')
        logging.warning(f"No warnings for {member.id}")

@warnremove.error
async def warnremove_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Неверный аргумент. Использование: `!warnremove @username`")
        logging.error(f"Missing required argument for warnremove command: {error}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Неверный аргумент. Убедитесь, что упомянут валидный пользователь.")
        logging.error(f"Bad argument for warnremove command: {error}")
    else:
        await ctx.send("Произошла ошибка при попытке снятия предупреждений пользователя.")
        logging.error(f"Error in warnremove command: {error}")

@warn.error
async def warn_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Неверный аргумент. Использование: `!warn @username причина`")
        logging.error(f"Missing required argument for warn command: {error}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Неверный аргумент. Убедитесь, что верно отмечен пользователь")
        logging.error(f"Bad argument for warn command: {error}")
    else:
        await ctx.send("Возникла ошибка при предупреждении пользователя.")
        logging.error(f"Error in warn command: {error}")

@mute.error
async def mute_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Неверный аргумент. Использование: `!mute @username длительность причина`")
        logging.error(f"Missing required argument for mute command: {error}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Неверный аргумент. Убедитесь, что верно отмечен пользователь, указано время мьюта в минутах.")
        logging.error(f"Bad argument for mute command: {error}")
    else:
        await ctx.send("Возникла ошибка при мьюте пользователя.")
        logging.error(f"Error in mute command: {error}")

@unmute.error
async def unmute_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Неверный аргумент. Использование: `!unmute @username`")
        logging.error(f"Missing required argument for unmute command: {error}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Неверный аргумент. Убедитесь, что упомянут валидный пользователь.")
        logging.error(f"Bad argument for unmute command: {error}")
    else:
        await ctx.send("Произошла ошибка при попытке анмьюта пользователя.")
        logging.error(f"Error in unmute command: {error}")

@warnings.error
async def warnings_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Неверный аргумент. Использование: `!warnings @username`")
        logging.error(f"Missing required argument for warnings command: {error}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Неверный аргумент. Убедитесь, что упомянут валидный пользователь.")
        logging.error(f"Bad argument for warnings command: {error}")
    else:
        await ctx.send("Произошла ошибка при попытке отображения предупреждений пользователя.")
        logging.error(f"Error in warnings command: {error}")

def parse_duration(duration: str) -> int:
    if duration.endswith('d'):
        return int(duration[:-1]) * 86400
    elif duration.endswith('h'):
        return int(duration[:-1]) * 3600
    elif duration.endswith('m'):
        return int(duration[:-1]) * 60
    elif duration.endswith('s'):
        return int(duration[:-1])
    else:
        return None

def get_youtube_service(api_key):
    return googleapiclient.discovery.build('youtube', 'v3', developerKey=api_key)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def getvideosid(ctx):
    for api_key in YOUTUBE_API_KEYS:
        youtube = get_youtube_service(api_key)
        try:
            request = youtube.search().list(
                part="snippet",
                channelId=YOUTUBE_CHANNEL_ID_1,
                order="date",
                maxResults=1
            )
            response = request.execute()
            if 'items' in response and len(response['items']) > 0:
                video_id = response['items'][0]['id']['videoId']
                last_video_id = get_last_video_id(YOUTUBE_CHANNEL_ID_1)
                if video_id != last_video_id:
                    logging.info(f"Last video ID for channel 1: {last_video_id}")
                    set_last_video_id(YOUTUBE_CHANNEL_ID_1, video_id)

            request = youtube.search().list(
                part="snippet",
                channelId=YOUTUBE_CHANNEL_ID_2,
                order="date",
                maxResults=1
            )
            response = request.execute()
            if 'items' in response and len(response['items']) > 0:
                video_id = response['items'][0]['id']['videoId']
                last_video_id = get_last_video_id(YOUTUBE_CHANNEL_ID_2)
                if video_id != last_video_id:
                    logging.info(f"Last video ID for channel 2: {last_video_id}")
                    set_last_video_id(YOUTUBE_CHANNEL_ID_2, video_id)
            break
        except googleapiclient.errors.HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e):
                logging.warning(f"Quota exceeded for API key: {api_key}")
            else:
                await ctx.send(f"An error occurred! Check admin console for more information!")
                logging.error(f"An error occurred (getvideosid): {e}")
                raise e

async def check_youtube_channels_manual(ctx):
    channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
    if not channel:
        await ctx.send("Notification channel not found.")
        logging.error("Notification channel not found")
        return

    for api_key in YOUTUBE_API_KEYS:
        youtube = get_youtube_service(api_key)
        try:
            request = youtube.search().list(
                part="snippet",
                channelId=YOUTUBE_CHANNEL_ID_1,
                order="date",
                maxResults=1
            )
            response = request.execute()
            if 'items' in response and len(response['items']) > 0:
                video_id = response['items'][0]['id']['videoId']
                last_video_id = get_last_video_id(YOUTUBE_CHANNEL_ID_1)
                if video_id != last_video_id:
                    video_title = response['items'][0]['snippet']['title']
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    await channel.send(f"<@&1104385788797534228>\nНа канале какая-то движуха. А ну-ка глянем: {video_url}")
                    set_last_video_id(YOUTUBE_CHANNEL_ID_1, video_id)
                    logging.info(f"New video detected on channel {YOUTUBE_CHANNEL_ID_1}: {video_url}")

            request = youtube.search().list(
                part="snippet",
                channelId=YOUTUBE_CHANNEL_ID_2,
                order="date",
                maxResults=1
            )
            response = request.execute()
            if 'items' in response and len(response['items']) > 0:
                video_id = response['items'][0]['id']['videoId']
                last_video_id = get_last_video_id(YOUTUBE_CHANNEL_ID_2)
                if video_id != last_video_id:
                    video_title = response['items'][0]['snippet']['title']
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    await channel.send(f"<@&1265571159601319989>\nНа втором канале что-то появилось. Давайте-ка заценим: {video_url}")
                    set_last_video_id(YOUTUBE_CHANNEL_ID_2, video_id)
                    logging.info(f"New video detected on channel {YOUTUBE_CHANNEL_ID_2}: {video_url}")
            await ctx.send("YouTube channels checked successfully.")
            logging.info("YouTube channels checked successfully")
            break
        except googleapiclient.errors.HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e):
                logging.warning(f"Quota exceeded for API key: {api_key}")
            else:
                await ctx.send(f"An error occurred! Check admin console for more information!")
                logging.error(f"An error occurred (check_youtube_channels_manual): {e}")
                raise e

@bot.command()
@commands.has_permissions(manage_messages=True)
async def check_yt(ctx):
    await check_youtube_channels_manual(ctx)

@tasks.loop(minutes=1)
async def check_mutes():
    current_time = datetime.now()
    mutes = get_mutes()
    for user_id, mute_info in list(mutes.items()):
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
