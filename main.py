import json
import asyncio
import random
import os
import time
import tempfile
import requests
import psutil
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.error import BadRequest, TelegramError, Forbidden, InvalidToken

try:
    from nudenet import NudeDetector
    _nsfw_detector = NudeDetector()
except Exception as _e:
    print(f"⚠️ NudeNet failed to load, NSFW scan disabled: {_e}")
    _nsfw_detector = None

# ──────── MAIN BOT CONSTANTS ────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8684382287:AAE17nfdgrbndBSl1wG9MWmiW9GdeErkTg4")
REMOVE_BG_API = "f3Se7SVDqpvsM5TLknPKN6Cz"
IMGBB_API = "62736b1fc27c5c6bb91063f2ec92913b"
BOT_USERNAME = "IMAGE_TO_BACKREMOVE_bot"

# 👑 SUPREME MASTER — controls every clone, sees /clonestats,
#     and broadcasts from the main bot fan out to every clone.
MASTER_OWNER_ID = 8441236350

PING_VIDEO = "https://files.catbox.moe/o57l0y.mp4"
START_VIDEO = "https://files.catbox.moe/wnw0ds.mp4"
SOURCE_PREVIEW = "https://files.catbox.moe/jizede.jpg"
GROUP_LINK = "https://t.me/+uRWDvRhCiNo0OWFl"
NETWORK_URL = "https://t.me/+Imyf3M9TO5k1ODRl"
HOME_URL = "https://t.me/+dv_rcq5uIXhmMWM1"
MASTER_LINK = "https://t.me/YOUR_MADARA_BRO"

USERS_FILE = "users.json"
CONFIG_FILE = "config.json"
CLONES_FILE = "clones.json"

AUTO_DELETE_SECONDS = 60
START_TIME = time.time()

# How-to links shared with clone owners
REMOVE_BG_HOWTO = "https://www.remove.bg/api"
IMGBB_HOWTO = "https://api.imgbb.com/"

GREET = [
    "<b>🌸 ʜᴇʟʟᴏ ᴛʜᴇʀᴇ...</b>",
    "<b>✨ ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ...</b>",
    "<b>💫 ʟᴏᴀᴅɪɴɢ ᴍᴀɢɪᴄ...</b>",
    "<b>🌹 ʜᴇʏ ᴄᴜᴛɪᴇ...</b>",
    "<b>🔮 sᴜᴍᴍᴏɴɪɴɢ ʙᴏᴛ...</b>",
]

# ──────── JSON helpers ────────
def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def write_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"⚠️ failed to write {path}: {e}")


