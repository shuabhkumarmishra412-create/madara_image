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


    # UPLOAD MODE
    if user_mode == "upload":
        if not unlimited:
            state.users[uid]["credits"] -= 1
            state.persist()

        async def upload_work():
            img_bytes = await asyncio.to_thread(
                lambda: requests.get(img_url, timeout=30).content
            )
            res = await asyncio.to_thread(
                lambda: requests.post(
                    "https://api.imgbb.com/1/upload",
                    params={"key": state.imgbb_api},
                    files={"image": img_bytes},
                    timeout=30,
                )
            )
            return res.json()

        try:
            data = await run_with_progress(processing, upload_work())
        except Exception:
            try:
                await processing.delete()
            except Exception:
                pass
            sent = await update.message.reply_text("❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ", reply_markup=source_keyboard())
            schedule_delete(sent)
            return

        try:
            await processing.delete()
        except Exception:
            pass

        if not data.get("success"):
            sent = await update.message.reply_text("❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ", reply_markup=source_keyboard())
            schedule_delete(sent)
            return

        state.uploads += 1
        state.persist()

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
        state.users[uid]["credits"] -= 1
        state.persist()

    async def remove_work():
        return await asyncio.to_thread(
            lambda: requests.post(
                "https://api.remove.bg/v1.0/removebg",
                data={"image_url": img_url},
                headers={"X-Api-Key": state.remove_bg_api},
                timeout=60,
            )
        )

    try:
        res = await run_with_progress(processing, remove_work())
    except Exception:
        try:
            await processing.delete()
        except Exception:
            pass
        sent = await update.message.reply_text("❌ ʙɢ ʀᴇᴍᴏᴠᴇ ғᴀɪʟᴇᴅ", reply_markup=source_keyboard())
        schedule_delete(sent)
        return

    try:
        await processing.delete()
    except Exception:
        pass

    if res.status_code != 200:
        sent = await update.message.reply_text("❌ ʙɢ ʀᴇᴍᴏᴠᴇ ғᴀɪʟᴇᴅ", reply_markup=source_keyboard())
        schedule_delete(sent)
        return

    state.removals += 1
    state.persist()

    sent = await update.message.reply_photo(
        res.content,
        has_spoiler=True,
        caption="✨ <b>ʏᴏᴜʀ ʙᴀᴄᴋɢʀᴏᴜɴᴅ-ʀᴇᴍᴏᴠᴇᴅ ɪᴍᴀɢᴇ</b> 🥀\n<i>ᴛᴀᴘ ᴛᴏ ʀᴇᴠᴇᴀʟ</i>",
        parse_mode="HTML",
        reply_markup=source_keyboard(),
    )
    schedule_delete(sent)


