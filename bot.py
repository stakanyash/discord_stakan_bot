import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import random
import googleapiclient.discovery
import googleapiclient.errors
import json
import os
import logging
from randomlist import mr_carsen_messages, gold_fund_messages

log_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_filename = f"bot_{log_timestamp}.log"

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

# Load configuration from file
with open('config.json', 'r') as file:
    config = json.load(file)

DISCORD_TOKEN = config['DISCORD_TOKEN']
MUTE_ROLE_ID = config['MUTE_ROLE_ID']
YOUR_ADMIN_ROLE_ID = config['YOUR_ADMIN_ROLE_ID']
NOTIFICATION_CHANNEL_ID = config['NOTIFICATION_CHANNEL_ID']
YOUTUBE_API_KEYS = config['YOUTUBE_API_KEYS']
YOUTUBE_CHANNEL_ID_1 = config['YOUTUBE_CHANNEL_ID_1']
YOUTUBE_CHANNEL_ID_2 = config['YOUTUBE_CHANNEL_ID_2']

warnings = {}
mutes = {}

@bot.event
async def on_ready():
    logging.info(f'Logged in as {bot.user}')
    load_data()
    check_mutes.start()

@bot.command()
@commands.has_permissions(manage_messages=True)
async def mute(ctx, member: discord.Member, duration: str, *, reason: str = "Not specified"):
    role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if not role:
        await ctx.send("Mute role not found. Ensure the role ID is correct.")
        logging.warning(f"Mute role not found for guild {ctx.guild.id}")
        return

    # Parse duration
    duration_seconds = parse_duration(duration)
    if duration_seconds is None:
        await ctx.send("Invalid duration format. Use format: 1d, 2h, 30m, 60s.")
        logging.warning(f"Invalid duration format: {duration}")
        return

    await member.add_roles(role, reason=reason)
    await ctx.send(f'{member.mention} has been muted for {duration}. Reason: {reason}')
    logging.info(f"Muted {member.id} for {duration}. Reason: {reason}")

    mutes[member.id] = {
        'end_time': datetime.now() + timedelta(seconds=duration_seconds),
        'reason': reason
    }
    save_data()

@bot.command()
@commands.has_permissions(manage_messages=True)
async def unmute(ctx, member: discord.Member):
    role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if role in member.roles:
        await member.remove_roles(role, reason="Manual unmute")
        await ctx.send(f'{member.mention} has been unmuted.')
        logging.info(f"Unmuted {member.id}")
        if member.id in mutes:
            del mutes[member.id]
            save_data()
    else:
        await ctx.send(f'{member.mention} is not muted.')
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
    died = random.randint(0, 1)
    if died == 1:
        await ctx.reply("БАБАХ! You are dead. Not a big surprise. ☠️")
        role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
        if role:
            await ctx.author.add_roles(role, reason="Russian roulette")
            await asyncio.sleep(60)  # Wait for 1 minute
            await ctx.author.remove_roles(role, reason="Mute time expired")
        logging.info(f"{ctx.author.id} lost the roulette and was muted for 1 minute")
    else:
        await ctx.reply("**·щёлк·**\nФартовый однако! 🤔")
        logging.info(f"{ctx.author.id} won the roulette")

