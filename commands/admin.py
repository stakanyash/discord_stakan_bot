"""Административные команды: adminmenu, getvideosid, check_yt, testyt, spamtest, bomb, defuse."""

import asyncio
import random

import discord
from discord.ext import commands

from config import MUTE_ROLE_ID
from moderation_core import is_admin
from views import AdminMenuView, ConfirmView
from youtube import fetch_and_save_latest_video_ids, check_youtube_channels
from antispam import (
    user_message_log,
    last_spam_alert,
    send_spam_alert,
    SPAM_TIME_WINDOW,
    SPAM_CHANNELS_THRESHOLD,
)
from database import (
    get_bomb_cooldown,
    set_bomb_cooldown,
    remove_bomb_cooldown,
)
from embeds import e_ok, e_err, e_info, e_warn
from moderation_core import seconds_to_human, _utcnow

# Состояние бомбы: guild_id -> {'number': int, 'end_time': datetime, 'task': Task}
bomb_info: dict[int, dict] = {}


def register(bot):

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
        )
        await ctx.send(embed=embed, view=AdminMenuView())

    @bot.hybrid_command(with_app_command=True)
    @commands.check(lambda ctx: is_admin(ctx.author))
    async def getvideosid(ctx: commands.Context):
        """Обновить ID последних видео на YouTube-каналах."""
        await fetch_and_save_latest_video_ids()
        await ctx.send(embed=e_ok("Готово", "ID последних видео обновлены."))

    @bot.hybrid_command(with_app_command=True)
    @commands.check(lambda ctx: is_admin(ctx.author))
    async def check_yt(ctx: commands.Context):
        """Вручную проверить YouTube-каналы на новые видео."""
        await check_youtube_channels(reply_channel=ctx.channel, bot=ctx.bot)

    @bot.hybrid_command(with_app_command=True)
    @commands.check(lambda ctx: is_admin(ctx.author))
    async def testyt(ctx: commands.Context, channel_index: int = 1):
        """Протестировать уведомление о видео (отправит в текущий канал)."""
        from youtube import _get_youtube_service, _send_video_notification
        from config import (
            YOUTUBE_API_KEYS,
            YOUTUBE_CHANNEL_ID_1,
            YOUTUBE_CHANNEL_ID_2,
        )

        yt_configs = {
            1: (YOUTUBE_CHANNEL_ID_1, "<@&1104385788797534228>", "На канале какая-то движуха. А ну-ка глянем"),
            2: (YOUTUBE_CHANNEL_ID_2, "<@&1265571159601319989>", "На втором канате что-то появилось. Давайте-ка заценим"),
        }
        if channel_index not in yt_configs:
            await ctx.send(embed=e_err("Ошибка", "Укажите 1 или 2."))
            return

        ch_id, mention, text = yt_configs[channel_index]
        sent = False

        for api_key in YOUTUBE_API_KEYS:
            youtube = _get_youtube_service(api_key)
            try:
                req = youtube.search().list(part="snippet", channelId=ch_id, order="date", maxResults=1)
                resp = req.execute()
                if resp.get('items'):
                    item = resp['items'][0]
                    if item['id']['kind'] != 'youtube#video':
                        await ctx.send(embed=e_err("Ошибка", "Последний элемент не является видео."))
                        return
                    await _send_video_notification(ctx.channel, ch_id, item, text, mention)
                    await ctx.send(embed=e_ok("Тест выполнен", "Уведомление отправлено выше."), ephemeral=True)
                    sent = True
                else:
                    await ctx.send(embed=e_err("Ошибка", "Не найдено видео на канале."))
                break
            except Exception as e:
                if 'quotaExceeded' in str(e):
                    continue
                else:
                    await ctx.send(embed=e_err("Ошибка YouTube API", str(e)[:200]))
                    return

        if not sent:
            await ctx.send(embed=e_err("Ошибка", "Не удалось получить видео. Возможно, лимит API исчерпан."))

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
                details=f"Каналы (симуляция): {', '.join(f'`fake_channel_{c}`' for c in fake_channels)}\n*Тест командой `!spamtest`.*",
                bot=ctx.bot,
            )
            await ctx.send(embed=e_ok("Тест выполнен", "Тип: **multichannel**"))
        elif trigger == "everyone":
            last_spam_alert.pop(ctx.author.id, None)
            await send_spam_alert(
                user=ctx.author,
                reason="[ТЕСТ] Попытка использовать @everyone / @here без прав",
                details=f"Канал: {ctx.channel.mention}\n*Тест командой `!spamtest everyone`.*",
                bot=ctx.bot,
            )
            await ctx.send(embed=e_ok("Тест выполнен", "Тип: **everyone**"))
        else:
            await ctx.send(embed=e_err("Неизвестный тип", "Доступно: `multichannel`, `everyone`"))

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
        msg = await ctx.send(f"{ctx.author.mention}, подтвердите действие:", view=view)
        view.message = msg
        await view.wait()

        if not view.value:
            remove_bomb_cooldown(ctx.guild.id)
            if view.value is False:
                await ctx.send(embed=e_info("Отменено", "Действие отменено."))
            else:
                await ctx.send(embed=e_info("Время вышло", "Действие отменено автоматически."))
            return

        number = random.randint(1000, 2000)
        number_str = str(number)
        masked = f"{number_str[0]}X{number_str[2]}X"

        bomb_info[ctx.guild.id] = {
            'number': number,
            'end_time': _utcnow() + __import__('datetime', fromlist=['timedelta']).timedelta(hours=1),
        }
        set_bomb_cooldown(ctx.guild.id, _utcnow() + __import__('datetime', fromlist=['timedelta']).timedelta(days=7))

        embed = discord.Embed(
            title="Bomb has been planted.",
            description=(
                f"Пользователь {ctx.author.mention} заложил бомбу в чате!\n\n"
                f"Для разминирования: `!defuse <код>` или `/defuse <код>`\n"
                f"**На разминирование — 60 минут!**\n\n"
                f"Подсказка: **{masked}**"
            ),
            color=0xFF6B35,
        )
        await ctx.send(embed=embed)

        async def bomb_timer():
            await asyncio.sleep(3600)
            if ctx.guild.id in bomb_info:
                del bomb_info[ctx.guild.id]
                await ctx.send(embed=discord.Embed(
                    title="Terrorist win!",
                    description="Время вышло! Все участники чата замьючены на 1 час.",
                    color=0xED4245,
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
            await ctx.send(embed=e_info("Нет бомы", "На сервере не заложена бомба."))
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
        else:
            await ctx.send(embed=e_err("Неверный код", "Попробуйте ещё раз!"))
