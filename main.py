import json
import asyncio
import random
import os
import time
import requests
import psutil
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.error import BadRequest, TelegramError, Forbidden

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8684382287:AAE17nfdgrbndBSl1wG9MWmiW9GdeErkTg4")
REMOVE_BG_API = "f3Se7SVDqpvsM5TLknPKN6Cz"
IMGBB_API = "62736b1fc27c5c6bb91063f2ec92913b"
BOT_USERNAME = "IMAGE_TO_BACKREMOVE_bot"

OWNER_ID = 8441236350
PING_VIDEO = "https://files.catbox.moe/o57l0y.mp4"
START_VIDEO = "https://files.catbox.moe/wnw0ds.mp4"
SOURCE_PREVIEW = "https://files.catbox.moe/jizede.jpg"
GROUP_LINK = "https://t.me/+uRWDvRhCiNo0OWFl"

USERS_FILE = "users.json"
CONFIG_FILE = "config.json"
AUTO_DELETE_SECONDS = 60
START_TIME = time.time()

GREET = [
    "<b>🌸 ʜᴇʟʟᴏ ᴛʜᴇʀᴇ...</b>",
    "<b>✨ ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ...</b>",
    "<b>💫 ʟᴏᴀᴅɪɴɢ ᴍᴀɢɪᴄ...</b>",
    "<b>🌹 ʜᴇʏ ᴄᴜᴛɪᴇ...</b>",
    "<b>🔮 sᴜᴍᴍᴏɴɪɴɢ ʙᴏᴛ...</b>",
]

# ──────── Persistence ────────
try:
    with open(USERS_FILE) as f:
        users = json.load(f)
except Exception:
    users = {}

try:
    with open(CONFIG_FILE) as f:
        config = json.load(f)
except Exception:
    config = {}

ALLOWED_GROUP_ID = config.get("allowed_group_id")  # int or None
banned = set(int(x) for x in config.get("banned", []))

mode = {}


def save():
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def save_config():
    config["allowed_group_id"] = ALLOWED_GROUP_ID
    config["banned"] = sorted(banned)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def is_owner(uid) -> bool:
    try:
        return int(uid) == OWNER_ID
    except (TypeError, ValueError):
        return False


def is_banned(uid) -> bool:
    try:
        return int(uid) in banned
    except (TypeError, ValueError):
        return False


def in_allowed_group(chat) -> bool:
    return (
        chat is not None
        and chat.type in ("group", "supergroup")
        and ALLOWED_GROUP_ID is not None
        and chat.id == ALLOWED_GROUP_ID
    )


def is_unlimited(uid, chat) -> bool:
    return is_owner(uid) or in_allowed_group(chat)