# ──────── BotState (per-bot configuration & data) ────────
class BotState:
    def __init__(
        self,
        *,
        token,
        owner_id,
        is_main=False,
        remove_bg_api=None,
        imgbb_api=None,
        bot_username=None,
        start_text=None,
        ping_text=None,
        join_url=None,
        network_url=None,
        home_url=None,
        master_link=None,
        users=None,
        banned=None,
        allowed_group_id=None,
        uploads=0,
        removals=0,
        created_at=None,
    ):
        self.token = token
        self.owner_id = int(owner_id) if owner_id is not None else MASTER_OWNER_ID
        self.is_main = is_main
        self.remove_bg_api = remove_bg_api
        self.imgbb_api = imgbb_api
        self.bot_username = bot_username
        self.start_text = start_text
        self.ping_text = ping_text
        self.join_url = join_url or GROUP_LINK
        self.network_url = network_url or NETWORK_URL
        self.home_url = home_url or HOME_URL
        self.master_link = master_link or MASTER_LINK
        self.users = users if users is not None else {}
        self.banned = set(int(x) for x in (banned or []))
        self.allowed_group_id = allowed_group_id
        self.uploads = int(uploads or 0)
        self.removals = int(removals or 0)
        self.created_at = created_at or datetime.utcnow().isoformat()
        # Per-user transient mode (remove / upload). Not persisted.
        self.mode = {}

    @classmethod
    def from_dict(cls, token, data):
        return cls(
            token=token,
            owner_id=data.get("owner_id"),
            is_main=False,
            remove_bg_api=data.get("remove_bg_api"),
            imgbb_api=data.get("imgbb_api"),
            bot_username=data.get("bot_username"),
            start_text=data.get("start_text"),
            ping_text=data.get("ping_text"),
            join_url=data.get("join_url"),
            network_url=data.get("network_url"),
            home_url=data.get("home_url"),
            master_link=data.get("master_link"),
            users=data.get("users", {}),
            banned=data.get("banned", []),
            allowed_group_id=data.get("allowed_group_id"),
            uploads=data.get("uploads", 0),
            removals=data.get("removals", 0),
            created_at=data.get("created_at"),
        )

    def to_dict(self):
        return {
            "owner_id": self.owner_id,
            "remove_bg_api": self.remove_bg_api,
            "imgbb_api": self.imgbb_api,
            "bot_username": self.bot_username,
            "start_text": self.start_text,
            "ping_text": self.ping_text,
            "join_url": self.join_url,
            "network_url": self.network_url,
            "home_url": self.home_url,
            "master_link": self.master_link,
            "users": self.users,
            "banned": sorted(self.banned),
            "allowed_group_id": self.allowed_group_id,
            "uploads": self.uploads,
            "removals": self.removals,
            "created_at": self.created_at,
        }

    def has_apis(self) -> bool:
        return bool(self.remove_bg_api) and bool(self.imgbb_api)

    def is_owner(self, uid) -> bool:
        try:
            uid_int = int(uid)
        except (TypeError, ValueError):
            return False
        return uid_int == self.owner_id or uid_int == MASTER_OWNER_ID

    def is_banned(self, uid) -> bool:
        try:
            return int(uid) in self.banned
        except (TypeError, ValueError):
            return False

    def persist(self):
        if self.is_main:
            write_json(USERS_FILE, self.users)
            write_json(CONFIG_FILE, {
                "allowed_group_id": self.allowed_group_id,
                "banned": sorted(self.banned),
            })
        else:
            CLONES_REGISTRY[self.token] = self.to_dict()
            write_json(CLONES_FILE, CLONES_REGISTRY)


# ──────── Global registries ────────
CLONES_REGISTRY: dict = load_json(CLONES_FILE, {})
CLONE_STATES: dict = {}      # token -> BotState
CLONE_APPS: dict = {}        # token -> Application

# Build the main state
_main_users = load_json(USERS_FILE, {})
_main_cfg = load_json(CONFIG_FILE, {})
MAIN_STATE = BotState(
    token=BOT_TOKEN,
    owner_id=MASTER_OWNER_ID,
    is_main=True,
    remove_bg_api=REMOVE_BG_API,
    imgbb_api=IMGBB_API,
    bot_username=BOT_USERNAME,
    users=_main_users,
    banned=_main_cfg.get("banned", []),
    allowed_group_id=_main_cfg.get("allowed_group_id"),
)


def state_of(context: ContextTypes.DEFAULT_TYPE) -> BotState:
    s = context.application.bot_data.get("state")
    return s if s is not None else MAIN_STATE


# ──────── Gate / helpers ────────
def in_allowed_group(state: BotState, chat) -> bool:
    return (
        chat is not None
        and chat.type in ("group", "supergroup")
        and state.allowed_group_id is not None
        and chat.id == state.allowed_group_id
    )


def is_unlimited(state: BotState, uid, chat) -> bool:
    return state.is_owner(uid) or in_allowed_group(state, chat)


async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    state = state_of(context)
    user = update.effective_user
    if user is not None and state.is_banned(user.id) and not state.is_owner(user.id):
        return False
    chat = update.effective_chat
    if chat is None:
        return False
    if chat.type == "private":
        return True
    if in_allowed_group(state, chat):
        return True
    if chat.type in ("group", "supergroup", "channel"):
        try:
            await context.bot.leave_chat(chat.id)
        except (BadRequest, TelegramError):
            pass
    return False


def reset(state: BotState, uid):
    today = str(datetime.now().date())
    if state.users[uid].get("last") != today:
        state.users[uid]["credits"] = 2
        state.users[uid]["last"] = today


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