# ──────── /ping ────────
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, context):
        return
    state = state_of(context)
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

    if state.ping_text:
        try:
            caption = state.ping_text.format(
                ping=f"{ping_ms:.3f}",
                uptime=format_uptime(),
                ram=ram, cpu=cpu, disk=disk,
                bot=context.bot.first_name or "ʙᴏᴛ",
            )
        except Exception:
            caption = state.ping_text
    else:
        caption = (
            "<b>sᴛᴧʀᴛed!</b>\n\n"
            f"🏓 <b>ᴘɪɴɢ..ᴩᴏɴɢ</b> : {ping_ms:.3f}\n"
            "🌺 <b>sʏsᴛᴇᴍ sᴛᴀᴛs</b> :\n\n"
            f":⧽ ᴜᴩᴛɪᴍᴇ : {format_uptime()}\n"
            f":⧽ ʀᴀᴍ : {ram}%\n"
            f":⧽ ᴄᴩᴜ : {cpu}%\n"
            f":⧽ ᴅɪsᴋ : {disk}%\n"
            f":⧽ ᴩʏ-ᴛɢᴄᴀʟʟs : 0.436ᴍs\n"
            f':⧽ ʙʏ » <a href="{state.master_link}">|𝐌 ᴀ ᴅ ᴀ ʀ ᴀ •|</a>'
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
        try:
            sent = await update.message.reply_text(
                caption, parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=source_keyboard(),
            )
        except (BadRequest, TelegramError):
            sent = await update.message.reply_text(
                caption, disable_web_page_preview=True, reply_markup=source_keyboard(),
            )

    schedule_delete(sent)


# ──────── /broadcast ────────
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, context):
        return
    state = state_of(context)
    uid = update.effective_user.id
    if not state.is_owner(uid):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent)
        return

    targets = list(state.users.keys())
    reply = update.message.reply_to_message
    text_arg = (update.message.text or "").partition(" ")[2].strip()

    if reply is None and not text_arg:
        sent = await update.message.reply_text(
            "📢 <b>ᴜsᴀɢᴇ:</b>\n"
            "/broadcast &lt;ᴍᴇssᴀɢᴇ&gt;\n"
            "ᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴡɪᴛʜ /broadcast",
            parse_mode="HTML",
        )
        schedule_delete(sent)
        return

    if not targets and not (state.is_main and int(uid) == MASTER_OWNER_ID and CLONE_APPS):
        sent = await update.message.reply_text("📭 ɴᴏ ᴜsᴇʀs ᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ᴛᴏ.")
        schedule_delete(sent)
        return

    status = await update.message.reply_text(
        f"📢 <b>ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ ᴛᴏ {len(targets)} ᴜsᴇʀs...</b>",
        parse_mode="HTML",
    )

    success, fail, blocked = 0, 0, 0
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
                await context.bot.send_message(chat_id=target_int, text=text_arg)
            success += 1
        except Forbidden:
            blocked += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)

    # Cross-broadcast: the SUPREME MASTER on the MAIN bot fans the message
    # out to every clone's user base (text-only cross-bot for safety).
    clone_total = 0
    clone_sent = 0
    clone_count = 0
    if state.is_main and int(uid) == MASTER_OWNER_ID and CLONE_APPS:
        cross_text = text_arg
        if not cross_text and reply is not None:
            cross_text = reply.text or reply.caption or ""
        if cross_text:
            for tk, capp in list(CLONE_APPS.items()):
                cs = CLONE_STATES.get(tk)
                if not cs:
                    continue
                clone_count += 1
                for cuid in list(cs.users.keys()):
                    clone_total += 1
                    try:
                        await capp.bot.send_message(int(cuid), cross_text)
                        clone_sent += 1
                    except Exception:
                        pass
                    await asyncio.sleep(0.04)

    summary = (
        "📢 <b>ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇ</b>\n"
        f"✅ sᴇɴᴛ: {success}\n"
        f"🚫 ʙʟᴏᴄᴋᴇᴅ: {blocked}\n"
        f"❌ ғᴀɪʟᴇᴅ: {fail}"
    )
    if clone_count:
        summary += (
            f"\n\n🌐 <b>ᴄʟᴏɴᴇ ɴᴇᴛᴡᴏʀᴋ</b>\n"
            f"🤖 ᴄʟᴏɴᴇs ʀᴇᴀᴄʜᴇᴅ: {clone_count}\n"
            f"✅ ᴜsᴇʀs sᴇɴᴛ: {clone_sent}/{clone_total}"
        )

    try:
        await status.edit_text(summary, parse_mode="HTML")
    except (BadRequest, TelegramError):
        pass
    schedule_delete(status)


# ──────── /stats ────────
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, context):
        return
    state = state_of(context)
    uid = update.effective_user.id
    if not state.is_owner(uid):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent)
        return

    total = len(state.users)
    total_credits = sum(u.get("credits", 0) for u in state.users.values())
    total_refs = sum(len(u.get("refs", [])) for u in state.users.values())

    text = (
        f"📊 <b>{'ᴍᴀɪɴ' if state.is_main else 'ᴄʟᴏɴᴇ'} sᴛᴀᴛɪsᴛɪᴄs</b>\n\n"
        f"🤖 ʙᴏᴛ : @{state.bot_username or '—'}\n"
        f"👥 ᴜsᴇʀs : {total}\n"
        f"💰 ᴄʀᴇᴅɪᴛs ɪɴ ᴄɪʀᴄᴜʟᴀᴛɪᴏɴ : {total_credits}\n"
        f"🔗 ᴛᴏᴛᴀʟ ʀᴇғᴇʀʀᴀʟs : {total_refs}\n"
        f"🧠 ʙɢ ʀᴇᴍᴏᴠᴀʟs : {state.removals}\n"
        f"📤 ɪᴍᴀɢᴇ ᴜᴘʟᴏᴀᴅs : {state.uploads}\n"
        f"⏳ ᴜᴘᴛɪᴍᴇ : {format_uptime()}\n"
        f"🏷 ᴀᴜᴛʜᴏʀɪᴢᴇᴅ ɢʀᴏᴜᴘ : <code>{state.allowed_group_id or 'ɴᴏᴛ ѕᴇᴛ'}</code>\n"
        f"🚫 ʙᴀɴɴᴇᴅ : {len(state.banned)}"
    )
    if state.is_main:
        text += f"\n🌐 ᴄʟᴏɴᴇs ᴀᴄᴛɪᴠᴇ : {len(CLONE_APPS)}"
    sent = await update.message.reply_text(text, parse_mode="HTML", reply_markup=source_keyboard())
    schedule_delete(sent)