async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Allow private chats and the one authorized group; leave any other group; ignore banned."""
    user = update.effective_user
    if user is not None and is_banned(user.id) and not is_owner(user.id):
        return False
    chat = update.effective_chat
    if chat is None:
        return False
    if chat.type == "private":
        return True
    if in_allowed_group(chat):
        return True
    if chat.type in ("group", "supergroup", "channel"):
        try:
            await context.bot.leave_chat(chat.id)
        except (BadRequest, TelegramError):
            pass
    return False


def reset(uid):
    today = str(datetime.now().date())
    if users[uid].get("last") != today:
        users[uid]["credits"] = 2
        users[uid]["last"] = today


def format_uptime() -> str:
    seconds = int(time.time() - START_TIME)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}ʜ:{m}ᴍ:{s}s"


async def _delete_later(message, delay):
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except (BadRequest, TelegramError):
        pass


def schedule_delete(message, delay=AUTO_DELETE_SECONDS):
    if message is not None:
        asyncio.create_task(_delete_later(message, delay))


async def safe_edit(message, text):
    try:
        await message.edit_text(text, parse_mode="HTML")
    except BadRequest:
        pass
    except TelegramError:
        pass


# ──────── Source-code button helper ────────
def source_button() -> InlineKeyboardButton:
    return InlineKeyboardButton("👨‍💻 sᴏᴜʀᴄᴇ ᴄᴏᴅᴇ", url=SOURCE_PREVIEW)


def source_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[source_button()]])


# ──────── Owner notification ────────
async def notify_owner(context, action: str, user, chat=None, **details):
    if user is None or int(user.id) == OWNER_ID:
        return
    parts = [f"🔔 <b>{action}</b>"]
    name = user.full_name or "Unknown"
    parts.append(f"👤 <a href=\"tg://user?id={user.id}\">{name}</a>")
    parts.append(f"🆔 <code>{user.id}</code>")
    if user.username:
        parts.append(f"📛 @{user.username}")
    if chat is not None and chat.type != "private":
        title = chat.title or str(chat.id)
        parts.append(f"💬 {title} (<code>{chat.id}</code>)")
    for k, v in details.items():
        parts.append(f"• {k}: {v}")
    try:
        await context.bot.send_message(
            OWNER_ID,
            "\n".join(parts),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except (BadRequest, TelegramError, Forbidden):
        pass


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥✨ ᴛᴀᴘ ᴛᴏ sᴇᴇ ᴍᴀɢɪᴄ ✨🔥", callback_data="remove")],
        [
            InlineKeyboardButton("🌐 ɴᴇᴛᴡᴏʀᴋ", url="https://t.me/+Imyf3M9TO5k1ODRl"),
            InlineKeyboardButton("🏠 ᴍʏ ʜᴏᴍᴇ", url="https://t.me/+dv_rcq5uIXhmMWM1"),
        ],
        [InlineKeyboardButton("🌟 ᴊᴏɪɴ ᴏᴜʀ ɢʀᴏᴜᴘ — ᴜɴʟɪᴍɪᴛᴇᴅ 🌟", url=GROUP_LINK)],
        [InlineKeyboardButton("📜💡 ʜᴇʟᴘ ᴀɴᴅ ᴄᴏᴍᴍᴀɴᴅs", callback_data="help")],
        [InlineKeyboardButton("👑 ᴍʏ ᴍᴀsᴛᴇʀ 🤴", url="https://t.me/YOUR_MADARA_BRO")],
        [
            InlineKeyboardButton("🖼 ɪᴍᴀɢᴇ → ʟɪɴᴋ", callback_data="upload"),
            InlineKeyboardButton("🔗 ʀᴇғᴇʀʀᴀʟ", callback_data="ref"),
        ],
        [source_button()],
    ])


# ──────── /start ────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, context):
        return

    uid = str(update.effective_user.id)
    chat = update.effective_chat
    ref_arg = context.args[0] if context.args else None

    if uid not in users:
        users[uid] = {"credits": 2, "refs": []}
        if ref_arg and ref_arg != uid and ref_arg in users:
            if uid not in users[ref_arg]["refs"]:
                users[ref_arg]["refs"].append(uid)
                users[ref_arg]["credits"] += 1

    reset(uid)
    save()

    await notify_owner(
        context, "ʙᴏᴛ sᴛᴀʀᴛᴇᴅ", update.effective_user, chat,
        ʀᴇғ=(ref_arg or "—"),
    )

    # Loading animation
    loading_1 = await update.message.reply_text(random.choice(GREET), parse_mode="HTML")
    frames = [
        "<b>ᴅɪηɢ ᴅᴏηɢ.❤️‍🔥</b>",
        "<b>ᴅɪηɢ ᴅᴏηɢ..❤️‍🔥</b>",
        "<b>𝐋ᴏᴠᴇ 𝐘ᴏᴜ</b>",
        "<b>𝐒ᴛᴀʀᴛɪɴɢ...</b>",
        "<b>𝐈ᴍᴀɢᴇ 𝐂ᴏɴᴠᴇʀᴛᴇʀ</b>",
        "<b>𝐈ᴍᴀɢᴇ 𝐂ᴏɴᴠᴇʀᴛᴇʀ ✨</b>",
        "<b>sᴛᴧʀᴛed!🥀</b>",
    ]
    for frame in frames:
        await asyncio.sleep(0.3)
        await safe_edit(loading_1, frame)
    await asyncio.sleep(0.3)
    try:
        await loading_1.delete()
    except (BadRequest, TelegramError):
        pass

    caption = f"""```
┌────── ˹ ɪɴғᴏʀᴍᴀᴛɪᴏɴ ˼──────🔹
┆◍ ʜєʏ, {update.effective_user.first_name} 🥀
┆◍ ɪ ᴧϻ {context.bot.first_name}
└──────────────────────•

✨ I can remove backgrounds & convert images to public links
💰 You get 2 free credits every day

🌟 JOIN OUR GROUP FOR UNLIMITED ACCESS:
{GROUP_LINK}

•──────────────────────•
⌯ ᴘᴏᴡєʀєᴅ ʙʏ » |𝐌 ᴀ ᴅ ᴀ ʀ ᴀ •|
•──────────────────────•
```"""

    try:
        sent = await update.message.reply_video(
            video=START_VIDEO,
            has_spoiler=True,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )
    except (BadRequest, TelegramError):
        # Fallback to text-only menu if Telegram can't fetch the video
        sent = await update.message.reply_text(
            caption, parse_mode="Markdown", reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )

    schedule_delete(sent)


# ──────── /referral callback ────────
async def ref(update, context):
    if not await gate(update, context):
        return
    q = update.callback_query
    uid = str(q.from_user.id)
    link = f"https://t.me/{BOT_USERNAME}?start={uid}"
    await q.answer()
    await notify_owner(context, "ᴄʟɪᴄᴋᴇᴅ ʀᴇғᴇʀʀᴀʟ", q.from_user, update.effective_chat)
    sent = await q.message.reply_text(
        f"🔗 <b>ʏᴏᴜʀ ʀᴇғᴇʀʀᴀʟ ʟɪɴᴋ:</b>\n{link}\n\n"
        "🎁 sʜᴀʀᴇ ɪᴛ ᴀɴᴅ ᴇᴀʀɴ +1 ᴄʀᴇᴅɪᴛ ᴘᴇʀ ɴᴇᴡ ᴜsᴇʀ!",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=source_keyboard(),
    )
    schedule_delete(sent)


# ──────── help text ────────
def help_text() -> str:
    return (
        "📜 <b>ʜᴇʟᴘ &amp; ᴄᴏᴍᴍᴀɴᴅs</b>\n\n"
        "🔥 /start — sʜᴏᴡ ᴍᴀɪɴ ᴍᴇɴᴜ\n"
        "🏓 /ping — ᴄʜᴇᴄᴋ ʟᴀᴛᴇɴᴄʏ &amp; sʏsᴛᴇᴍ sᴛᴀᴛs\n"
        "🆔 /id — ʏᴏᴜʀ ᴛᴇʟᴇɢʀᴀᴍ ɪᴅ\n"
        "🧠 ʀᴇᴍᴏᴠᴇ ʙɢ — ᴛᴀᴘ ᴛʜᴇ ᴍᴀɢɪᴄ ʙᴜᴛᴛᴏɴ &amp; sᴇɴᴅ ᴀ ᴘʜᴏᴛᴏ\n"
        "🖼 ɪᴍᴀɢᴇ → ʟɪɴᴋ — ɢᴇᴛ ᴀ sʜᴀʀᴇᴀʙʟᴇ ᴜʀʟ\n"
        "🔗 ʀᴇғᴇʀʀᴀʟ — sʜᴀʀᴇ ʏᴏᴜʀ ʟɪɴᴋ ᴀɴᴅ ᴇᴀʀɴ ᴄʀᴇᴅɪᴛs\n"
        "💰 ᴄʀᴇᴅɪᴛs — 2 ғʀᴇᴇ ᴘᴇʀ ᴅᴀʏ + 1 ᴘᴇʀ ʀᴇғᴇʀʀᴀʟ\n"
        f"🌟 <a href=\"{GROUP_LINK}\">ᴊᴏɪɴ ᴏᴜʀ ɢʀᴏᴜᴘ</a> — ᴜɴʟɪᴍɪᴛᴇᴅ ᴜsᴀɢᴇ ɪɴsɪᴅᴇ\n\n"
        "👑 <b>ᴏᴡɴᴇʀ ᴄᴏᴍᴍᴀɴᴅs</b>\n"
        "📢 /broadcast &lt;ᴍsɢ&gt; — sᴇɴᴅ ᴛᴏ ᴀʟʟ ᴜsᴇʀs\n"
        "📊 /stats — ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs\n"
        "🔧 /setgroup — ᴀᴜᴛʜᴏʀɪᴢᴇ ᴄᴜʀʀᴇɴᴛ ɢʀᴏᴜᴘ\n"
        "🚫 /ban &lt;ɪᴅ&gt; — ʙᴀɴ ᴜsᴇʀ\n"
        "✅ /unban &lt;ɪᴅ&gt; — ʟɪғᴛ ʙᴀɴ\n"
        "📋 /banned — sᴇᴇ ʙᴀɴɴᴇᴅ ʟɪsᴛ\n\n"
        "⏳ <i>ᴀʟʟ ʙᴏᴛ ᴍᴇssᴀɢᴇs ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇ ᴀғᴛᴇʀ 1 ᴍɪɴᴜᴛᴇ.</i>"
    )


# ──────── help callback ────────
async def help_cb(update, context):
    if not await gate(update, context):
        return
    q = update.callback_query
    await q.answer()
    await notify_owner(context, "ᴏᴘᴇɴᴇᴅ ʜᴇʟᴘ", q.from_user, update.effective_chat)
    sent = await q.message.reply_text(
        help_text(),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=source_keyboard(),
    )
    schedule_delete(sent)


# ──────── /help command ────────
async def help_cmd(update, context):
    if not await gate(update, context):
        return
    await notify_owner(context, "ᴏᴘᴇɴᴇᴅ /ʜᴇʟᴘ", update.effective_user, update.effective_chat)
    sent = await update.message.reply_text(
        help_text(),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=source_keyboard(),
    )
    schedule_delete(sent)


# ──────── /id command ────────
async def id_cmd(update, context):
    if not await gate(update, context):
        return
    user = update.effective_user
    chat = update.effective_chat
    text = (
        "🆔 <b>ʏᴏᴜʀ ɪᴅ</b>\n\n"
        f"👤 <code>{user.id}</code>\n"
        f"📛 @{user.username or '—'}\n"
        f"💬 ᴄʜᴀᴛ: <code>{chat.id}</code>"
    )
    sent = await update.message.reply_text(text, parse_mode="HTML", reply_markup=source_keyboard())
    schedule_delete(sent)


# ──────── mode set callback ────────
async def set_mode(update, context):
    if not await gate(update, context):
        return
    q = update.callback_query
    uid = str(q.from_user.id)

    if q.data == "remove":
        mode[uid] = "remove"
        await q.answer()
        await notify_owner(context, "ᴄʜᴏsᴇ: ʀᴇᴍᴏᴠᴇ ʙɢ", q.from_user, update.effective_chat)
        sent = await q.message.reply_text(
            "🧠✨ sᴇɴᴅ ᴀɴ ɪᴍᴀɢᴇ ᴛᴏ ʀᴇᴍᴏᴠᴇ ɪᴛs ʙᴀᴄᴋɢʀᴏᴜɴᴅ",
            reply_markup=source_keyboard(),
        )
        schedule_delete(sent)

    elif q.data == "upload":
        mode[uid] = "upload"
        await q.answer()
        await notify_owner(context, "ᴄʜᴏsᴇ: ɪᴍᴀɢᴇ → ʟɪɴᴋ", q.from_user, update.effective_chat)
        sent = await q.message.reply_text(
            "📤🌐 sᴇɴᴅ ᴀɴ ɪᴍᴀɢᴇ ᴛᴏ ᴜᴘʟᴏᴀᴅ",
            reply_markup=source_keyboard(),
        )
        schedule_delete(sent)


# ──────── photo handler ────────
async def handle_photo(update, context):
    if not await gate(update, context):
        return

    uid = str(update.effective_user.id)
    chat = update.effective_chat
    unlimited = is_unlimited(uid, chat)

    if uid not in users:
        users[uid] = {"credits": 2, "refs": []}
    reset(uid)

    if not unlimited and users[uid]["credits"] <= 0:
        sent = await update.message.reply_text(
            "❌ ɴᴏ ᴄʀᴇᴅɪᴛs ʟᴇғᴛ! ᴛʀʏ ᴀɢᴀɪɴ ᴛᴏᴍᴏʀʀᴏᴡ 🥀",
            reply_markup=source_keyboard(),
        )
        schedule_delete(sent)
        return

    file = await update.message.photo[-1].get_file()
    img_url = file.file_path

    user_mode = mode.get(uid, "remove")
    await notify_owner(
        context, f"ᴜsᴇᴅ: {user_mode.upper()}",
        update.effective_user, chat,
        ᴜɴʟɪᴍɪᴛᴇᴅ=("ʏᴇs" if unlimited else "ɴᴏ"),
    )

    # UPLOAD MODE
    if user_mode == "upload":
        if not unlimited:
            users[uid]["credits"] -= 1
            save()
        try:
            img_bytes = requests.get(img_url, timeout=30).content
            res = requests.post(
                "https://api.imgbb.com/1/upload",
                params={"key": IMGBB_API},
                files={"image": img_bytes},
                timeout=30,
            )
            data = res.json()
        except Exception:
            sent = await update.message.reply_text(
                "❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ", reply_markup=source_keyboard()
            )
            schedule_delete(sent)
            return

        if not data.get("success"):
            sent = await update.message.reply_text(
                "❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ", reply_markup=source_keyboard()
            )
            schedule_delete(sent)
            return

        sent = await update.message.reply_text(
            f"🌐✨ <b>ʏᴏᴜʀ ɪᴍᴀɢᴇ ʟɪɴᴋ:</b>\n{data['data']['url']}",
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=source_keyboard(),
        )
        schedule_delete(sent)
        return

    # REMOVE BACKGROUND
    if not unlimited:
        users[uid]["credits"] -= 1
        save()
    try:
        res = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            data={"image_url": img_url},
            headers={"X-Api-Key": REMOVE_BG_API},
            timeout=60,
        )
    except Exception:
        sent = await update.message.reply_text(
            "❌ ʙɢ ʀᴇᴍᴏᴠᴇ ғᴀɪʟᴇᴅ", reply_markup=source_keyboard()
        )
        schedule_delete(sent)
        return

    if res.status_code != 200:
        sent = await update.message.reply_text(
            "❌ ʙɢ ʀᴇᴍᴏᴠᴇ ғᴀɪʟᴇᴅ", reply_markup=source_keyboard()
        )
        schedule_delete(sent)
        return

    sent = await update.message.reply_photo(res.content, reply_markup=source_keyboard())
    schedule_delete(sent)


# ──────── /ping ────────
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, context):
        return
    t0 = time.time()
    pinging = await update.message.reply_text("🏓 ᴘɪɴɢɪɴɢ...")
    ping_ms = (time.time() - t0) * 1000

    try:
        cpu = psutil.cpu_percent(interval=0.4)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
    except Exception:
        cpu = ram = disk = 0.0

    await notify_owner(
        context, "ᴜsᴇᴅ /ᴘɪɴɢ",
        update.effective_user, update.effective_chat,
        ʟᴀᴛᴇɴᴄʏ=f"{ping_ms:.2f}ᴍs",
    )

    caption = (
        "<b>sᴛᴧʀᴛed!</b>\n\n"
        f"🏓 <b>ᴘɪɴɢ..ᴩᴏɴɢ</b> : {ping_ms:.3f}\n"
        "🌺 <b>sʏsᴛᴇᴍ sᴛᴀᴛs</b> :\n\n"
        f":⧽ ᴜᴩᴛɪᴍᴇ : {format_uptime()}\n"
        f":⧽ ʀᴀᴍ : {ram}%\n"
        f":⧽ ᴄᴩᴜ : {cpu}%\n"
        f":⧽ ᴅɪsᴋ : {disk}%\n"
        f":⧽ ᴩʏ-ᴛɢᴄᴀʟʟs : 0.436ᴍs\n"
        ':⧽ ʙʏ » <a href="http://t.me/YOUR_MADARA_BRO">|𝐌 ᴀ ᴅ ᴀ ʀ ᴀ •|</a>'
    )

    try:
        await pinging.delete()
    except (BadRequest, TelegramError):
        pass

    try:
        sent = await update.message.reply_video(
            video=PING_VIDEO,
            caption=caption,
            parse_mode="HTML",
            has_spoiler=True,
            reply_markup=source_keyboard(),
        )
    except (BadRequest, TelegramError):
        sent = await update.message.reply_text(
            caption, parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=source_keyboard(),
        )

    schedule_delete(sent)


# ──────── /broadcast (owner only) ────────
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, context):
        return
    uid = update.effective_user.id
    if not is_owner(uid):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent)
        return

    targets = list(users.keys())
    if not targets:
        sent = await update.message.reply_text("📭 ɴᴏ ᴜsᴇʀs ᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ᴛᴏ.")
        schedule_delete(sent)
        return

    status = await update.message.reply_text(
        f"📢 <b>ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ ᴛᴏ {len(targets)} ᴜsᴇʀs...</b>",
        parse_mode="HTML",
    )

    success, fail, blocked = 0, 0, 0
    reply = update.message.reply_to_message

    for target_uid in targets:
        try:
            target_int = int(target_uid)
            if reply is not None:
                await context.bot.copy_message(
                    chat_id=target_int,
                    from_chat_id=reply.chat_id,
                    message_id=reply.message_id,
                )
            else:
                text = update.message.text.partition(" ")[2].strip()
                if not text:
                    try:
                        await status.edit_text(
                            "📢 <b>ᴜsᴀɢᴇ:</b>\n"
                            "/broadcast &lt;ᴍᴇssᴀɢᴇ&gt;\n"
                            "ᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴡɪᴛʜ /broadcast",
                            parse_mode="HTML",
                        )
                    except (BadRequest, TelegramError):
                        pass
                    schedule_delete(status)
                    return
                await context.bot.send_message(chat_id=target_int, text=text)
            success += 1
        except Forbidden:
            blocked += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)

    try:
        await status.edit_text(
            "📢 <b>ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇ</b>\n"
            f"✅ sᴇɴᴛ: {success}\n"
            f"🚫 ʙʟᴏᴄᴋᴇᴅ: {blocked}\n"
            f"❌ ғᴀɪʟᴇᴅ: {fail}",
            parse_mode="HTML",
        )
    except (BadRequest, TelegramError):
        pass
    schedule_delete(status)


# ──────── /stats (owner only) ────────
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, context):
        return
    uid = update.effective_user.id
    if not is_owner(uid):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent)
        return

    total = len(users)
    total_credits = sum(u.get("credits", 0) for u in users.values())
    total_refs = sum(len(u.get("refs", [])) for u in users.values())

    text = (
        "📊 <b>ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs</b>\n\n"
        f"👥 ᴜsᴇʀs : {total}\n"
        f"💰 ᴄʀᴇᴅɪᴛs ɪɴ ᴄɪʀᴄᴜʟᴀᴛɪᴏɴ : {total_credits}\n"
        f"🔗 ᴛᴏᴛᴀʟ ʀᴇғᴇʀʀᴀʟs : {total_refs}\n"
        f"⏳ ᴜᴘᴛɪᴍᴇ : {format_uptime()}\n"
        f"🏷 ᴀᴜᴛʜᴏʀɪᴢᴇᴅ ɢʀᴏᴜᴘ : <code>{ALLOWED_GROUP_ID or 'ɴᴏᴛ ѕᴇᴛ'}</code>\n"
        f"🚫 ʙᴀɴɴᴇᴅ : {len(banned)}"
    )
    sent = await update.message.reply_text(text, parse_mode="HTML", reply_markup=source_keyboard())
    schedule_delete(sent)


# ──────── /setgroup (owner only, run inside group) ────────
async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent)
        return

    chat = update.effective_chat
    if chat.type == "private":
        sent = await update.message.reply_text(
            f"ℹ️ ʀᴜɴ /setgroup ɪɴsɪᴅᴇ ᴛʜᴇ ɢʀᴏᴜᴘ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴀᴜᴛʜᴏʀɪᴢᴇ.\n"
            f"ɢʀᴏᴜᴘ ʟɪɴᴋ: {GROUP_LINK}",
            disable_web_page_preview=True,
        )
        schedule_delete(sent)
        return

    global ALLOWED_GROUP_ID
    ALLOWED_GROUP_ID = chat.id
    save_config()

    sent = await update.message.reply_text(
        f"✅ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ ɢʀᴏᴜᴘ sᴇᴛ ᴛᴏ <b>{chat.title}</b>\n"
        f"🆔 <code>{chat.id}</code>\n"
        "🌟 ᴀʟʟ ᴍᴇᴍʙᴇʀs ʜᴇʀᴇ ɴᴏᴡ ɢᴇᴛ ᴜɴʟɪᴍɪᴛᴇᴅ ᴜsᴀɢᴇ.",
        parse_mode="HTML",
    )
    schedule_delete(sent)


# ──────── ban / unban / banned (owner only) ────────
def _parse_target_id(update, context):
    """Get target user id from /cmd <id> or from a reply."""
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        return update.message.reply_to_message.from_user.id
    if context.args:
        try:
            return int(context.args[0])
        except (TypeError, ValueError):
            return None
    return None


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent)
        return

    target = _parse_target_id(update, context)
    if target is None:
        sent = await update.message.reply_text(
            "🚫 <b>ᴜsᴀɢᴇ:</b>\n/ban &lt;ᴜsᴇʀ_ɪᴅ&gt;\nᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴡɪᴛʜ /ban",
            parse_mode="HTML",
        )
        schedule_delete(sent)
        return
    if target == OWNER_ID:
        sent = await update.message.reply_text("🙃 ᴄᴀɴ'ᴛ ʙᴀɴ ᴛʜᴇ ᴏᴡɴᴇʀ.")
        schedule_delete(sent)
        return

    banned.add(int(target))
    save_config()
    sent = await update.message.reply_text(
        f"🚫 <b>ʙᴀɴɴᴇᴅ</b> <code>{target}</code>\nᴛʜᴇʏ ᴄᴀɴ ɴᴏ ʟᴏɴɢᴇʀ ᴜsᴇ ᴛʜᴇ ʙᴏᴛ.",
        parse_mode="HTML",
    )
    schedule_delete(sent)


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent)
        return

    target = _parse_target_id(update, context)
    if target is None:
        sent = await update.message.reply_text(
            "✅ <b>ᴜsᴀɢᴇ:</b>\n/unban &lt;ᴜsᴇʀ_ɪᴅ&gt;\nᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴡɪᴛʜ /unban",
            parse_mode="HTML",
        )
        schedule_delete(sent)
        return

    if int(target) not in banned:
        sent = await update.message.reply_text(
            f"ℹ️ <code>{target}</code> ɪs ɴᴏᴛ ʙᴀɴɴᴇᴅ.", parse_mode="HTML"
        )
        schedule_delete(sent)
        return

    banned.discard(int(target))
    save_config()
    sent = await update.message.reply_text(
        f"✅ <b>ᴜɴʙᴀɴɴᴇᴅ</b> <code>{target}</code>", parse_mode="HTML"
    )
    schedule_delete(sent)


async def banned_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent)
        return

    if not banned:
        text = "📋 <b>ʙᴀɴɴᴇᴅ ʟɪsᴛ</b>\n\nɴᴏ ᴜsᴇʀs ᴀʀᴇ ʙᴀɴɴᴇᴅ. ✨"
    else:
        rows = "\n".join(f"• <code>{u}</code>" for u in sorted(banned))
        text = f"📋 <b>ʙᴀɴɴᴇᴅ ʟɪsᴛ</b> ({len(banned)})\n\n{rows}"

    sent = await update.message.reply_text(text, parse_mode="HTML", reply_markup=source_keyboard())
    schedule_delete(sent)


# ──────── MAIN ────────
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ping", ping))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CommandHandler("id", id_cmd))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("setgroup", setgroup))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unban", unban))
app.add_handler(CommandHandler("banned", banned_list))
app.add_handler(CallbackQueryHandler(ref, pattern="^ref$"))
app.add_handler(CallbackQueryHandler(help_cb, pattern="^help$"))
app.add_handler(CallbackQueryHandler(set_mode, pattern="^(remove|upload)$"))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

if __name__ == "__main__":
    try:
        print("🚀 Bot starting...")
        app.run_polling()
    except Exception:
        import traceback
        print("❌ FULL ERROR:")
        traceback.print_exc()