@bot.command()
async def помощь(ctx):
    help_message = (
        "**Здарова, салаги!**\n"
        "Данный бот может много чего. Прислать уведомление о новом видео, замутить вас или же позабавить своими командами!\n"
        "\n"
        "Доступные команды:\n"
        "\n"
        "- `!MrCarsen` - содержит все так называемые 'Цытаты виликих' из модификаций данного товарища.\n"
        "\n"
        "- `!золотойфонд` - выдаёт случайное сообщение из золотого фонда.\n"
        "\n"
        "- `!неумничай` - если кто-то слишком сильно умничает. В ответ на неё бот пошлёт вас на три буквы.\n"
        "Однако вы можете ответить ему командой `!аможетбытьты`, получив в ответ 'КТО?! Я?!'.\n"
        "Написав команду `!ХУЯБЛЯ` бот включает режим Глада Валакаса и отправляет вас в бан. На целую минуту.\n"
        "\n"
        "- `!пошёлтынахуй` - позволяет послать собеседника куда подальше, но бот воспримет это на свой счёт, учтите.\n"
        "||на самом деле ничего не будет и он просто спросит за что вы так с ним||\n"
        "\n"
        "- `!рулетка` - своеобразная 'Русская рулетка'. Либо жив, либо умер. В случае 'смерти' получаете мьют на минуту.\n"
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
        await ctx.author.add_roles(role, reason="You've gone too far!")
        await asyncio.sleep(60)  # Wait for 1 minute
        await ctx.author.remove_roles(role, reason="Mute time expired")
    logging.info(f"{ctx.author.id} triggered the ХУЯБЛЯ command and was muted for 1 minute")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason: str = "Not specified"):
    if member.id not in warnings:
        warnings[member.id] = []

    # Remove warnings older than 24 hours
    warnings[member.id] = [w for w in warnings[member.id] if datetime.fromisoformat(w['timestamp']) > datetime.now() - timedelta(days=1)]

    # Add new warning
    warnings[member.id].append({'timestamp': datetime.now().isoformat(), 'reason': reason})

    # Check the number of warnings in the last 24 hours
    recent_warnings = [w for w in warnings[member.id] if datetime.fromisoformat(w['timestamp']) > datetime.now() - timedelta(days=1)]
    if len(recent_warnings) >= 3:
        await mute(ctx, member, '24h', reason="3 warnings in 24 hours")
        warnings[member.id] = []
    else:
        await ctx.send(f'{member.mention} has been warned. Reason: {reason}.')
        logging.info(f"Warned {member.id}. Reason: {reason}")

    save_data()

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warnremove(ctx, member: discord.Member):
    if member.id in warnings and len(warnings[member.id]) >= 1:
        warnings[member.id] = []
        await ctx.send(f'All warnings for {member.mention} have been removed.')
        logging.info(f"Removed all warnings for {member.id}")
    else:
        await ctx.send(f'{member.mention} has no active warnings.')
        logging.warning(f"No active warnings for {member.id}")

    save_data()

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warnings(ctx, member: discord.Member):
    if member.id in warnings and len(warnings[member.id]) >= 1:
        warn_list = warnings[member.id]
        warn_messages = [f"{datetime.fromisoformat(w['timestamp']).strftime('%d-%m-%Y %H-%M')}: {w['reason']}" for w in warn_list]
        warn_messages.reverse()  # Show warnings from newest to oldest
        await ctx.send(f"Warnings for {member.mention}:\n" + "\n".join(warn_messages))
        logging.info(f"Listed warnings for {member.id}")
    else:
        await ctx.send(f'{member.mention} has no warnings.')
        logging.warning(f"No warnings for {member.id}")

@warnremove.error
async def warnremove_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Invalid argument. Usage: `!warnremove @username`")
        logging.error(f"Missing required argument for warnremove command: {error}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument. Ensure a valid user is mentioned.")
        logging.error(f"Bad argument for warnremove command: {error}")
    else:
        await ctx.send("An error occurred while removing warnings.")
        logging.error(f"Error in warnremove command: {error}")

@warn.error
async def warn_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Invalid argument. Usage: `!warn @username reason`")
        logging.error(f"Missing required argument for warn command: {error}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument. Ensure a valid user is mentioned.")
        logging.error(f"Bad argument for warn command: {error}")
    else:
        await ctx.send("An error occurred while warning the user.")
        logging.error(f"Error in warn command: {error}")

@mute.error
async def mute_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Invalid argument. Usage: `!mute @username duration reason`")
        logging.error(f"Missing required argument for mute command: {error}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument. Ensure a valid user is mentioned and duration is specified.")
        logging.error(f"Bad argument for mute command: {error}")
    else:
        await ctx.send("An error occurred while muting the user.")
        logging.error(f"Error in mute command: {error}")

@unmute.error
async def unmute_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Invalid argument. Usage: `!unmute @username`")
        logging.error(f"Missing required argument for unmute command: {error}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument. Ensure a valid user is mentioned.")
        logging.error(f"Bad argument for unmute command: {error}")
    else:
        await ctx.send("An error occurred while unmuting the user.")
        logging.error(f"Error in unmute command: {error}")

# Parse duration for mute command
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

# YouTube API setup
def get_youtube_service(api_key):
    return googleapiclient.discovery.build('youtube', 'v3', developerKey=api_key)

# Load last checked video IDs from file
def load_last_video_ids():
    if os.path.exists('last_video_ids.json'):
        with open('last_video_ids.json', 'r') as file:
            return json.load(file)
    return {YOUTUBE_CHANNEL_ID_1: None, YOUTUBE_CHANNEL_ID_2: None}

# Save last checked video IDs to file
def save_last_video_ids(last_video_ids):
    with open('last_video_ids.json', 'w') as file:
        json.dump(last_video_ids, file)

last_video_ids = load_last_video_ids()