# ──────── Processing animation (0% → 100%) ────────
PROGRESS_STEPS = [
    ("🚀 ɪɴɪᴛɪᴀʟɪᴢɪɴɢ ᴇɴɢɪɴᴇ",      6),
    ("🔍 sᴄᴀɴɴɪɴɢ ᴘɪxᴇʟs",         18),
    ("🧠 ᴀɪ ᴀɴᴀʟʏᴢɪɴɢ ɪᴍᴀɢᴇ",     32),
    ("⚙️ ᴄᴏᴍᴘᴜᴛɪɴɢ ᴍᴀsᴋ",          48),
    ("✨ ᴡᴏʀᴋɪɴɢ ᴍᴀɢɪᴄ",            64),
    ("🎨 ʀᴇɴᴅᴇʀɪɴɢ ʟᴀʏᴇʀs",        78),
    ("🌟 ᴘᴏʟɪsʜɪɴɢ ʀᴇsᴜʟᴛ",         90),
    ("⚡ ғɪɴᴀʟɪᴢɪɴɢ",                97),
]
SPIN = ["◐", "◓", "◑", "◒"]


def progress_card(label: str, pct: int, spin_i: int) -> str:
    filled = pct // 10
    empty = 10 - filled
    bar = "▰" * filled + "▱" * empty
    spinner = SPIN[spin_i % len(SPIN)]
    return (
        f"╭─〘 {spinner} <b>ᴘʀᴏᴄᴇssɪɴɢ ᴍᴀɢɪᴄ</b> {spinner} 〙─╮\n"
        f"│\n"
        f"│  <code>[{bar}]</code>\n"
        f"│  <b>{pct:3d}%</b>  ·  {label}\n"
        f"│\n"
        f"╰──〘 ᴍᴀᴅᴀʀᴀ ʙɢ ᴇɴɢɪɴᴇ 〙──╯"
    )


async def progress_anim(message, stop_event: asyncio.Event):
    spin_i = 0
    i = 0
    while not stop_event.is_set() and i < len(PROGRESS_STEPS):
        label, pct = PROGRESS_STEPS[i]
        await safe_edit(message, progress_card(label, pct, spin_i))
        spin_i += 1
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=0.45)
        except asyncio.TimeoutError:
            pass
        i += 1
    while not stop_event.is_set():
        label, pct = PROGRESS_STEPS[-1]
        await safe_edit(message, progress_card(label, pct, spin_i))
        spin_i += 1
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=0.45)
        except asyncio.TimeoutError:
            pass
    await safe_edit(message, progress_card("✅ ᴄᴏᴍᴘʟᴇᴛᴇ", 100, spin_i))
    await asyncio.sleep(0.35)


async def run_with_progress(processing_msg, work_coro):
    stop = asyncio.Event()
    anim_task = asyncio.create_task(progress_anim(processing_msg, stop))
    try:
        return await work_coro
    finally:
        stop.set()
        try:
            await anim_task
        except Exception:
            pass


# ──────── NSFW scanner ────────
NSFW_LABELS = {
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "BUTTOCKS_EXPOSED",
    "ANUS_EXPOSED",
}
NSFW_THRESHOLD = 0.55
WARNING_LIMIT = 3


def _scan_image_sync(image_bytes: bytes):
    if _nsfw_detector is None:
        return False, ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        try:
            results = _nsfw_detector.detect(tmp_path) or []
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        for r in results:
            cls = r.get("class") or r.get("label") or ""
            score = r.get("score", 0)
            if cls in NSFW_LABELS and score >= NSFW_THRESHOLD:
                return True, f"{cls} ({score:.2f})"
    except Exception as e:
        print(f"⚠️ NSFW scan error: {e}")
    return False, ""


async def scan_image(image_bytes: bytes):
    return await asyncio.to_thread(_scan_image_sync, image_bytes)


# ──────── Source-code button helper ────────
def source_button() -> InlineKeyboardButton:
    return InlineKeyboardButton("👨‍💻 sᴏᴜʀᴄᴇ ᴄᴏᴅᴇ", url=SOURCE_PREVIEW)


def source_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[source_button()]])


# ──────── Owner notification ────────
async def notify_owner(context, action: str, user, chat=None, **details):
    state = state_of(context)
    if user is None or int(user.id) == state.owner_id:
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
            state.owner_id,
            "\n".join(parts),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except (BadRequest, TelegramError, Forbidden):
        pass


