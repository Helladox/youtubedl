#!/usr/bin/env python3
"""
YouTube Telegram Downloader Bot with:
- Format selection
- Auto merge video+audio if needed
- Thumbnail preview
"""

import os
import uuid
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp
import requests

# --- Config ---
API_ID = int(os.getenv("API_ID", "20723624"))
API_HASH = os.getenv("API_HASH", "6b2d857266669bab971257d8312af741")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7980540583:AAHzzJgGcR6tBAkDaamsz9XfhifV1rO4pJM")
COOKIES_FILE = os.path.join(os.getcwd(), "cookies.txt")
logging.basicConfig(level=logging.INFO)

sessions = {}

# --- Extract available formats (video only + audio merged later) ---
def get_video_formats(url):
    ydl_opts = {
        'quiet': True,
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'skip_download': True,
        'forcejson': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = {}
    for fmt in info.get('formats', []):
        if fmt.get('vcodec') != 'none':  # all video formats, audio may be none
            format_id = fmt.get('format_id')
            ext = fmt.get('ext')
            height = fmt.get('height') or ''
            fps = fmt.get('fps') or ''
            resolution = f"{height}p {fps}fps".strip() if height else fmt.get('format_note', '')
            formats[format_id] = {'ext': ext, 'resolution': resolution}

    return info.get('title', 'Unknown Title'), formats, info.get("thumbnail")

# --- Initialize bot ---
bot = Client("yt_dlp_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.command("start"))
async def start(_, message):
    await message.reply_text("👋 Send me a YouTube URL, and I'll show you available download options.")

def is_youtube_url(text):
    return text.startswith("http") and ("youtube.com" in text or "youtu.be" in text)

@bot.on_message(filters.private & filters.text)
async def handle_url(_, message):
    url = message.text.strip()
    if not is_youtube_url(url):
        return await message.reply_text("Please send a valid YouTube URL.")

    msg = await message.reply_text("⏳ Fetching formats...")

    try:
        title, formats, thumbnail = get_video_formats(url)
    except Exception as e:
        return await msg.edit(f"❌ Error fetching info:\n`{e}`")

    if not formats:
        return await msg.edit("❌ No downloadable formats found.")

    session_id = str(uuid.uuid4())
    sessions[session_id] = {'url': url, 'title': title, 'formats': formats, 'thumbnail': thumbnail}

    buttons = []
    for itag, fmt in sorted(formats.items(), key=lambda x: int(x[0])):
        buttons.append([InlineKeyboardButton(fmt['resolution'], callback_data=f"{session_id}|{itag}")])

    await msg.edit(
        f"🎬 *{title}*\nSelect resolution to download:",
        parse_mode=None,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@bot.on_callback_query()
async def handle_download(client, callback_query):
    data = callback_query.data
    session_id, itag = data.split("|")
    session = sessions.get(session_id)

    if not session:
        return await callback_query.answer("Session expired. Please resend the link.", show_alert=True)

    await callback_query.answer("Downloading...", show_alert=False)
    url = session['url']
    title = session['title']
    thumbnail_url = session['thumbnail']
    out_path = f"{session_id}.mp4"

    ydl_opts = {
        'format': f"{itag}+bestaudio/best",
        'outtmpl': out_path,
        'merge_output_format': 'mp4',
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'quiet': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        thumb_file = None
        if thumbnail_url:
            thumb_file = f"{session_id}.jpg"
            r = requests.get(thumbnail_url)
            with open(thumb_file, "wb") as f:
                f.write(r.content)

        await client.send_video(
            chat_id=callback_query.message.chat.id,
            video=out_path,
            caption=title,
            thumb=thumb_file if os.path.exists(thumb_file) else None
        )

        os.remove(out_path)
        if thumb_file and os.path.exists(thumb_file):
            os.remove(thumb_file)
        del sessions[session_id]

    except Exception as e:
        await client.send_message(callback_query.message.chat.id, f"❌ Failed to download:\n`{e}`")

if __name__ == "__main__":
    print("Bot is running...")
    bot.run()