async def check_youtube_channels_manual(ctx):
    channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
    if not channel:
        await ctx.send("Notification channel not found.")
        logging.error("Notification channel not found")
        return

    for api_key in YOUTUBE_API_KEYS:
        youtube = get_youtube_service(api_key)
        try:
            # Check first YouTube channel
            request = youtube.search().list(
                part="snippet",
                channelId=YOUTUBE_CHANNEL_ID_1,
                order="date",
                maxResults=1
            )
            response = request.execute()
            if 'items' in response and len(response['items']) > 0:
                video_id = response['items'][0]['id']['videoId']
                if video_id != last_video_ids[YOUTUBE_CHANNEL_ID_1]:
                    video_title = response['items'][0]['snippet']['title']
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    await channel.send(f"<@&1104385788797534228>\nНа канале какая-то движуха. А ну-ка глянем: {video_url}")
                    last_video_ids[YOUTUBE_CHANNEL_ID_1] = video_id
                    save_last_video_ids(last_video_ids)
                    logging.info(f"New video detected on channel {YOUTUBE_CHANNEL_ID_1}: {video_url}")

            # Check second YouTube channel
            request = youtube.search().list(
                part="snippet",
                channelId=YOUTUBE_CHANNEL_ID_2,
                order="date",
                maxResults=1
            )
            response = request.execute()
            if 'items' in response and len(response['items']) > 0:
                video_id = response['items'][0]['id']['videoId']
                if video_id != last_video_ids[YOUTUBE_CHANNEL_ID_2]:
                    video_title = response['items'][0]['snippet']['title']
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    await channel.send(f"<@&1265571159601319989>\nНа втором канале что-то появилось. Давайте-ка заценим: {video_url}")
                    last_video_ids[YOUTUBE_CHANNEL_ID_2] = video_id
                    save_last_video_ids(last_video_ids)
                    logging.info(f"New video detected on channel {YOUTUBE_CHANNEL_ID_2}: {video_url}")
            await ctx.send("YouTube channels checked successfully.")
            logging.info("YouTube channels checked successfully")
            break  # Exit the loop if the request was successful
        except googleapiclient.errors.HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e):
                await ctx.send(f"Quota exceeded for API key: {api_key}. Trying next key...")
                logging.warning(f"Quota exceeded for API key: {api_key}")
            else:
                await ctx.send(f"An error occurred: {e}")
                logging.error(f"An error occurred: {e}")
                raise e

@bot.command()
@commands.has_permissions(manage_messages=True)
async def check_youtube_channels(ctx):
    await check_youtube_channels_manual(ctx)

# Load warnings and mutes from file
def load_data():
    global warnings, mutes
    if os.path.exists('data.json'):
        with open('data.json', 'r') as file:
            try:
                data = json.load(file)
                warnings = data.get('warnings', {})
                mutes = data.get('mutes', {})
                # Convert timestamp strings back to datetime objects
                for user_id, warn_list in warnings.items():
                    for warn in warn_list:
                        if isinstance(warn['timestamp'], str):
                            warn['timestamp'] = datetime.fromisoformat(warn['timestamp'])
                for user_id, mute_info in mutes.items():
                    if isinstance(mute_info['end_time'], str):
                        mute_info['end_time'] = datetime.fromisoformat(mute_info['end_time'])
                logging.info("Data loaded successfully.")
            except json.JSONDecodeError as e:
                logging.error(f"Error loading data: {e}")
                warnings = {}
                mutes = {}
    else:
        logging.warning("Data file not found. Starting with empty data.")

# Save warnings and mutes to file
def save_data():
    try:
        with open('data.json', 'w') as file:
            data = {
                'warnings': {user_id: [{'timestamp': warn['timestamp'].isoformat() if isinstance(warn['timestamp'], datetime) else warn['timestamp'], 'reason': warn['reason']} for warn in warn_list] for user_id, warn_list in warnings.items()},
                'mutes': {user_id: {'end_time': mute_info['end_time'].isoformat() if isinstance(mute_info['end_time'], datetime) else mute_info['end_time'], 'reason': mute_info['reason']} for user_id, mute_info in mutes.items()}
            }
            json.dump(data, file)
        logging.info("Data saved successfully.")
    except Exception as e:
        logging.error(f"Error saving data: {e}")

@tasks.loop(minutes=1)
async def check_mutes():
    current_time = datetime.now()
    for user_id, mute_info in list(mutes.items()):
        if current_time >= mute_info['end_time']:
            guild = bot.get_guild(YOUR_ADMIN_ROLE_ID)
            member = guild.get_member(user_id)
            if member:
                role = discord.utils.get(guild.roles, id=MUTE_ROLE_ID)
                if role in member.roles:
                    await member.remove_roles(role, reason="Mute duration expired")
                    del mutes[user_id]
                    save_data()
                    logging.info(f"Unmuted {user_id} as mute duration expired")

bot.run(DISCORD_TOKEN)