# ──────── Keyboards ────────
def main_keyboard_full(state: BotState) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥✨ ᴛᴀᴘ ᴛᴏ sᴇᴇ ᴍᴀɢɪᴄ ✨🔥", callback_data="remove")],
        [
            InlineKeyboardButton("🌐 ɴᴇᴛᴡᴏʀᴋ", url=state.network_url),
            InlineKeyboardButton("🏠 ᴍʏ ʜᴏᴍᴇ", url=state.home_url),
        ],
        [InlineKeyboardButton("🌟 ᴊᴏɪɴ ᴏᴜʀ ɢʀᴏᴜᴘ — ᴜɴʟɪᴍɪᴛᴇᴅ 🌟", url=state.join_url)],
        [InlineKeyboardButton("📜💡 ʜᴇʟᴘ ᴀɴᴅ ᴄᴏᴍᴍᴀɴᴅs", callback_data="help")],
        [InlineKeyboardButton("👑 ᴍʏ ᴍᴀsᴛᴇʀ 🤴", url=state.master_link)],
        [
            InlineKeyboardButton("🖼 ɪᴍᴀɢᴇ → ʟɪɴᴋ", callback_data="upload"),
            InlineKeyboardButton("🔗 ʀᴇғᴇʀʀᴀʟ", callback_data="ref"),
        ],
        [source_button()],
    ])


