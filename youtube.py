"""YouTube: API-функции, проверка каналов, уведомления."""

import discord
from datetime import datetime, timedelta, timezone

import googleapiclient.discovery
import googleapiclient.errors

from config import (
    YOUTUBE_API_KEYS,
    YOUTUBE_CHANNEL_ID_1,
    YOUTUBE_CHANNEL_ID_2,
    NOTIFICATION_CHANNEL_ID,
)
from database import (
    is_video_known,
    add_video_to_history,
    set_last_video_id,
)
from embeds import LOG_COLORS, e_ok, e_err


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def dt_from_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_youtube_service(api_key: str):
    return googleapiclient.discovery.build('youtube', 'v3', developerKey=api_key)


async def fetch_all_videos_to_history() -> int:
    """Парсит все публичные видео со всех YouTube каналов и сохраняет в video_history."""
    total_saved = 0
    for api_key in YOUTUBE_API_KEYS:
        youtube = _get_youtube_service(api_key)
        try:
            for ch_id in (YOUTUBE_CHANNEL_ID_1, YOUTUBE_CHANNEL_ID_2):
                page_token = None
                while True:
                    req = youtube.search().list(
                        part="snippet",
                        channelId=ch_id,
                        order="date",
                        maxResults=50,
                        type="video",
                        pageToken=page_token,
                    )
                    resp = req.execute()
                    for item in resp.get('items', []):
                        if item['id']['kind'] == 'youtube#video':
                            video_id = item['id']['videoId']
                            if not is_video_known(ch_id, video_id):
                                add_video_to_history(ch_id, video_id)
                                total_saved += 1
                    page_token = resp.get('nextPageToken')
                    if not page_token:
                        break
            return total_saved
        except googleapiclient.errors.HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e):
                pass  # logged below
            else:
                raise
    return total_saved


async def fetch_and_save_latest_video_ids():
    """Обновляет ID последних видео без уведомлений."""
    for api_key in YOUTUBE_API_KEYS:
        youtube = _get_youtube_service(api_key)
        try:
            for ch_id in (YOUTUBE_CHANNEL_ID_1, YOUTUBE_CHANNEL_ID_2):
                req = youtube.search().list(part="snippet", channelId=ch_id, order="date", maxResults=1)
                resp = req.execute()
                if resp.get('items'):
                    item = resp['items'][0]
                    if item['id']['kind'] == 'youtube#video':
                        video_id = item['id']['videoId']
                        set_last_video_id(ch_id, video_id)
                        add_video_to_history(ch_id, video_id)
                    else:
                        pass  # non-video item
            return
        except googleapiclient.errors.HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e):
                pass
            else:
                raise


async def _send_video_notification(channel, ch_id: str, item: dict, text: str, mention: str):
    """Отправляет уведомление о новом видео в указанный канал."""
    video_id = item['id']['videoId']
    title = item['snippet']['title']
    channel_name = item['snippet']['channelTitle']
    published_at = dt_from_iso(item['snippet']['publishedAt'])
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    thumbnails = item['snippet']['thumbnails']
    thumb_url = thumbnails.get('maxres', thumbnails.get('high', thumbnails.get('medium', {}))).get('url', '')

    embed = discord.Embed(
        title=title,
        url=video_url,
        description=f"📺 **{channel_name}**\n🔗 {video_url}\n\n{text}",
        color=LOG_COLORS["yt"],
        timestamp=published_at,
    )
    if thumb_url:
        embed.set_image(url=thumb_url)
    embed.set_footer(text="Новое видео")

    if mention:
        await channel.send(mention, embed=embed)
    else:
        await channel.send(embed=embed)


async def check_youtube_channels(reply_channel=None, bot=None):
    """Проверяет новые видео и отправляет уведомления."""
    import discord
    notification_channel = bot.get_channel(NOTIFICATION_CHANNEL_ID) if bot else None
    if not notification_channel:
        return

    yt_configs = [
        (YOUTUBE_CHANNEL_ID_1, "<@&1104385788797534228>", "На канале какая-то движуха. А ну-ка глянем"),
        (YOUTUBE_CHANNEL_ID_2, "<@&1265571159601319989>", "На втором канале что-то появилось. Давайте-ка заценим"),
    ]

    for api_key in YOUTUBE_API_KEYS:
        youtube = _get_youtube_service(api_key)
        try:
            for ch_id, mention, text in yt_configs:
                req = youtube.search().list(part="snippet", channelId=ch_id, order="date", maxResults=1)
                resp = req.execute()
                if resp.get('items'):
                    item = resp['items'][0]
                    if item['id']['kind'] != 'youtube#video':
                        continue

                    video_id = item['id']['videoId']
                    published_at = dt_from_iso(item['snippet']['publishedAt'])

                    # Если видео уже известно — не уведомляем
                    if is_video_known(ch_id, video_id):
                        continue

                    # Проверка свежести: видео должно быть не старше 2 часов
                    video_age_seconds = (_utcnow() - published_at).total_seconds()
                    if video_age_seconds > 7200:
                        # Всё равно добавляем в историю, чтобы не проверять это видео снова
                        add_video_to_history(ch_id, video_id)
                        continue

                    # Видео новое и свежее — добавляем в историю и уведомляем
                    add_video_to_history(ch_id, video_id)
                    set_last_video_id(ch_id, video_id)

                    await _send_video_notification(notification_channel, ch_id, item, text, mention)

            if reply_channel:
                await reply_channel.send(embed=e_ok("YouTube проверен", "Каналы успешно проверены."))
            return
        except googleapiclient.errors.HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e):
                pass
            else:
                if reply_channel:
                    await reply_channel.send(embed=e_err("Ошибка YouTube API", str(e)[:200]))
                raise