# ──────── /setgroup ────────
async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = state_of(context)
    uid = update.effective_user.id
    if not state.is_owner(uid):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent)
        return

    chat = update.effective_chat
    if chat.type == "private":
        sent = await update.message.reply_text(
            f"ℹ️ ʀᴜɴ /setgroup ɪɴsɪᴅᴇ ᴛʜᴇ ɢʀᴏᴜᴘ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴀᴜᴛʜᴏʀɪᴢᴇ.\n"
            f"ɢʀᴏᴜᴘ ʟɪɴᴋ: {state.join_url}",
            disable_web_page_preview=True,
        )
        schedule_delete(sent)
        return

    state.allowed_group_id = chat.id
    state.persist()

    sent = await update.message.reply_text(
        f"✅ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ ɢʀᴏᴜᴘ sᴇᴛ ᴛᴏ <b>{chat.title}</b>\n"
        f"🆔 <code>{chat.id}</code>\n"
        "🌟 ᴀʟʟ ᴍᴇᴍʙᴇʀs ʜᴇʀᴇ ɴᴏᴡ ɢᴇᴛ ᴜɴʟɪᴍɪᴛᴇᴅ ᴜsᴀɢᴇ.",
        parse_mode="HTML",
    )
    schedule_delete(sent)


# ──────── ban / unban / banned / warnings / resetwarn ────────
def _parse_target_id(update, context):
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        return update.message.reply_to_message.from_user.id
    if context.args:
        try:
            return int(context.args[0])
        except (TypeError, ValueError):
            return None
    return None


async def ban(update, context):
    state = state_of(context)
    if not state.is_owner(update.effective_user.id):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent); return

    target = _parse_target_id(update, context)
    if target is None:
        sent = await update.message.reply_text(
            "🚫 <b>ᴜsᴀɢᴇ:</b>\n/ban &lt;ᴜsᴇʀ_ɪᴅ&gt;\nᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴡɪᴛʜ /ban",
            parse_mode="HTML",
        )
        schedule_delete(sent); return
    if int(target) == state.owner_id or int(target) == MASTER_OWNER_ID:
        sent = await update.message.reply_text("🙃 ᴄᴀɴ'ᴛ ʙᴀɴ ᴛʜᴇ ᴏᴡɴᴇʀ.")
        schedule_delete(sent); return

    state.banned.add(int(target))
    state.persist()
    sent = await update.message.reply_text(
        f"🚫 <b>ʙᴀɴɴᴇᴅ</b> <code>{target}</code>\nᴛʜᴇʏ ᴄᴀɴ ɴᴏ ʟᴏɴɢᴇʀ ᴜsᴇ ᴛʜᴇ ʙᴏᴛ.",
        parse_mode="HTML",
    )
    schedule_delete(sent)


async def unban(update, context):
    state = state_of(context)
    if not state.is_owner(update.effective_user.id):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent); return

    target = _parse_target_id(update, context)
    if target is None:
        sent = await update.message.reply_text(
            "✅ <b>ᴜsᴀɢᴇ:</b>\n/unban &lt;ᴜsᴇʀ_ɪᴅ&gt;\nᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴡɪᴛʜ /unban",
            parse_mode="HTML",
        )
        schedule_delete(sent); return

    if int(target) not in state.banned:
        sent = await update.message.reply_text(
            f"ℹ️ <code>{target}</code> ɪs ɴᴏᴛ ʙᴀɴɴᴇᴅ.", parse_mode="HTML"
        )
        schedule_delete(sent); return

    state.banned.discard(int(target))
    state.persist()
    sent = await update.message.reply_text(
        f"✅ <b>ᴜɴʙᴀɴɴᴇᴅ</b> <code>{target}</code>", parse_mode="HTML"
    )
    schedule_delete(sent)


async def warnings_cmd(update, context):
    state = state_of(context)
    if not state.is_owner(update.effective_user.id):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent); return

    rows = []
    for u, info in state.users.items():
        w = info.get("warnings", 0)
        if w > 0:
            rows.append(f"• <code>{u}</code> — <b>{w}/{WARNING_LIMIT}</b>")
    if not rows:
        text = "📋 <b>ᴡᴀʀɴɪɴɢs ʟɪsᴛ</b>\n\nɴᴏ ᴜsᴇʀs ʜᴀᴠᴇ ᴡᴀʀɴɪɴɢs. ✨"
    else:
        text = f"📋 <b>ᴡᴀʀɴɪɴɢs ʟɪsᴛ</b> ({len(rows)})\n\n" + "\n".join(rows)
    sent = await update.message.reply_text(text, parse_mode="HTML", reply_markup=source_keyboard())
    schedule_delete(sent)


async def resetwarn_cmd(update, context):
    state = state_of(context)
    if not state.is_owner(update.effective_user.id):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent); return

    target = _parse_target_id(update, context)
    if target is None:
        sent = await update.message.reply_text(
            "♻️ <b>ᴜsᴀɢᴇ:</b>\n/resetwarn &lt;ᴜsᴇʀ_ɪᴅ&gt;\nᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴡɪᴛʜ /resetwarn",
            parse_mode="HTML",
        )
        schedule_delete(sent); return

    uid_str = str(int(target))
    if uid_str in state.users:
        state.users[uid_str]["warnings"] = 0
        state.persist()
    sent = await update.message.reply_text(
        f"♻️ <b>ʀᴇsᴇᴛ ᴡᴀʀɴɪɴɢs</b> ғᴏʀ <code>{target}</code>",
        parse_mode="HTML",
    )
    schedule_delete(sent)