def clone_keyboard(state: BotState) -> InlineKeyboardMarkup:
    """Slim clone keyboard — Magic + 3 owner-customizable buttons + Help."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥✨ ᴛᴀᴘ ᴛᴏ sᴇᴇ ᴍᴀɢɪᴄ ✨🔥", callback_data="remove")],
        [InlineKeyboardButton("🌟 ᴊᴏɪɴ ɢʀᴏᴜᴘ", url=state.join_url)],
        [
            InlineKeyboardButton("🌐 ɴᴇᴛᴡᴏʀᴋ", url=state.network_url),
            InlineKeyboardButton("🏠 ʜᴏᴍᴇ", url=state.home_url),
        ],
        [InlineKeyboardButton("📜 ʜᴇʟᴘ", callback_data="help")],
    ])


def keyboard_for(state: BotState) -> InlineKeyboardMarkup:
    return main_keyboard_full(state) if state.is_main else clone_keyboard(state)


# ──────── /start ────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, context):
        return
    state = state_of(context)

    uid = str(update.effective_user.id)
    chat = update.effective_chat
    ref_arg = context.args[0] if context.args else None

    if uid not in state.users:
        state.users[uid] = {"credits": 2, "refs": []}
        if ref_arg and ref_arg != uid and ref_arg in state.users:
            if uid not in state.users[ref_arg].setdefault("refs", []):
                state.users[ref_arg]["refs"].append(uid)
                state.users[ref_arg]["credits"] = state.users[ref_arg].get("credits", 0) + 1

    reset(state, uid)
    state.persist()

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

    # Build caption (custom if owner set it, else default)
    user_first = update.effective_user.first_name or "ʙʀᴏ"
    bot_name = context.bot.first_name or "ʙᴏᴛ"

    if state.start_text:
        try:
            caption = state.start_text.format(name=user_first, bot=bot_name)
        except Exception:
            caption = state.start_text
        parse_mode = "HTML"
    else:
        caption = (
            "```\n"
            "┌────── ˹ ɪɴғᴏʀᴍᴀᴛɪᴏɴ ˼──────🔹\n"
            f"┆◍ ʜєʏ, {user_first} 🥀\n"
            f"┆◍ ɪ ᴧϻ {bot_name}\n"
            "└──────────────────────•\n\n"
            "✨ I can remove backgrounds & convert images to public links\n"
            "💰 You get 2 free credits every day\n\n"
            "🌟 JOIN OUR GROUP FOR UNLIMITED ACCESS:\n"
            f"{state.join_url}\n\n"
            "•──────────────────────•\n"
            "⌯ ᴘᴏᴡєʀєᴅ ʙʏ » |𝐌 ᴀ ᴅ ᴀ ʀ ᴀ •|\n"
            "•──────────────────────•\n"
            "```"
        )
        parse_mode = "Markdown"

    keyboard = keyboard_for(state)

    sent = None
    try:
        sent = await update.message.reply_video(
            video=START_VIDEO,
            has_spoiler=True,
            caption=caption,
            parse_mode=parse_mode,
            reply_markup=keyboard,
        )
    except (BadRequest, TelegramError):
        try:
            sent = await update.message.reply_text(
                caption, parse_mode=parse_mode, reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except (BadRequest, TelegramError):
            sent = await update.message.reply_text(
                caption, reply_markup=keyboard, disable_web_page_preview=True,
            )

    schedule_delete(sent)


# ──────── /referral callback ────────
async def ref(update, context):
    if not await gate(update, context):
        return
    state = state_of(context)
    q = update.callback_query
    uid = str(q.from_user.id)
    bot_uname = state.bot_username or context.bot.username or BOT_USERNAME
    link = f"https://t.me/{bot_uname}?start={uid}"
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


# ──────── help ────────
def help_text(state: BotState) -> str:
    base = (
        "📜 <b>ʜᴇʟᴘ &amp; ᴄᴏᴍᴍᴀɴᴅs</b>\n\n"
        "🔥 /start — sʜᴏᴡ ᴍᴀɪɴ ᴍᴇɴᴜ\n"
        "🏓 /ping — ᴄʜᴇᴄᴋ ʟᴀᴛᴇɴᴄʏ &amp; sʏsᴛᴇᴍ sᴛᴀᴛs\n"
        "🆔 /id — ʏᴏᴜʀ ᴛᴇʟᴇɢʀᴀᴍ ɪᴅ\n"
        "🧠 ʀᴇᴍᴏᴠᴇ ʙɢ — ᴛᴀᴘ ᴛʜᴇ ᴍᴀɢɪᴄ ʙᴜᴛᴛᴏɴ &amp; sᴇɴᴅ ᴀ ᴘʜᴏᴛᴏ\n"
        "🖼 ɪᴍᴀɢᴇ → ʟɪɴᴋ — ɢᴇᴛ ᴀ sʜᴀʀᴇᴀʙʟᴇ ᴜʀʟ\n"
        "🔗 ʀᴇғᴇʀʀᴀʟ — sʜᴀʀᴇ ʏᴏᴜʀ ʟɪɴᴋ ᴀɴᴅ ᴇᴀʀɴ ᴄʀᴇᴅɪᴛs\n"
        "💰 ᴄʀᴇᴅɪᴛs — 2 ғʀᴇᴇ ᴘᴇʀ ᴅᴀʏ + 1 ᴘᴇʀ ʀᴇғᴇʀʀᴀʟ\n"
        f"🌟 <a href=\"{state.join_url}\">ᴊᴏɪɴ ᴏᴜʀ ɢʀᴏᴜᴘ</a> — ᴜɴʟɪᴍɪᴛᴇᴅ ᴜsᴀɢᴇ ɪɴsɪᴅᴇ\n\n"
    )
    if state.is_main:
        owner = (
            "👑 <b>ᴏᴡɴᴇʀ ᴄᴏᴍᴍᴀɴᴅs</b>\n"
            "📢 /broadcast &lt;ᴍsɢ&gt; — sᴇɴᴅ ᴛᴏ ᴀʟʟ ᴜsᴇʀs (ᴍᴀsᴛᴇʀ ᴀʟsᴏ ʜɪᴛs ᴄʟᴏɴᴇs)\n"
            "📊 /stats — ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs\n"
            "🌐 /clonestats — ɴᴇᴛᴡᴏʀᴋ-ᴡɪᴅᴇ ᴄʟᴏɴᴇ sᴛᴀᴛs (ᴍᴀsᴛᴇʀ)\n"
            "🤖 /clones — ʟɪsᴛ ᴀʟʟ ᴄʟᴏɴᴇs (ᴍᴀsᴛᴇʀ)\n"
            "🧬 /clone &lt;ᴛᴏᴋᴇɴ&gt; — ᴄʟᴏɴᴇ ᴛʜɪs ʙᴏᴛ ᴡɪᴛʜ ʏᴏᴜʀ ᴏᴡɴ ᴛᴏᴋᴇɴ\n"
            "🔧 /setgroup — ᴀᴜᴛʜᴏʀɪᴢᴇ ᴄᴜʀʀᴇɴᴛ ɢʀᴏᴜᴘ\n"
            "🚫 /ban &lt;ɪᴅ&gt; — ʙᴀɴ ᴜsᴇʀ\n"
            "✅ /unban &lt;ɪᴅ&gt; — ʟɪғᴛ ʙᴀɴ\n"
            "📋 /banned — sᴇᴇ ʙᴀɴɴᴇᴅ ʟɪsᴛ\n"
            "⚠️ /warnings — sᴇᴇ ɴsғᴡ sᴛʀɪᴋᴇs\n"
            "♻️ /resetwarn &lt;ɪᴅ&gt; — ᴄʟᴇᴀʀ sᴛʀɪᴋᴇs\n\n"
        )
    else:
        owner = (
            "👑 <b>ᴄʟᴏɴᴇ ᴏᴡɴᴇʀ ᴄᴏᴍᴍᴀɴᴅs</b>\n"
            "🔑 /setapi &lt;ʀᴇᴍᴏᴠᴇʙɢ&gt; &lt;ɪᴍɢʙʙ&gt; — ᴀᴅᴅ ʏᴏᴜʀ ᴀᴘɪ ᴋᴇʏs\n"
            "📝 /setstart &lt;ᴛᴇxᴛ&gt; — ᴄᴜsᴛᴏᴍ sᴛᴀʀᴛ ᴄᴀᴘᴛɪᴏɴ ({name}, {bot} ᴀᴄᴄᴇᴘᴛᴇᴅ)\n"
            "🏓 /setping &lt;ᴛᴇxᴛ&gt; — ᴄᴜsᴛᴏᴍ ᴘɪɴɢ ᴄᴀᴘᴛɪᴏɴ\n"
            "🎛 /setbuttons &lt;ᴊᴏɪɴ&gt; | &lt;ɴᴇᴛᴡᴏʀᴋ&gt; | &lt;ʜᴏᴍᴇ&gt;\n"
            "👑 /setowner &lt;ɪᴅ&gt; — ᴄʜᴀɴɢᴇ ᴍᴀsᴛᴇʀ ᴜsᴇʀ\n"
            "📢 /broadcast &lt;ᴍsɢ&gt; — sᴇɴᴅ ᴛᴏ ʏᴏᴜʀ ᴄʟᴏɴᴇ ᴜsᴇʀs\n"
            "📊 /stats — ʏᴏᴜʀ ᴄʟᴏɴᴇ sᴛᴀᴛɪsᴛɪᴄs\n"
            "🚫 /ban /unban /banned — ᴍᴏᴅᴇʀᴀᴛɪᴏɴ\n\n"
        )
    return base + owner + (
        "🛡 <i>ᴀʟʟ ᴜᴘʟᴏᴀᴅs ᴀʀᴇ sᴄᴀɴɴᴇᴅ ғᴏʀ ɴsғᴡ ᴄᴏɴᴛᴇɴᴛ. 3 sᴛʀɪᴋᴇs = ᴀᴜᴛᴏ-ʙᴀɴ.</i>\n"
        "⏳ <i>ᴀʟʟ ʙᴏᴛ ᴍᴇssᴀɢᴇs ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇ ᴀғᴛᴇʀ 1 ᴍɪɴᴜᴛᴇ.</i>"
    )


async def help_cb(update, context):
    if not await gate(update, context):
        return
    state = state_of(context)
    q = update.callback_query
    await q.answer()
    await notify_owner(context, "ᴏᴘᴇɴᴇᴅ ʜᴇʟᴘ", q.from_user, update.effective_chat)
    sent = await q.message.reply_text(
        help_text(state),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=source_keyboard(),
    )
    schedule_delete(sent)


async def help_cmd(update, context):
    if not await gate(update, context):
        return
    state = state_of(context)
    await notify_owner(context, "ᴏᴘᴇɴᴇᴅ /ʜᴇʟᴘ", update.effective_user, update.effective_chat)
    sent = await update.message.reply_text(
        help_text(state),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=source_keyboard(),
    )
    schedule_delete(sent)


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
    state = state_of(context)
    q = update.callback_query
    uid = str(q.from_user.id)

    if q.data == "remove":
        state.mode[uid] = "remove"
        await q.answer()
        await notify_owner(context, "ᴄʜᴏsᴇ: ʀᴇᴍᴏᴠᴇ ʙɢ", q.from_user, update.effective_chat)
        sent = await q.message.reply_text(
            "🧠✨ sᴇɴᴅ ᴀɴ ɪᴍᴀɢᴇ ᴛᴏ ʀᴇᴍᴏᴠᴇ ɪᴛs ʙᴀᴄᴋɢʀᴏᴜɴᴅ",
            reply_markup=source_keyboard(),
        )
        schedule_delete(sent)

    elif q.data == "upload":
        state.mode[uid] = "upload"
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
    state = state_of(context)

    uid = str(update.effective_user.id)
    chat = update.effective_chat
    unlimited = is_unlimited(state, uid, chat)

    if uid not in state.users:
        state.users[uid] = {"credits": 2, "refs": []}
    reset(state, uid)

    # Clone API-key gate
    if not state.has_apis():
        msg = (
            "⚙️ <b>ᴛʜɪs ʙᴏᴛ ɪs ɴᴏᴛ ʏᴇᴛ ᴄᴏɴғɪɢᴜʀᴇᴅ</b>\n\n"
            "ᴛʜᴇ ᴏᴡɴᴇʀ ᴍᴜsᴛ ᴀᴅᴅ ᴀᴘɪ ᴋᴇʏs ʙᴇғᴏʀᴇ ᴛʜᴇ ʙᴏᴛ ᴄᴀɴ ᴘʀᴏᴄᴇss ɪᴍᴀɢᴇs.\n\n"
            "<b>ʜᴏᴡ ᴛᴏ ɢᴇᴛ ᴋᴇʏs:</b>\n"
            f"• ʀᴇᴍᴏᴠᴇ.ʙɢ → {REMOVE_BG_HOWTO}\n"
            f"• ɪᴍɢʙʙ → {IMGBB_HOWTO}\n\n"
            "<b>ᴛʜᴇɴ ᴏᴡɴᴇʀ ᴄᴀɴ ʀᴜɴ:</b>\n"
            "<code>/setapi REMOVEBG_KEY IMGBB_KEY</code>"
        )
        sent = await update.message.reply_text(
            msg, parse_mode="HTML", disable_web_page_preview=True,
            reply_markup=source_keyboard(),
        )
        schedule_delete(sent, 120)
        if not state.is_main:
            try:
                await context.bot.send_message(
                    state.owner_id,
                    "⚙️ ᴀ ᴜsᴇʀ ᴊᴜsᴛ ᴛʀɪᴇᴅ ᴛᴏ ᴜsᴇ ʏᴏᴜʀ ᴄʟᴏɴᴇ — ᴀᴅᴅ ᴀᴘɪ ᴋᴇʏs ᴛᴏ ᴜɴʟᴏᴄᴋ ɪᴛ:\n\n"
                    + msg,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception:
                pass
        return

    if not unlimited and state.users[uid].get("credits", 0) <= 0:
        sent = await update.message.reply_text(
            "❌ ɴᴏ ᴄʀᴇᴅɪᴛs ʟᴇғᴛ! ᴛʀʏ ᴀɢᴀɪɴ ᴛᴏᴍᴏʀʀᴏᴡ 🥀",
            reply_markup=source_keyboard(),
        )
        schedule_delete(sent)
        return

    file = await update.message.photo[-1].get_file()
    img_url = file.file_path

    user_mode = state.mode.get(uid, "remove")
    await notify_owner(
        context, f"ᴜsᴇᴅ: {user_mode.upper()}",
        update.effective_user, chat,
        ᴜɴʟɪᴍɪᴛᴇᴅ=("ʏᴇs" if unlimited else "ɴᴏ"),
    )

    processing = await update.message.reply_text(
        progress_card("🚀 ɪɴɪᴛɪᴀʟɪᴢɪɴɢ ᴇɴɢɪɴᴇ", 0, 0),
        parse_mode="HTML",
    )

    # ─── NSFW safety scan ───
    if not state.is_owner(uid):
        try:
            await safe_edit(processing, progress_card("🛡 sᴀғᴇᴛʏ sᴄᴀɴ", 10, 0))
            img_bytes_for_scan = await asyncio.to_thread(
                lambda: requests.get(img_url, timeout=30).content
            )
            unsafe, reason = await scan_image(img_bytes_for_scan)
        except Exception:
            unsafe, reason = False, ""

        if unsafe:
            state.users[uid]["warnings"] = state.users[uid].get("warnings", 0) + 1
            warns = state.users[uid]["warnings"]
            state.persist()

            try:
                await processing.delete()
            except Exception:
                pass

            await notify_owner(
                context,
                f"🚨 ᴜɴsᴀғᴇ ɪᴍᴀɢᴇ ᴅᴇᴛᴇᴄᴛᴇᴅ (sᴛʀɪᴋᴇ {warns}/{WARNING_LIMIT})",
                update.effective_user, chat,
                ʀᴇᴀsᴏɴ=reason or "ɴsғᴡ",
            )

            if warns >= WARNING_LIMIT:
                state.banned.add(int(uid))
                state.persist()
                msg = (
                    "⛔ <b>ʏᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ ʙᴀɴɴᴇᴅ</b>\n\n"
                    f"🚨 sᴛʀɪᴋᴇ <b>{warns}/{WARNING_LIMIT}</b> — ʀᴇᴘᴇᴀᴛᴇᴅ ɴsғᴡ ᴄᴏɴᴛᴇɴᴛ.\n"
                    "ʏᴏᴜ ᴄᴀɴ ɴᴏ ʟᴏɴɢᴇʀ ᴜsᴇ ᴛʜɪs ʙᴏᴛ.\n\n"
                    "ɪғ ʏᴏᴜ ʙᴇʟɪᴇᴠᴇ ᴛʜɪs ɪs ᴀ ᴍɪsᴛᴀᴋᴇ, ᴄᴏɴᴛᴀᴄᴛ ᴛʜᴇ ᴏᴡɴᴇʀ."
                )
            elif warns == 1:
                msg = (
                    "⚠️ <b>ᴡᴀʀɴɪɴɢ 1 ᴏғ 3</b>\n\n"
                    "🚫 ʏᴏᴜʀ ɪᴍᴀɢᴇ ᴡᴀs ғʟᴀɢɢᴇᴅ ᴀs <b>ɴsғᴡ / ᴜɴsᴀғᴇ</b> ᴀɴᴅ ᴡᴀs ʀᴇᴊᴇᴄᴛᴇᴅ.\n\n"
                    "ᴘʟᴇᴀsᴇ ᴅᴏ ɴᴏᴛ sᴇɴᴅ ᴘᴏʀɴᴏɢʀᴀᴘʜɪᴄ, ᴅʀᴜɢ-ʀᴇʟᴀᴛᴇᴅ, ᴏʀ ᴀɴʏ ᴜɴsᴀғᴇ ᴄᴏɴᴛᴇɴᴛ.\n"
                    "ʀᴇᴘᴇᴀᴛ ᴏғғᴇɴᴄᴇs ᴡɪʟʟ ʀᴇsᴜʟᴛ ɪɴ ᴀ ᴘᴇʀᴍᴀɴᴇɴᴛ ʙᴀɴ."
                )
            else:
                msg = (
                    "⚠️ <b>ғɪɴᴀʟ ᴡᴀʀɴɪɴɢ — 2 ᴏғ 3</b>\n\n"
                    "🚫 ʏᴏᴜʀ ɪᴍᴀɢᴇ ᴡᴀs ғʟᴀɢɢᴇᴅ ᴀs <b>ɴsғᴡ / ᴜɴsᴀғᴇ</b> ᴀɢᴀɪɴ.\n\n"
                    "<b>ᴏɴᴇ ᴍᴏʀᴇ ᴏғғᴇɴᴄᴇ ᴀɴᴅ ʏᴏᴜ ᴡɪʟʟ ʙᴇ ʙᴀɴɴᴇᴅ ғʀᴏᴍ ᴛʜᴇ ʙᴏᴛ.</b>"
                )

            sent = await update.message.reply_text(msg, parse_mode="HTML", reply_markup=source_keyboard())
            schedule_delete(sent)
            return
