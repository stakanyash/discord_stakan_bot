import re
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import asyncio
import collections
import logging
import sqlite3
import sys
import os
import random
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
import googleapiclient.discovery
import googleapiclient.errors
from randomlist import mr_carsen_messages, gold_fund_messages

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

def setup_logger() -> logging.Logger:
    log_filename = f"stakandiscordbot_{datetime.now().strftime('%Y.%m.%d_%H.%M.%S')}.log"
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(levelname)s] %(asctime)s - %(message)s', '%Y-%m-%d %H:%M:%S')
    logger.handlers.clear()
    file_handler = RotatingFileHandler(log_filename, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger

logger = setup_logger()

# ---------------------------------------------------------------------------
# ENV
# ---------------------------------------------------------------------------

load_dotenv()

DISCORD_TOKEN            = os.getenv("DISCORD_TOKEN")
MUTE_ROLE_ID             = int(os.getenv("MUTE_ROLE_ID"))
YOUR_ADMIN_ROLE_ID       = int(os.getenv("YOUR_ADMIN_ROLE_ID"))
NOTIFICATION_CHANNEL_ID  = int(os.getenv("NOTIFICATION_CHANNEL_ID"))
YOUTUBE_API_KEYS         = [k.strip('"') for k in os.getenv("YOUTUBE_API_KEYS").split(',')]
YOUTUBE_CHANNEL_ID_1     = os.getenv("YOUTUBE_CHANNEL_ID_1")
YOUTUBE_CHANNEL_ID_2     = os.getenv("YOUTUBE_CHANNEL_ID_2")
LOG_CHANNEL_ID           = int(os.getenv("LOG_CHANNEL_ID"))
YT_SUBSCRIBER_ROLE_ID    = int(os.getenv("YT_SUBSCRIBER_ROLE_ID"))
SEC_YT_SUBSCRIBER_ROLE_ID = int(os.getenv("SEC_YT_SUBSCRIBER_ROLE_ID"))
USER_ID                  = int(os.getenv("USER_ID"))
MODERATOR_ROLE_ID        = int(os.getenv("MODERATOR_ROLE_ID"))
ANTISPAM_CHANNEL_ID      = int(os.getenv("ANTISPAM_CHANNEL_ID"))
GUILD_ID                 = int(os.getenv("GUILD_ID"))  # NEW: нужен для корректного поиска участников

SPAM_TIME_WINDOW      = int(os.getenv("SPAM_TIME_WINDOW", "120"))
SPAM_CHANNELS_THRESHOLD = int(os.getenv("SPAM_CHANNELS_THRESHOLD", "3"))
SPAM_ALERT_COOLDOWN   = 300

DB_FILE = os.getenv("DB_FILE", "bot_data.db")

# ---------------------------------------------------------------------------
# INTENTS & BOT
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, log_handler=None)
bot.remove_command('help')

# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def create_tables():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS warnings (
                      user_id   INTEGER,
                      timestamp TEXT,
                      reason    TEXT
                   )''')
        c.execute('''CREATE TABLE IF NOT EXISTS mutes (
                      user_id  INTEGER UNIQUE,
                      end_time TEXT,
                      reason   TEXT
                   )''')
        c.execute('''CREATE TABLE IF NOT EXISTS bomb_cooldowns (
                      guild_id INTEGER PRIMARY KEY,
                      end_time TEXT
                   )''')
        c.execute('''CREATE TABLE IF NOT EXISTS last_video_ids (
                      channel_id TEXT PRIMARY KEY,
                      video_id   TEXT
                   )''')
        c.execute('''CREATE TABLE IF NOT EXISTS role_users (
                      user_id INTEGER PRIMARY KEY,
                      role_id INTEGER
                   )''')

create_tables()

# ---------------------------------------------------------------------------
# TIME HELPERS
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def dt_to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()

def dt_from_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def parse_duration(duration: str) -> int | None:
    duration = duration.strip()
    try:
        if duration.endswith('d'): return int(duration[:-1]) * 86400
        if duration.endswith('h'): return int(duration[:-1]) * 3600
        if duration.endswith('m'): return int(duration[:-1]) * 60
        if duration.endswith('s'): return int(duration[:-1])
    except ValueError:
        pass
    return None

def seconds_to_human(seconds: int) -> str:
    parts = []
    weeks, seconds = divmod(seconds, 604800)
    days,  seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    mins,  seconds = divmod(seconds, 60)
    if weeks:  parts.append(f"{weeks} нед.")
    if days:   parts.append(f"{days} дн.")
    if hours:  parts.append(f"{hours} ч.")
    if mins:   parts.append(f"{mins} мин.")
    if seconds or not parts: parts.append(f"{seconds} сек.")
    return " ".join(parts)

# ---------------------------------------------------------------------------
# DB — warnings
# ---------------------------------------------------------------------------

def get_warnings(user_id: int) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT timestamp, reason FROM warnings WHERE user_id = ? ORDER BY timestamp",
            (user_id,)
        ).fetchall()
    return [{'timestamp': r[0], 'reason': r[1]} for r in rows]

def add_warning(user_id: int, reason: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO warnings (user_id, timestamp, reason) VALUES (?, ?, ?)",
            (user_id, dt_to_iso(_utcnow()), reason)
        )

def remove_warnings(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))

def get_recent_warnings(user_id: int) -> list:
    """Возвращает предупреждения за последние 24 часа."""
    since = dt_to_iso(_utcnow() - timedelta(days=1))
    with get_db() as conn:
        rows = conn.execute(
            "SELECT timestamp, reason FROM warnings WHERE user_id = ? AND timestamp > ?",
            (user_id, since)
        ).fetchall()
    return [{'timestamp': r[0], 'reason': r[1]} for r in rows]

# ---------------------------------------------------------------------------
# DB — mutes
# ---------------------------------------------------------------------------

def get_mutes() -> dict:
    with get_db() as conn:
        rows = conn.execute("SELECT user_id, end_time, reason FROM mutes").fetchall()
    return {r[0]: {'end_time': r[1], 'reason': r[2]} for r in rows}

def add_mute(user_id: int, end_time: datetime, reason: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO mutes (user_id, end_time, reason) VALUES (?, ?, ?)",
            (user_id, dt_to_iso(end_time), reason)
        )

def remove_mute(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM mutes WHERE user_id = ?", (user_id,))

# ---------------------------------------------------------------------------
# DB — bomb cooldowns
# ---------------------------------------------------------------------------

def get_bomb_cooldown(guild_id: int) -> datetime | None:
    with get_db() as conn:
        result = conn.execute(
            "SELECT end_time FROM bomb_cooldowns WHERE guild_id = ?", (guild_id,)
        ).fetchone()
    return dt_from_iso(result[0]) if result else None

def set_bomb_cooldown(guild_id: int, end_time: datetime):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO bomb_cooldowns (guild_id, end_time) VALUES (?, ?)",
            (guild_id, dt_to_iso(end_time))
        )

def remove_bomb_cooldown(guild_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM bomb_cooldowns WHERE guild_id = ?", (guild_id,))

# ---------------------------------------------------------------------------
# DB — YouTube
# ---------------------------------------------------------------------------

def get_last_video_id(channel_id: str) -> str | None:
    with get_db() as conn:
        result = conn.execute(
            "SELECT video_id FROM last_video_ids WHERE channel_id = ?", (channel_id,)
        ).fetchone()
    return result[0] if result else None

def set_last_video_id(channel_id: str, video_id: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO last_video_ids (channel_id, video_id) VALUES (?, ?)",
            (channel_id, video_id)
        )

# ---------------------------------------------------------------------------
# DB — role_users
# ---------------------------------------------------------------------------

def add_role_user(user_id: int, role_id: int):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO role_users (user_id, role_id) VALUES (?, ?)",
            (user_id, role_id)
        )

def remove_role_user(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM role_users WHERE user_id = ?", (user_id,))

# ---------------------------------------------------------------------------
# EMBED BUILDERS
# ---------------------------------------------------------------------------

def _now_dt() -> datetime:
    return _utcnow()

def e_ok(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=0x57F287, timestamp=_now_dt())

def e_err(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=0xED4245, timestamp=_now_dt())

def e_info(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=0x5865F2, timestamp=_now_dt())

def e_warn(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=0xFEE75C, timestamp=_now_dt())

LOG_COLORS = {
    "join":       0x57F287,
    "leave":      0xED4245,
    "role_add":   0x5865F2,
    "role_remove":0xEB459E,
    "voice":      0x9B59B6,
    "msg_edit":   0xFEE75C,
    "msg_delete": 0xE67E22,
    "mod":        0xED4245,
    "spam":       0xFF6B35,
    "yt":         0xFF0000,
}

async def send_log_embed(embed: discord.Embed):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)
    else:
        logger.error(f"Log channel {LOG_CHANNEL_ID} not found")

async def send_mod_log(
    title: str,
    color: int,
    member: discord.User | discord.Member,
    *,
    moderator: discord.Member = None,
    reason: str = None,
    duration: str = None,
    until: datetime = None,
    extra_fields: list[tuple[str, str, bool]] = None,
):
    embed = discord.Embed(title=title, color=color, timestamp=_now_dt())
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    embed.add_field(name="Участник", value=member.mention, inline=True)
    if moderator:
        embed.add_field(name="Модератор", value=moderator.mention, inline=True)
    if duration:
        embed.add_field(name="Длительность", value=duration, inline=True)
    if until:
        embed.add_field(name="До", value=discord.utils.format_dt(until, style="f"), inline=True)
    if reason:
        embed.add_field(name="Причина", value=reason, inline=False)
    if extra_fields:
        for name, value, inline in extra_fields:
            embed.add_field(name=name, value=value, inline=inline)
    embed.set_footer(text=f"ID: {member.id}")
    await send_log_embed(embed)

def make_action_embed(
    action: str,
    member: discord.Member,
    moderator: discord.Member,
    reason: str,
    color: discord.Color,
    *,
    duration: str = None,
    until: datetime = None,
) -> discord.Embed:
    embed = discord.Embed(color=color, timestamp=_now_dt())
    embed.set_author(name=f"Участник {member} {action}.", icon_url=member.display_avatar.url)
    embed.add_field(name="Причина",   value=reason,            inline=False)
    embed.add_field(name="Модератор", value=moderator.mention, inline=True)
    if duration:
        embed.add_field(name="Длительность", value=duration, inline=True)
    if until:
        embed.add_field(name="Заглушён до", value=discord.utils.format_dt(until, style="f"), inline=True)
    embed.set_footer(text=f"ID: {member.id}")
    return embed

# ---------------------------------------------------------------------------
# PERMISSION HELPERS
# ---------------------------------------------------------------------------

def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.manage_messages

def is_moderator(member: discord.Member) -> bool:
    return any(role.id == MODERATOR_ROLE_ID for role in member.roles)

def is_admin_or_moderator(member: discord.Member) -> bool:
    return is_admin(member) or is_moderator(member)

def _can_moderate(actor: discord.Member, target: discord.Member) -> tuple[bool, str]:
    """
    Проверяет, может ли actor применить модерационное действие к target.
    Возвращает (можно, причина_отказа).

    Правила:
    - Нельзя применять действие к самому себе.
    - Нельзя применять действие к боту.
    - Владельца сервера (administrator) нельзя модерировать.
    - Администратор не может модерировать другого администратора.
    - Модератор не может модерировать другого модератора или администратора.
    - Нельзя применять действие к участнику с равной или более высокой верхней ролью
      (если actor сам не является администратором сервера).
    """
    if actor.id == target.id:
        return False, "Нельзя применить это действие к самому себе."
    if target.bot:
        return False, "Нельзя применять модерацию к ботам."
    if target.guild_permissions.administrator:
        return False, "Нельзя применить это действие к администратору сервера."
    if is_moderator(target) and not actor.guild_permissions.administrator:
        return False, "Нельзя применить это действие к другому модератору."
    if actor.top_role <= target.top_role and not actor.guild_permissions.administrator:
        return False, "Нельзя применить это действие к участнику с равной или более высокой ролью."
    return True, ""

# ---------------------------------------------------------------------------
# ANTI-SPAM
# ---------------------------------------------------------------------------

user_message_log: dict[int, collections.deque] = collections.defaultdict(lambda: collections.deque())
last_spam_alert: dict[int, datetime] = {}

async def send_spam_alert(user: discord.Member, reason: str, details: str):
    user_id = user.id
    now = _utcnow()
    last_alert = last_spam_alert.get(user_id)
    if last_alert and (now - last_alert).total_seconds() < SPAM_ALERT_COOLDOWN:
        return
    last_spam_alert[user_id] = now

    channel = bot.get_channel(ANTISPAM_CHANNEL_ID)
    if not channel:
        logger.error(f"Antispam channel {ANTISPAM_CHANNEL_ID} not found.")
        return

    embed = discord.Embed(
        title="Антиспам: подозрительная активность!",
        color=LOG_COLORS["spam"],
        timestamp=_now_dt()
    )
    embed.set_author(name=str(user), icon_url=user.display_avatar.url)
    embed.add_field(name="Пользователь", value=f"{user.mention} (`{user}` | ID: `{user_id}`)", inline=False)
    embed.add_field(name="Причина",      value=reason, inline=False)
    embed.add_field(name="Детали",       value=details, inline=False)
    embed.set_footer(text=f"ID: {user_id}")

    mention_text = f"<@&{YOUR_ADMIN_ROLE_ID}> <@&{MODERATOR_ROLE_ID}>"
    await channel.send(mention_text, embed=embed)
    logger.warning(f"[SPAM ALERT] [{reason}] {user} ({user_id}). {details}")

async def check_spam(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    member = message.author
    user_id = member.id
    now = _utcnow()

    if "@everyone" in message.content or "@here" in message.content:
        if not member.guild_permissions.mention_everyone:
            preview = message.content[:300].replace("```", "")
            await send_spam_alert(
                user=member,
                reason="Попытка использовать @everyone / @here без прав",
                details=f"Канал: {message.channel.mention}\nТекст:\n```{preview}```"
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
            details=f"Каналы: {channel_mentions}\nСообщений в окне: `{len(log)}`"
        )

# ---------------------------------------------------------------------------
# CORE MODERATION LOGIC
# ---------------------------------------------------------------------------

async def _apply_mute(ctx, member: discord.Member, duration_seconds: int, reason: str) -> bool:
    role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if not role:
        await ctx.send(embed=e_err("Роль мьюта не найдена", "Проверьте переменную `MUTE_ROLE_ID` в `.env`."))
        return False
    try:
        await member.add_roles(role, reason=reason)
    except discord.Forbidden:
        await ctx.send(embed=e_err("Нет прав", "У меня недостаточно прав для выдачи роли мьюта."))
        logger.error(f"Missing permissions to mute {member} in {ctx.guild.name}")
        return False

    until = _utcnow() + timedelta(seconds=duration_seconds)
    human = seconds_to_human(duration_seconds)
    add_mute(member.id, until, reason)

    embed = make_action_embed(
        action="заглушён", member=member, moderator=ctx.author,
        reason=reason, color=discord.Color.orange(),
        duration=human, until=until,
    )
    await ctx.send(embed=embed, view=UnmuteView(member.id))
    logger.info(f"Muted {member.id} for {human}. Reason: {reason}")
    await send_mod_log(
        "Мут выдан", LOG_COLORS["mod"], member,
        moderator=ctx.author, reason=reason,
        duration=human, until=until,
    )
    return True

async def _apply_warn(ctx, member: discord.Member, reason: str):
    mute_role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
    if mute_role and mute_role in member.roles:
        await ctx.send(embed=e_warn("Уже замьючен", f"{member.mention} уже находится в муте — варн не выдан."))
        return

    add_warning(member.id, reason)
    recent = get_recent_warnings(member.id)

    if len(recent) >= 3:
        muted = await _apply_mute(ctx, member, duration_seconds=86400,
                                  reason="3 предупреждения за 24 часа")
        if muted:
            remove_warnings(member.id)
    else:
        embed = make_action_embed(
            action="предупреждён", member=member, moderator=ctx.author,
            reason=reason, color=discord.Color.yellow(),
        )
        embed.add_field(name="Предупреждений (за 24ч)", value=f"{len(recent)}/3", inline=True)
        await ctx.send(embed=embed)
        logger.info(f"Warned {member.id}. Reason: {reason}")
        await send_mod_log(
            "Предупреждение выдано", 0xFEE75C, member,
            moderator=ctx.author, reason=reason,
            extra_fields=[("Счётчик", f"{len(recent)}/3", True)],
        )

# ---------------------------------------------------------------------------
# PERSISTENT VIEWS
# ---------------------------------------------------------------------------

class UnmuteView(discord.ui.View):
    def __init__(self, user_id: int = 0):
        super().__init__(timeout=None)
        btn = discord.ui.Button(
            label="Снять мут",
            style=discord.ButtonStyle.danger,
            custom_id=f"unmute:{user_id}",
        )
        btn.callback = self._callback
        self.add_item(btn)

    async def _callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                embed=e_err("Нет прав", "У вас нет прав для этого действия."), ephemeral=True
            )
            return
        user_id = int(interaction.data["custom_id"].split(":")[1])
        member  = interaction.guild.get_member(user_id)
        if member is None:
            await interaction.response.send_message(
                embed=e_err("Не найден", "Пользователь не найден на сервере."), ephemeral=True
            )
            return
        role = discord.utils.get(interaction.guild.roles, id=MUTE_ROLE_ID)
        if role and role in member.roles:
            await member.remove_roles(role, reason=f"Анмьют через кнопку ({interaction.user})")
            remove_mute(user_id)
            for item in self.children:
                item.disabled = True
                item.label = "Мут снят"
            await interaction.response.edit_message(view=self)
            embed = e_ok("Мут снят", f"{member.mention} размьючен пользователем {interaction.user.mention}.")
            embed.set_footer(text=f"ID: {user_id}")
            await interaction.followup.send(embed=embed)
            logger.info(f"Unmuted {user_id} via button by {interaction.user.id}")
            await send_mod_log("Мут снят", LOG_COLORS["join"], member, moderator=interaction.user)
        else:
            await interaction.response.send_message(
                embed=e_warn("Не замьючен", f"{member.mention} не имеет роли мьюта."), ephemeral=True
            )


class SubscribeView(discord.ui.View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.role_id = role_id

        add_btn = discord.ui.Button(
            label="Получить роль",
            style=discord.ButtonStyle.green,
            custom_id=f"subscribe_add_{role_id}"
        )
        add_btn.callback = self._add_callback
        self.add_item(add_btn)

        remove_btn = discord.ui.Button(
            label="Отказаться от роли",
            style=discord.ButtonStyle.red,
            custom_id=f"subscribe_remove_{role_id}"
        )
        remove_btn.callback = self._remove_callback
        self.add_item(remove_btn)

    async def _add_callback(self, interaction: discord.Interaction):
        await self._update_role(interaction, add=True)

    async def _remove_callback(self, interaction: discord.Interaction):
        await self._update_role(interaction, add=False)

    async def _update_role(self, interaction: discord.Interaction, add: bool):
        role = discord.utils.get(interaction.guild.roles, id=self.role_id)
        if role is None:
            await interaction.response.send_message(embed=e_err("Роль не найдена"), ephemeral=True)
            return
        if add:
            if role not in interaction.user.roles:
                await interaction.user.add_roles(role)
                add_role_user(interaction.user.id, self.role_id)
                await interaction.response.send_message(
                    embed=e_ok("Роль выдана", f"Вам выдана роль {role.mention}!"), ephemeral=True
                )
                logger.info(f"Added role {role.id} to user {interaction.user.id}")
            else:
                await interaction.response.send_message(
                    embed=e_info("Уже есть", f"У вас уже есть роль {role.mention}."), ephemeral=True
                )
        else:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                remove_role_user(interaction.user.id)
                await interaction.response.send_message(
                    embed=e_ok("Роль снята", f"Роль {role.mention} удалена."), ephemeral=True
                )
                logger.info(f"Removed role {role.id} from user {interaction.user.id}")
            else:
                await interaction.response.send_message(
                    embed=e_info("Роли нет", f"У вас нет роли {role.mention}."), ephemeral=True
                )


class ConfirmView(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=15)
        self.author = author
        self.value: bool | None = None
        self.message: discord.Message | None = None

    @discord.ui.button(label="Подтвердить", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Это не ваша кнопка.", ephemeral=True)
            return
        self.value = True
        self.stop()
        await interaction.response.defer()
        if self.message:
            await self.message.delete()

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Это не ваша кнопка.", ephemeral=True)
            return
        self.value = False
        self.stop()
        await interaction.response.defer()
        if self.message:
            await self.message.delete()


class AdminMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Проверить YouTube каналы", style=discord.ButtonStyle.blurple, custom_id="admin_check_yt")
    async def check_yt_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(embed=e_err("Нет прав"), ephemeral=True)
            return
        await interaction.response.send_message("Проверяю YouTube каналы...", ephemeral=True)
        await _check_youtube_channels(interaction.channel)

    @discord.ui.button(label="Обновить ID последних видео", style=discord.ButtonStyle.green, custom_id="admin_update_ids")
    async def update_ids_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(embed=e_err("Нет прав"), ephemeral=True)
            return
        await interaction.response.send_message("Обновляю ID последних видео...", ephemeral=True)
        await _fetch_and_save_latest_video_ids()
        await interaction.followup.send(embed=e_ok("Готово", "ID последних видео обновлены."), ephemeral=True)

    @discord.ui.button(label="Перезагрузить бота", style=discord.ButtonStyle.red, custom_id="admin_restart")
    async def restart_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(embed=e_err("Нет прав"), ephemeral=True)
            return
        await interaction.response.send_message(embed=e_warn("Перезагрузка", "Бот перезапускается..."), ephemeral=True)
        logger.info(f"Bot restarting by {interaction.user}")
        await asyncio.sleep(2)
        os.execv(sys.executable, ['python'] + sys.argv)

# ---------------------------------------------------------------------------
# YOUTUBE HELPERS
# ---------------------------------------------------------------------------

def _get_youtube_service(api_key: str):
    return googleapiclient.discovery.build('youtube', 'v3', developerKey=api_key)

async def _fetch_and_save_latest_video_ids():
    """Обновляет ID последних видео без уведомлений."""
    for api_key in YOUTUBE_API_KEYS:
        youtube = _get_youtube_service(api_key)
        try:
            for ch_id in (YOUTUBE_CHANNEL_ID_1, YOUTUBE_CHANNEL_ID_2):
                req  = youtube.search().list(part="snippet", channelId=ch_id, order="date", maxResults=1)
                resp = req.execute()
                if resp.get('items'):
                    video_id = resp['items'][0]['id']['videoId']
                    set_last_video_id(ch_id, video_id)
                    logger.info(f"Updated last video ID for {ch_id}: {video_id}")
            return
        except googleapiclient.errors.HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e):
                logger.warning(f"Quota exceeded for API key: {api_key}")
            else:
                logger.error(f"YouTube API error: {e}")
                raise

async def _check_youtube_channels(reply_channel=None):
    """Проверяет новые видео и отправляет уведомления."""
    notification_channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
    if not notification_channel:
        logger.error("Notification channel not found")
        return

    yt_configs = [
        (YOUTUBE_CHANNEL_ID_1, "<@&1104385788797534228>", "На канале какая-то движуха. А ну-ка глянем"),
        (YOUTUBE_CHANNEL_ID_2, "<@&1265571159601319989>", "На втором канале что-то появилось. Давайте-ка заценим"),
    ]

    for api_key in YOUTUBE_API_KEYS:
        youtube = _get_youtube_service(api_key)
        try:
            for ch_id, mention, text in yt_configs:
                req  = youtube.search().list(part="snippet", channelId=ch_id, order="date", maxResults=1)
                resp = req.execute()
                if resp.get('items'):
                    video_id = resp['items'][0]['id']['videoId']
                    if video_id != get_last_video_id(ch_id):
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        embed = discord.Embed(
                            title="Новое видео!",
                            description=f"{text}: {video_url}",
                            color=LOG_COLORS["yt"],
                            timestamp=_now_dt()
                        )
                        await notification_channel.send(mention, embed=embed)
                        set_last_video_id(ch_id, video_id)
                        logger.info(f"New video on {ch_id}: {video_url}")

            if reply_channel:
                await reply_channel.send(embed=e_ok("YouTube проверен", "Каналы успешно проверены."))
            logger.info("YouTube channels checked successfully")
            return
        except googleapiclient.errors.HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e):
                logger.warning(f"Quota exceeded for API key: {api_key}")
            else:
                logger.error(f"YouTube API error: {e}")
                if reply_channel:
                    await reply_channel.send(embed=e_err("Ошибка YouTube API", "Проверьте консоль."))
                raise

# ---------------------------------------------------------------------------
# BOT EVENTS
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    # Restore persistent views
    for uid in get_mutes():
        bot.add_view(UnmuteView(uid))
    bot.add_view(UnmuteView(0))
    bot.add_view(SubscribeView(YT_SUBSCRIBER_ROLE_ID))
    bot.add_view(SubscribeView(SEC_YT_SUBSCRIBER_ROLE_ID))
    bot.add_view(AdminMenuView())

    await bot.tree.sync()
    logger.info("Slash commands synced")
    logger.info(f"{bot.user} is online and ready)0))")

    if not check_mutes.is_running():
        check_mutes.start()
    if not check_youtube.is_running():
        check_youtube.start()


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
    await check_spam(message)
    await bot.process_commands(message)


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if before.roles == after.roles:
        return
    added   = [r for r in after.roles  if r not in before.roles and r.id != MUTE_ROLE_ID]
    removed = [r for r in before.roles if r not in after.roles  and r.id != MUTE_ROLE_ID]

    if added:
        embed = discord.Embed(title="Роли добавлены", color=LOG_COLORS["role_add"], timestamp=_now_dt())
        embed.set_author(name=str(after), icon_url=after.display_avatar.url)
        embed.add_field(name="Участник", value=after.mention, inline=True)
        embed.add_field(name="Роли",     value=" ".join(r.mention for r in added), inline=True)
        embed.set_footer(text=f"ID: {after.id}")
        await send_log_embed(embed)

    if removed:
        embed = discord.Embed(title="Роли удалены", color=LOG_COLORS["role_remove"], timestamp=_now_dt())
        embed.set_author(name=str(after), icon_url=after.display_avatar.url)
        embed.add_field(name="Участник", value=after.mention, inline=True)
        embed.add_field(name="Роли",     value=" ".join(r.mention for r in removed), inline=True)
        embed.set_footer(text=f"ID: {after.id}")
        await send_log_embed(embed)


@bot.event
async def on_member_join(member: discord.Member):
    embed = discord.Embed(title="Участник вошёл", color=LOG_COLORS["join"], timestamp=_now_dt())
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    embed.add_field(name="Упоминание",     value=member.mention, inline=True)
    embed.add_field(name="Аккаунт создан", value=discord.utils.format_dt(member.created_at, style="R"), inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"ID: {member.id}")
    await send_log_embed(embed)


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
    await send_log_embed(embed)


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
        embed.add_field(name="Куда",   value=after.channel.mention,  inline=True)
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    embed.add_field(name="Участник", value=member.mention, inline=True)
    embed.set_footer(text=f"ID: {member.id}")
    await send_log_embed(embed)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.content == after.content:
        return
    def trim(text: str) -> str:
        return text[:1021] + "..." if len(text) > 1024 else (text or "*пусто*")
    embed = discord.Embed(title="Сообщение отредактировано", color=LOG_COLORS["msg_edit"],
                          timestamp=_now_dt(), url=after.jump_url)
    embed.set_author(name=str(after.author), icon_url=after.author.display_avatar.url)
    embed.add_field(name="Канал",   value=after.channel.mention,                inline=True)
    embed.add_field(name="Перейти", value=f"[к сообщению]({after.jump_url})",   inline=True)
    embed.add_field(name="До",      value=trim(before.content),                 inline=False)
    embed.add_field(name="После",   value=trim(after.content),                  inline=False)
    embed.set_footer(text=f"ID автора: {after.author.id}")
    await send_log_embed(embed)


@bot.event
async def on_message_delete(message: discord.Message):
    if message.author == bot.user or isinstance(message.channel, discord.DMChannel):
        return
    def trim(text: str) -> str:
        return text[:1021] + "..." if len(text) > 1024 else (text or "*пусто*")
    embed = discord.Embed(title="Сообщение удалено", color=LOG_COLORS["msg_delete"], timestamp=_now_dt())
    embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
    embed.add_field(name="Автор", value=message.author.mention,  inline=True)
    embed.add_field(name="Канал", value=message.channel.mention, inline=True)
    embed.add_field(name="Текст", value=trim(message.content),   inline=False)
    if message.attachments:
        embed.add_field(
            name=f"Вложения ({len(message.attachments)})",
            value="\n".join(a.filename for a in message.attachments),
            inline=False
        )
    embed.set_footer(text=f"ID автора: {message.author.id}")
    await send_log_embed(embed)

# ---------------------------------------------------------------------------
# ERROR HANDLER
# ---------------------------------------------------------------------------

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(embed=e_err("Нет прав", "У вас нет прав для этой команды."))
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=e_err("Неверные аргументы", f"Пропущен аргумент: `{error.param.name}`"))
    elif isinstance(error, commands.BadArgument):
        await ctx.send(embed=e_err("Неверный аргумент", str(error)))
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        logger.error(f"Unhandled error in {ctx.command}: {error}", exc_info=error)

# ---------------------------------------------------------------------------
# MODERATION COMMANDS
# ---------------------------------------------------------------------------

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
    await _apply_mute(ctx, member, duration_seconds, reason)


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
        logger.info(f"Unmuted {member.id} by {ctx.author.id}")
        await send_mod_log("Мут снят", LOG_COLORS["join"], member, moderator=ctx.author)
    else:
        await ctx.send(embed=e_warn("Не замьючен", f"{member.mention} не имеет роли мьюта."))


@bot.hybrid_command(with_app_command=True)
@commands.check(lambda ctx: is_admin_or_moderator(ctx.author))
async def warn(ctx: commands.Context, member: discord.Member, *, reason: str = "Не указана"):
    """Выдать предупреждение участнику."""
    can, why = _can_moderate(ctx.author, member)
    if not can:
        await ctx.send(embed=e_err("Нет прав", why))
        return
    await _apply_warn(ctx, member, reason)


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
        logger.info(f"Removed all warnings for {member.id}")
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
    logger.info(f"Mass mute in {ctx.channel.id} by {ctx.author.id}")
    await asyncio.sleep(3600)
    await asyncio.gather(*[m.remove_roles(role, reason="Время мьюта истекло") for m in members])
    await ctx.send(embed=e_ok("Массовый мут снят", "Все участники размьючены."))
    logger.info("Mass unmute complete")


@bot.hybrid_command(with_app_command=True)
@commands.check(lambda ctx: is_admin(ctx.author))
async def adminmenu(ctx: commands.Context):
    """Открыть панель администратора."""
    embed = discord.Embed(
        title="Панель администратора",
        description=(
            "**Проверить YouTube каналы** — вручную запустить проверку новых видео.\n"
            "**Обновить ID последних видео** — сохранить ID текущих последних роликов.\n"
            "**Перезагрузить бота** — безопасно перезапустить процесс."
        ),
        color=discord.Color.gold(),
        timestamp=_now_dt()
    )
    await ctx.send(embed=embed, view=AdminMenuView())
    logger.info(f"Admin menu opened by {ctx.author}")


@bot.hybrid_command(with_app_command=True)
@commands.check(lambda ctx: is_admin(ctx.author))
async def getvideosid(ctx: commands.Context):
    """Обновить ID последних видео на YouTube-каналах."""
    await _fetch_and_save_latest_video_ids()
    await ctx.send(embed=e_ok("Готово", "ID последних видео обновлены."))


@bot.hybrid_command(with_app_command=True)
@commands.check(lambda ctx: is_admin(ctx.author))
async def check_yt(ctx: commands.Context):
    """Вручную проверить YouTube-каналы на новые видео."""
    await _check_youtube_channels(ctx.channel)


@bot.hybrid_command(with_app_command=True)
@commands.check(lambda ctx: is_admin(ctx.author))
async def spamtest(ctx: commands.Context, trigger: str = "multichannel"):
    """Тест антиспам-системы."""
    trigger = trigger.lower().strip()
    if trigger in ("multichannel", "channels"):
        fake_channels = list(range(SPAM_CHANNELS_THRESHOLD))
        now = _utcnow()
        log = user_message_log[ctx.author.id]
        for ch_id in fake_channels:
            log.append((now, ch_id))
        last_spam_alert.pop(ctx.author.id, None)
        await send_spam_alert(
            user=ctx.author,
            reason=f"[ТЕСТ] Сообщения в {len(fake_channels)} каналах за {SPAM_TIME_WINDOW // 60} мин.",
            details=f"Каналы (симуляция): {', '.join(f'`fake_channel_{c}`' for c in fake_channels)}\n*Тест командой `!spamtest`.*"
        )
        await ctx.send(embed=e_ok("Тест выполнен", "Тип: **multichannel**"))
    elif trigger == "everyone":
        last_spam_alert.pop(ctx.author.id, None)
        await send_spam_alert(
            user=ctx.author,
            reason="[ТЕСТ] Попытка использовать @everyone / @here без прав",
            details=f"Канал: {ctx.channel.mention}\n*Тест командой `!spamtest everyone`.*"
        )
        await ctx.send(embed=e_ok("Тест выполнен", "Тип: **everyone**"))
    else:
        await ctx.send(embed=e_err("Неизвестный тип", "Доступно: `multichannel`, `everyone`"))

# ---------------------------------------------------------------------------
# FUN COMMANDS
# ---------------------------------------------------------------------------

@bot.command(name="MrCarsen")
async def mrcarsen(ctx: commands.Context):
    await ctx.reply(random.choice(mr_carsen_messages))
    logger.info(f"Sent MrCarsen message to {ctx.author.id}")


@bot.command(name="золотойфонд")
async def zolotoy_fond(ctx: commands.Context):
    await ctx.reply(random.choice(gold_fund_messages))
    logger.info(f"Sent gold fund message to {ctx.author.id}")


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
        logger.info(f"{ctx.author.id} triggered ХУЯБЛЯ and was muted for 1 minute")
    else:
        logger.info(f"{ctx.author.id} triggered ХУЯБЛЯ but is admin — skipping mute")


@bot.command(name="рулетка")
async def roulette(ctx: commands.Context):
    if random.randint(1, 6) == 6:
        await ctx.reply("БАБАХ! You are dead. Not a big surprise.")
        role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
        if role and not ctx.author.guild_permissions.administrator:
            await ctx.author.add_roles(role, reason="Русская рулетка")
            logger.info(f"{ctx.author.id} lost the roulette and was muted for 1 minute")
            await asyncio.sleep(60)
            await ctx.author.remove_roles(role, reason="Время мьюта истекло")
        else:
            logger.info(f"{ctx.author.id} lost the roulette but is admin — skipping mute")
    else:
        await ctx.reply("**·щёлк·**\nФартовый однако!")
        logger.info(f"{ctx.author.id} won the roulette")

# ---------------------------------------------------------------------------
# BOMB COMMAND
# ---------------------------------------------------------------------------

# Состояние бомбы: guild_id -> {'number': int, 'end_time': datetime, 'task': Task}
bomb_info: dict[int, dict] = {}

@bot.hybrid_command(name="bomb", with_app_command=True)
async def bomb(ctx: commands.Context):
    """Заложить бомбу."""
    cooldown_end = get_bomb_cooldown(ctx.guild.id)
    if cooldown_end and _utcnow() < cooldown_end:
        time_left = int((cooldown_end - _utcnow()).total_seconds())
        await ctx.send(embed=e_err(
            "Команда недоступна",
            f"Попробуйте снова через **{seconds_to_human(time_left)}**."
        ))
        return

    view = ConfirmView(ctx.author)
    msg  = await ctx.send(f"{ctx.author.mention}, подтвердите действие:", view=view)
    view.message = msg
    await view.wait()

    if not view.value:
        remove_bomb_cooldown(ctx.guild.id)
        if view.value is False:
            await ctx.send(embed=e_info("Отменено", "Действие отменено."))
        else:
            await ctx.send(embed=e_info("Время вышло", "Действие отменено автоматически."))
        return

    number     = random.randint(1000, 2000)
    number_str = str(number)
    masked     = f"{number_str[0]}X{number_str[2]}X"

    bomb_info[ctx.guild.id] = {
        'number':   number,
        'end_time': _utcnow() + timedelta(hours=1),
    }
    set_bomb_cooldown(ctx.guild.id, _utcnow() + timedelta(days=7))

    embed = discord.Embed(
        title="Bomb has been planted.",
        description=(
            f"Пользователь {ctx.author.mention} заложил бомбу в чате!\n\n"
            f"Для разминирования: `!defuse <код>` или `/defuse <код>`\n"
            f"**На разминирование — 60 минут!**\n\n"
            f"Подсказка: **{masked}**"
        ),
        color=0xFF6B35,
        timestamp=_now_dt()
    )
    await ctx.send(embed=embed)
    logger.info(f"Bomb planted by {ctx.author} in {ctx.guild.id}. Mask: {masked}. Code: {number}")

    async def bomb_timer():
        await asyncio.sleep(3600)
        if ctx.guild.id in bomb_info:
            del bomb_info[ctx.guild.id]
            await ctx.send(embed=discord.Embed(
                title="Terrorist win!",
                description="Время вышло! Все участники чата замьючены на 1 час.",
                color=0xED4245, timestamp=_now_dt()
            ))
            role = discord.utils.get(ctx.guild.roles, id=MUTE_ROLE_ID)
            if role:
                members = [m for m in ctx.channel.members if m != ctx.guild.me and not m.guild_permissions.administrator and m.id != ctx.author.id]
                await asyncio.gather(*[m.add_roles(role, reason="Бомба взорвалась") for m in members])
                await asyncio.sleep(3600)
                await asyncio.gather(*[m.remove_roles(role, reason="Время мьюта истекло") for m in members])

    bomb_info[ctx.guild.id]['task'] = asyncio.create_task(bomb_timer())


@bot.hybrid_command(name="defuse", with_app_command=True)
async def defuse(ctx: commands.Context, guess: int):
    """Разминировать бомбу."""
    if ctx.guild.id not in bomb_info:
        await ctx.send(embed=e_info("Нет бомбы", "На сервере не заложена бомба."))
        return
    if guess == bomb_info[ctx.guild.id]['number']:
        task = bomb_info[ctx.guild.id].get('task')
        if task:
            task.cancel()
        del bomb_info[ctx.guild.id]
        embed = e_ok(
            "Bomb has been defused!",
            f"Пользователь {ctx.author.mention} угадал код и спас чат! "
        )
        await ctx.send(embed=embed)
        logger.info(f"Bomb defused by {ctx.author} in {ctx.guild.id}")
    else:
        await ctx.send(embed=e_err("Неверный код", "Попробуйте ещё раз!"))

# ---------------------------------------------------------------------------
# SUBSCRIBE COMMANDS
# ---------------------------------------------------------------------------

@bot.hybrid_command(with_app_command=True)
@commands.has_permissions(manage_roles=True)
async def subscribe(ctx: commands.Context):
    """Отправить кнопку подписки на уведомления (первый канал)."""
    role = discord.utils.get(ctx.guild.roles, id=YT_SUBSCRIBER_ROLE_ID)
    if not role:
        await ctx.send(embed=e_err("Роль не найдена"))
        return
    embed = discord.Embed(
        title=f"Подписка на уведомления",
        description=f"Нажмите кнопку ниже, чтобы получить или снять роль {role.mention}.",
        color=role.color, timestamp=_now_dt()
    )
    await ctx.send(embed=embed, view=SubscribeView(YT_SUBSCRIBER_ROLE_ID))


@bot.hybrid_command(with_app_command=True)
@commands.has_permissions(manage_roles=True)
async def subscribesecond(ctx: commands.Context):
    """Отправить кнопку подписки на уведомления (второй канал)."""
    role = discord.utils.get(ctx.guild.roles, id=SEC_YT_SUBSCRIBER_ROLE_ID)
    if not role:
        await ctx.send(embed=e_err("Роль не найдена"))
        return
    embed = discord.Embed(
        title=f"Подписка на уведомления",
        description=f"Нажмите кнопку ниже, чтобы получить или снять роль {role.mention}.",
        color=role.color, timestamp=_now_dt()
    )
    await ctx.send(embed=embed, view=SubscribeView(SEC_YT_SUBSCRIBER_ROLE_ID))

# ---------------------------------------------------------------------------
# HELP
# ---------------------------------------------------------------------------

@bot.tree.command(name="help", description="Показать справку по командам бота (видно только вам)")
async def help_command(interaction: discord.Interaction):
    embeds = []

    overview = discord.Embed(
        title="Справка по командам бота",
        description=(
            "Административные команды доступны как `/команда`, так и `!команда`.\n"
            "Развлекательные команды — только через префикс `!`.\n\n"
            "**Разделы:** Мут / Анмьют | Предупреждения | Развлечения"
        ),
        color=0x5865F2, timestamp=_now_dt()
    )
    embeds.append(overview)

    mute_embed = discord.Embed(title="Мут / Анмьют", color=0xFFA500, timestamp=_now_dt())
    mute_embed.add_field(name="/mute участник длительность [причина]",
                         value="Выдаёт мут. Форматы: `60s`, `30m`, `2h`, `1d`.", inline=False)
    mute_embed.add_field(name="/unmute участник",
                         value="Снимает мут немедленно.", inline=False)
    mute_embed.add_field(name="/mute_all [причина]",
                         value="Мьютит всех в канале на 1 час (только администраторы).", inline=False)
    embeds.append(mute_embed)

    warn_embed = discord.Embed(title="Предупреждения", color=0xFEE75C, timestamp=_now_dt())
    warn_embed.add_field(name="/warn участник [причина]",
                         value="Выдаёт предупреждение. При 3 варнах за 24ч — автомут на 24ч.", inline=False)
    warn_embed.add_field(name="/warnings участник", value="Показывает предупреждения.", inline=False)
    warn_embed.add_field(name="/warnremove участник", value="Удаляет все предупреждения.", inline=False)
    embeds.append(warn_embed)

    fun_embed = discord.Embed(title="Развлечения (только !)", color=0x57F287, timestamp=_now_dt())
    fun_embed.add_field(name="!рулетка",       value="Русская рулетка. Проигравший получает мут на 1 мин.", inline=False)
    fun_embed.add_field(name="!bomb",           value="Заложить бомбу. 60 мин на разминирование командой `!defuse`.", inline=False)
    fun_embed.add_field(name="!defuse <код>",   value="Ввести код разминирования бомбы.", inline=False)
    fun_embed.add_field(name="!MrCarsen",       value="Случайная цитата МрКарсена.", inline=False)
    fun_embed.add_field(name="!золотойфонд",    value="Случайное сообщение из золотого фонда.", inline=False)
    fun_embed.add_field(name="!неумничай",      value="Послать умника.", inline=False)
    fun_embed.add_field(name="!аможетбытьты",   value="КТО?! Я?!", inline=False)
    fun_embed.add_field(name="!пошёлтынахуй",   value="Та за що, плять?..", inline=False)
    fun_embed.add_field(name="!ХУЯБЛЯ",         value="БАН! Мут на 1 минуту.", inline=False)
    embeds.append(fun_embed)

    await interaction.response.send_message(embeds=embeds, ephemeral=True)

# ---------------------------------------------------------------------------
# PERIODIC TASKS
# ---------------------------------------------------------------------------

@tasks.loop(minutes=1)
async def check_mutes():
    try:
        now = _utcnow()
        for user_id, mute_info in list(get_mutes().items()):
            try:
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
                role = discord.utils.get(guild.roles, id=MUTE_ROLE_ID)
                if role and role in member.roles:
                    await member.remove_roles(role, reason="Время мьюта истекло")
                remove_mute(user_id)
                logger.info(f"Auto-unmuted {user_id}")
                await send_mod_log("Мут истёк", LOG_COLORS["join"], member)
            except Exception as e:
                logger.error(f"Auto-unmute error for user {user_id}: {e}")
    except Exception as e:
        logger.error(f"check_mutes task fatal error: {e}")


@tasks.loop(minutes=15)
async def check_youtube():
    await _check_youtube_channels()


@check_mutes.before_loop
@check_youtube.before_loop
async def before_tasks():
    await bot.wait_until_ready()

# ---------------------------------------------------------------------------
# STARTUP
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_TOKEN not found in .env!")
    else:
        bot.run(DISCORD_TOKEN)