async def banned_list(update, context):
    state = state_of(context)
    if not state.is_owner(update.effective_user.id):
        sent = await update.message.reply_text("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.</b>", parse_mode="HTML")
        schedule_delete(sent); return

    if not state.banned:
        text = "📋 <b>ʙᴀɴɴᴇᴅ ʟɪsᴛ</b>\n\nɴᴏ ᴜsᴇʀs ᴀʀᴇ ʙᴀɴɴᴇᴅ. ✨"
    else:
        rows = "\n".join(f"• <code>{u}</code>" for u in sorted(state.banned))
        text = f"📋 <b>ʙᴀɴɴᴇᴅ ʟɪsᴛ</b> ({len(state.banned)})\n\n{rows}"

    sent = await update.message.reply_text(text, parse_mode="HTML", reply_markup=source_keyboard())
    schedule_delete(sent)


# ════════════════════════════════════════════════════════════════════
#                          CLONE FEATURE
# ════════════════════════════════════════════════════════════════════

async def _start_clone(state: BotState) -> Application:
    """Build, initialize, start, and start polling for a clone bot."""
    capp = build_application(state)
    await capp.initialize()
    await capp.start()
    await capp.updater.start_polling(drop_pending_updates=True)
    CLONE_APPS[state.token] = capp
    CLONE_STATES[state.token] = state
    return capp


async def _stop_clone(token: str):
    capp = CLONE_APPS.pop(token, None)
    CLONE_STATES.pop(token, None)
    if capp is not None:
        try:
            await capp.updater.stop()
        except Exception:
            pass
        try:
            await capp.stop()
        except Exception:
            pass
        try:
            await capp.shutdown()
        except Exception:
            pass


# ──────── /clone (main bot only) ────────
async def clone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, context):
        return
    state = state_of(context)
    if not state.is_main:
        sent = await update.message.reply_text(
            "⛔ ᴄʟᴏɴɪɴɢ ɪs ᴀᴠᴀɪʟᴀʙʟᴇ ᴏɴʟʏ ғʀᴏᴍ ᴛʜᴇ ᴍᴀɪɴ ʙᴏᴛ."
        )
        schedule_delete(sent)
        return

    if not context.args:
        sent = await update.message.reply_text(
            "🧬 <b>ᴄʟᴏɴᴇ ᴛʜɪs ʙᴏᴛ</b>\n\n"
            "<b>ᴜsᴀɢᴇ:</b> <code>/clone &lt;ʙᴏᴛ_ᴛᴏᴋᴇɴ&gt;</code>\n\n"
            "1️⃣ ɢᴇᴛ ᴀ ᴛᴏᴋᴇɴ ғʀᴏᴍ @BotFather\n"
            "2️⃣ sᴇɴᴅ <code>/clone &lt;ʏᴏᴜʀ_ᴛᴏᴋᴇɴ&gt;</code> ʜᴇʀᴇ\n"
            "3️⃣ ʏᴏᴜʀ ɴᴇᴡ ᴄʟᴏɴᴇ ɢᴏᴇs ʟɪᴠᴇ ɪɴsᴛᴀɴᴛʟʏ\n"
            "4️⃣ ᴏᴘᴇɴ ʏᴏᴜʀ ᴄʟᴏɴᴇ ᴀɴᴅ sᴇɴᴅ <code>/setapi REMOVEBG_KEY IMGBB_KEY</code>\n\n"
            "<b>ɢᴇᴛ ᴀᴘɪ ᴋᴇʏs:</b>\n"
            f"• ʀᴇᴍᴏᴠᴇ.ʙɢ → {REMOVE_BG_HOWTO}\n"
            f"• ɪᴍɢʙʙ → {IMGBB_HOWTO}",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        schedule_delete(sent, 180)
        return

    token = context.args[0].strip()

    if token in CLONE_APPS or token == BOT_TOKEN:
        sent = await update.message.reply_text("⚠️ ᴛʜɪs ᴛᴏᴋᴇɴ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ.")
        schedule_delete(sent)
        return

    # Validate token
    pending = await update.message.reply_text("🔍 ᴠᴀʟɪᴅᴀᴛɪɴɢ ᴛᴏᴋᴇɴ...")
    try:
        tmp_bot = Bot(token=token)
        me = await tmp_bot.get_me()
    except (InvalidToken, TelegramError) as e:
        try:
            await pending.edit_text(f"❌ ɪɴᴠᴀʟɪᴅ ᴛᴏᴋᴇɴ:\n<code>{e}</code>", parse_mode="HTML")
        except Exception:
            pass
        schedule_delete(pending)
        return

    cs = BotState(
        token=token,
        owner_id=update.effective_user.id,
        is_main=False,
        bot_username=me.username,
    )

    try:
        await _start_clone(cs)
    except Exception as e:
        try:
            await pending.edit_text(f"❌ ғᴀɪʟᴇᴅ ᴛᴏ sᴛᴀʀᴛ ᴄʟᴏɴᴇ:\n<code>{e}</code>", parse_mode="HTML")
        except Exception:
            pass
        schedule_delete(pending)
        return

    cs.persist()

    msg = (
        f"✅ <b>ᴄʟᴏɴᴇ ɪs ʟɪᴠᴇ!</b> @{me.username}\n\n"
        "ɴᴏᴡ ᴏᴘᴇɴ ʏᴏᴜʀ ᴄʟᴏɴᴇ ᴀɴᴅ sᴇɴᴅ:\n"
        "<code>/setapi REMOVEBG_KEY IMGBB_KEY</code>\n\n"
        "<b>ɢᴇᴛ ᴀᴘɪ ᴋᴇʏs ʜᴇʀᴇ:</b>\n"
        f"• ʀᴇᴍᴏᴠᴇ.ʙɢ → {REMOVE_BG_HOWTO}\n"
        f"• ɪᴍɢʙʙ → {IMGBB_HOWTO}\n\n"
        "<b>ᴄᴜsᴛᴏᴍɪᴢᴇ ʏᴏᴜʀ ᴄʟᴏɴᴇ:</b>\n"
        "• <code>/setstart &lt;text&gt;</code> — ᴄᴜsᴛᴏᴍ sᴛᴀʀᴛ ᴄᴀᴘᴛɪᴏɴ\n"
        "• <code>/setping &lt;text&gt;</code> — ᴄᴜsᴛᴏᴍ ᴘɪɴɢ ᴄᴀᴘᴛɪᴏɴ\n"
        "• <code>/setbuttons &lt;join&gt; | &lt;network&gt; | &lt;home&gt;</code>\n"
        "• <code>/setowner &lt;user_id&gt;</code> — ᴛʀᴀɴsғᴇʀ ᴏᴡɴᴇʀsʜɪᴘ\n\n"
        "⚠️ <i>ᴜɴᴛɪʟ ᴀᴘɪ ᴋᴇʏs ᴀʀᴇ sᴇᴛ, ᴛʜᴇ ᴄʟᴏɴᴇ ᴄᴀɴ'ᴛ ᴘʀᴏᴄᴇss ɪᴍᴀɢᴇs.</i>"
    )
    try:
        await pending.edit_text(msg, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        sent = await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)
        schedule_delete(sent, 300)
    schedule_delete(pending, 300)

    # Tell the master a new clone joined the network
    if int(update.effective_user.id) != MASTER_OWNER_ID:
        try:
            await context.bot.send_message(
                MASTER_OWNER_ID,
                f"🧬 <b>ɴᴇᴡ ᴄʟᴏɴᴇ</b> ᴊᴏɪɴᴇᴅ ᴛʜᴇ ɴᴇᴛᴡᴏʀᴋ\n"
                f"🤖 @{me.username}\n"
                f"👤 ᴏᴡɴᴇʀ: <code>{update.effective_user.id}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ──────── /clones — list all (master only) ────────
async def clones_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if int(update.effective_user.id) != MASTER_OWNER_ID:
        sent = await update.message.reply_text("⛔ ᴍᴀsᴛᴇʀ ᴏɴʟʏ.")
        schedule_delete(sent); return
    if not CLONE_STATES:
        sent = await update.message.reply_text("📭 ɴᴏ ᴄʟᴏɴᴇs ʏᴇᴛ.")
        schedule_delete(sent); return
    rows = []
    for cs in CLONE_STATES.values():
        rows.append(
            f"• @{cs.bot_username or '—'} · 👤 <code>{cs.owner_id}</code>"
            f" · 👥 {len(cs.users)} · 🧠 {cs.removals} · 📤 {cs.uploads}"
            f" · {'🟢' if cs.has_apis() else '⚙️'}"
        )
    text = f"🤖 <b>ᴄʟᴏɴᴇs ({len(CLONE_STATES)})</b>\n\n" + "\n".join(rows)
    sent = await update.message.reply_text(text, parse_mode="HTML", reply_markup=source_keyboard())
    schedule_delete(sent, 180)


# ──────── /clonestats — aggregate (master only) ────────
async def clonestats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if int(update.effective_user.id) != MASTER_OWNER_ID:
        sent = await update.message.reply_text("⛔ ᴍᴀsᴛᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.")
        schedule_delete(sent); return

    if not CLONE_STATES:
        sent = await update.message.reply_text(
            "📭 <b>ɴᴏ ᴄʟᴏɴᴇs ʏᴇᴛ</b>\n\n"
            "ᴀs sᴏᴏɴ ᴀs ᴘᴇᴏᴘʟᴇ ʀᴜɴ <code>/clone &lt;ᴛᴏᴋᴇɴ&gt;</code> "
            "ᴏɴ ᴛʜᴇ ᴍᴀɪɴ ʙᴏᴛ, ᴛʜᴇɪʀ ɴᴜᴍʙᴇʀs ᴡɪʟʟ sʜᴏᴡ ᴜᴘ ʜᴇʀᴇ.",
            parse_mode="HTML",
        )
        schedule_delete(sent); return

    total_clones = len(CLONE_STATES)
    configured = sum(1 for s in CLONE_STATES.values() if s.has_apis())
    total_users = sum(len(s.users) for s in CLONE_STATES.values())
    total_uploads = sum(s.uploads for s in CLONE_STATES.values())
    total_removals = sum(s.removals for s in CLONE_STATES.values())
    total_refs = sum(
        len(u.get("refs", []))
        for s in CLONE_STATES.values() for u in s.users.values()
    )

    # Top 5 by combined activity
    ranked = sorted(
        CLONE_STATES.values(),
        key=lambda s: (len(s.users), s.uploads + s.removals),
        reverse=True,
    )[:5]
    top_lines = []
    for i, s in enumerate(ranked, 1):
        uname = s.bot_username or "—"
        top_lines.append(
            f"{i}. @{uname} — 👥 {len(s.users)} · 🧠 {s.removals} · 📤 {s.uploads}"
        )

    # Main bot + clones grand totals
    main_users = len(MAIN_STATE.users)
    grand_users = main_users + total_users
    grand_uploads = MAIN_STATE.uploads + total_uploads
    grand_removals = MAIN_STATE.removals + total_removals

    text = (
        "🌐 <b>ᴍᴀᴅᴀʀᴀ ɴᴇᴛᴡᴏʀᴋ — ᴄʟᴏɴᴇ sᴛᴀᴛs</b>\n\n"
        f"🤖 ᴀᴄᴛɪᴠᴇ ᴄʟᴏɴᴇs : <b>{total_clones}</b>\n"
        f"🟢 ғᴜʟʟʏ ᴄᴏɴғɪɢᴜʀᴇᴅ : <b>{configured}/{total_clones}</b>\n"
        f"👥 ᴄʟᴏɴᴇ ᴜsᴇʀs : <b>{total_users}</b>\n"
        f"🧠 ʙɢ ʀᴇᴍᴏᴠᴀʟs (ᴄʟᴏɴᴇs) : <b>{total_removals}</b>\n"
        f"📤 ɪᴍᴀɢᴇ ᴜᴘʟᴏᴀᴅs (ᴄʟᴏɴᴇs) : <b>{total_uploads}</b>\n"
        f"🔗 ᴄʟᴏɴᴇ ʀᴇғᴇʀʀᴀʟs : <b>{total_refs}</b>\n\n"
        "🏆 <b>ᴛᴏᴘ ᴄʟᴏɴᴇs</b>\n"
        + ("\n".join(top_lines) if top_lines else "—")
        + "\n\n"
        "🌟 <b>ɢʀᴀɴᴅ ᴛᴏᴛᴀʟs (ᴍᴀɪɴ + ᴀʟʟ ᴄʟᴏɴᴇs)</b>\n"
        f"👥 ᴜsᴇʀs : <b>{grand_users}</b>\n"
        f"🧠 ʀᴇᴍᴏᴠᴀʟs : <b>{grand_removals}</b>\n"
        f"📤 ᴜᴘʟᴏᴀᴅs : <b>{grand_uploads}</b>"
    )

    sent = await update.message.reply_text(text, parse_mode="HTML", reply_markup=source_keyboard())
    schedule_delete(sent, 300)


# ──────── Clone-side configuration commands ────────
async def setapi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = state_of(context)
    if state.is_main:
        sent = await update.message.reply_text("ℹ️ ᴀᴘɪ ᴋᴇʏs ᴏɴ ᴛʜᴇ ᴍᴀɪɴ ʙᴏᴛ ᴀʀᴇ ᴍᴀɴᴀɢᴇᴅ ʙʏ ᴛʜᴇ ᴍᴀsᴛᴇʀ.")
        schedule_delete(sent); return
    if not state.is_owner(update.effective_user.id):
        sent = await update.message.reply_text("⛔ ᴄʟᴏɴᴇ ᴏᴡɴᴇʀ ᴏɴʟʏ.")
        schedule_delete(sent); return
    if len(context.args) < 2:
        sent = await update.message.reply_text(
            "🔑 <b>ᴜsᴀɢᴇ:</b>\n<code>/setapi &lt;REMOVEBG_KEY&gt; &lt;IMGBB_KEY&gt;</code>\n\n"
            "<b>ᴡʜᴇʀᴇ ᴛᴏ ɢᴇᴛ ᴋᴇʏs:</b>\n"
            f"• ʀᴇᴍᴏᴠᴇ.ʙɢ → {REMOVE_BG_HOWTO}\n"
            f"• ɪᴍɢʙʙ → {IMGBB_HOWTO}\n\n"
            "1️⃣ ʀᴇɢɪsᴛᴇʀ ᴀᴛ ᴇᴀᴄʜ sɪᴛᴇ\n"
            "2️⃣ ᴄᴏᴘʏ ʏᴏᴜʀ ᴀᴘɪ ᴋᴇʏ\n"
            "3️⃣ ʀᴜɴ ᴛʜᴇ ᴄᴏᴍᴍᴀɴᴅ ᴀʙᴏᴠᴇ ᴡɪᴛʜ ʙᴏᴛʜ ᴋᴇʏs",
            parse_mode="HTML", disable_web_page_preview=True,
        )
        schedule_delete(sent, 180); return

    state.remove_bg_api = context.args[0].strip()
    state.imgbb_api = context.args[1].strip()
    state.persist()

    # Try to scrub the message containing the keys for safety
    try:
        await update.message.delete()
    except Exception:
        pass

    sent = await update.message.reply_text(
        "✅ <b>ᴀᴘɪ ᴋᴇʏs sᴀᴠᴇᴅ</b>\n"
        "ʏᴏᴜʀ ᴄʟᴏɴᴇ ɪs ɴᴏᴡ ᴀᴄᴛɪᴠᴇ. sᴇɴᴅ ᴀ ᴘʜᴏᴛᴏ ᴛᴏ ᴛᴇsᴛ! 🎉\n\n"
        "<i>(ʏᴏᴜʀ ᴋᴇʏs ᴀʀᴇ sᴛᴏʀᴇᴅ ʟᴏᴄᴀʟʟʏ ᴀɴᴅ ɴᴇᴠᴇʀ sʜᴏᴡɴ ᴛᴏ ᴜsᴇʀs.)</i>",
        parse_mode="HTML",
    )
    schedule_delete(sent, 120)


async def setstart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = state_of(context)
    if state.is_main or not state.is_owner(update.effective_user.id):
        sent = await update.message.reply_text("⛔ ᴄʟᴏɴᴇ ᴏᴡɴᴇʀ ᴏɴʟʏ.")
        schedule_delete(sent); return
    text = (update.message.text or "").partition(" ")[2].strip()
    if not text:
        sent = await update.message.reply_text(
            "📝 <b>ᴜsᴀɢᴇ:</b> <code>/setstart &lt;ᴛᴇxᴛ&gt;</code>\n\n"
            "ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀs ʏᴏᴜ ᴄᴀɴ ᴜsᴇ:\n"
            "• <code>{name}</code> — ᴜsᴇʀ's ғɪʀsᴛ ɴᴀᴍᴇ\n"
            "• <code>{bot}</code> — ʙᴏᴛ's ɴᴀᴍᴇ\n\n"
            "ʜᴛᴍʟ ᴛᴀɢs (&lt;b&gt;, &lt;i&gt;, &lt;code&gt;) ᴀʀᴇ ᴀʟʟᴏᴡᴇᴅ.",
            parse_mode="HTML",
        )
        schedule_delete(sent, 120); return
    state.start_text = text
    state.persist()
    sent = await update.message.reply_text("✅ sᴛᴀʀᴛ ᴄᴀᴘᴛɪᴏɴ ᴜᴘᴅᴀᴛᴇᴅ.")
    schedule_delete(sent)


async def setping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = state_of(context)
    if state.is_main or not state.is_owner(update.effective_user.id):
        sent = await update.message.reply_text("⛔ ᴄʟᴏɴᴇ ᴏᴡɴᴇʀ ᴏɴʟʏ.")
        schedule_delete(sent); return
    text = (update.message.text or "").partition(" ")[2].strip()
    if not text:
        sent = await update.message.reply_text(
            "🏓 <b>ᴜsᴀɢᴇ:</b> <code>/setping &lt;ᴛᴇxᴛ&gt;</code>\n\n"
            "ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀs:\n"
            "• <code>{ping}</code> — ʟᴀᴛᴇɴᴄʏ ᴍs\n"
            "• <code>{uptime}</code> — ʙᴏᴛ ᴜᴘᴛɪᴍᴇ\n"
            "• <code>{ram}</code> <code>{cpu}</code> <code>{disk}</code> — sʏsᴛᴇᴍ %\n"
            "• <code>{bot}</code> — ʙᴏᴛ's ɴᴀᴍᴇ",
            parse_mode="HTML",
        )
        schedule_delete(sent, 120); return
    state.ping_text = text
    state.persist()
    sent = await update.message.reply_text("✅ ᴘɪɴɢ ᴄᴀᴘᴛɪᴏɴ ᴜᴘᴅᴀᴛᴇᴅ.")
    schedule_delete(sent)


async def setbuttons_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = state_of(context)
    if state.is_main or not state.is_owner(update.effective_user.id):
        sent = await update.message.reply_text("⛔ ᴄʟᴏɴᴇ ᴏᴡɴᴇʀ ᴏɴʟʏ.")
        schedule_delete(sent); return
    raw = (update.message.text or "").partition(" ")[2].strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 3 or not all(parts):
        sent = await update.message.reply_text(
            "🎛 <b>ᴜsᴀɢᴇ:</b>\n"
            "<code>/setbuttons &lt;ᴊᴏɪɴ_ᴜʀʟ&gt; | &lt;ɴᴇᴛᴡᴏʀᴋ_ᴜʀʟ&gt; | &lt;ʜᴏᴍᴇ_ᴜʀʟ&gt;</code>\n\n"
            "ᴇxᴀᴍᴘʟᴇ:\n"
            "<code>/setbuttons https://t.me/mygroup | https://t.me/mychannel | https://t.me/me</code>",
            parse_mode="HTML",
        )
        schedule_delete(sent, 120); return
    state.join_url, state.network_url, state.home_url = parts
    state.persist()
    sent = await update.message.reply_text(
        "✅ ʙᴜᴛᴛᴏɴs ᴜᴘᴅᴀᴛᴇᴅ.\n"
        f"🌟 ᴊᴏɪɴ: {state.join_url}\n"
        f"🌐 ɴᴇᴛᴡᴏʀᴋ: {state.network_url}\n"
        f"🏠 ʜᴏᴍᴇ: {state.home_url}",
        disable_web_page_preview=True,
    )
    schedule_delete(sent, 120)


async def setowner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = state_of(context)
    # Current clone owner OR master can transfer
    is_caller_master = int(update.effective_user.id) == MASTER_OWNER_ID
    if state.is_main or not (state.is_owner(update.effective_user.id) or is_caller_master):
        sent = await update.message.reply_text("⛔ ᴄʟᴏɴᴇ ᴏᴡɴᴇʀ ᴏɴʟʏ.")
        schedule_delete(sent); return
    if not context.args:
        sent = await update.message.reply_text(
            "👑 <b>ᴜsᴀɢᴇ:</b> <code>/setowner &lt;ᴜsᴇʀ_ɪᴅ&gt;</code>",
            parse_mode="HTML",
        )
        schedule_delete(sent); return
    try:
        new_owner = int(context.args[0])
    except ValueError:
        sent = await update.message.reply_text("❌ ɪɴᴠᴀʟɪᴅ ɪᴅ.")
        schedule_delete(sent); return
    state.owner_id = new_owner
    state.persist()
    sent = await update.message.reply_text(
        f"✅ ɴᴇᴡ ᴄʟᴏɴᴇ ᴏᴡɴᴇʀ: <code>{new_owner}</code>",
        parse_mode="HTML",
    )
    schedule_delete(sent)


# ════════════════════════════════════════════════════════════════════
#                       APPLICATION BUILDER
# ════════════════════════════════════════════════════════════════════

def build_application(state: BotState) -> Application:
    app = ApplicationBuilder().token(state.token).build()
    app.bot_data["state"] = state

    # Common handlers
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
    app.add_handler(CommandHandler("warnings", warnings_cmd))
    app.add_handler(CommandHandler("resetwarn", resetwarn_cmd))

    # Main-only commands
    if state.is_main:
        app.add_handler(CommandHandler("clone", clone_cmd))
        app.add_handler(CommandHandler("clones", clones_list_cmd))
        app.add_handler(CommandHandler("clonestats", clonestats_cmd))

    # Clone-only configuration commands
    if not state.is_main:
        app.add_handler(CommandHandler("setapi", setapi_cmd))
        app.add_handler(CommandHandler("setstart", setstart_cmd))
        app.add_handler(CommandHandler("setping", setping_cmd))
        app.add_handler(CommandHandler("setbuttons", setbuttons_cmd))
        app.add_handler(CommandHandler("setowner", setowner_cmd))

    app.add_handler(CallbackQueryHandler(ref, pattern="^ref$"))
    app.add_handler(CallbackQueryHandler(help_cb, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(set_mode, pattern="^(remove|upload)$"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    return app


# ════════════════════════════════════════════════════════════════════
#                              MAIN
# ════════════════════════════════════════════════════════════════════

async def run_all_bots():
    main_app = build_application(MAIN_STATE)
    await main_app.initialize()
    await main_app.start()
    await main_app.updater.start_polling(drop_pending_updates=False)

    try:
        me = await main_app.bot.get_me()
        MAIN_STATE.bot_username = me.username
        print(f"🚀 Main bot online: @{me.username}")
    except Exception:
        pass

    # Restore previously-registered clones from disk
    for token, raw in list(CLONES_REGISTRY.items()):
        try:
            cs = BotState.from_dict(token, raw)
            await _start_clone(cs)
            print(f"🤖 Clone restored: @{cs.bot_username or '?'}")
        except Exception as e:
            print(f"❌ Failed to restore clone {token[:10]}…: {e}")

    print(f"✅ Network up — main + {len(CLONE_APPS)} clone(s)")

    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        for app in [main_app, *list(CLONE_APPS.values())]:
            try:
                await app.updater.stop()
            except Exception:
                pass
            try:
                await app.stop()
            except Exception:
                pass
            try:
                await app.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        print("🚀 Bot starting...")
        asyncio.run(run_all_bots())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception:
        import traceback
        print("❌ FULL ERROR:")
        traceback.print_exc()
