"""
Telegram handlers for the simplified Netflix login bot.
"""

import asyncio
import io
import os
import time
import logging
from datetime import datetime
from html import escape
from concurrent.futures import ThreadPoolExecutor

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import Forbidden
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import (
    ADMIN_IDS, GROUP_USERNAME, DAILY_LIMIT, MAX_REF_BONUS,
    BOT_USERNAME, CURRENCY_MAP, BASE_DIR,
)
from lang import t
from storage import (
    load_cookies, save_cookies_for,
    get_random_index, mark_dead, mark_permanent_dead, release_index,
    get_cookie_line, get_cookie_stats, get_total_cookie_stats, record_account_usage,
    get_user, set_user_lang, get_user_lang, get_total_users, delete_user,
    can_use_today, record_use, get_streak,
    get_ref_count, get_ref_bonus, add_referral,
    get_uses_left, consume_use, add_uses, get_next_refill_time,
    create_gift_code, redeem_gift_code, get_user_daily_limit_val,
    get_all_user_ids,
)

logger = logging.getLogger("NetflixBot")
_executor = ThreadPoolExecutor(max_workers=1)  # Queue: xử lý từng người một để tránh Netflix block
_active_sessions = {}
_feedback_jobs = {}
_get_inflight_users = set()
_inflight_lock = None  # lazy-init asyncio.Lock
FEEDBACK_DELAY_SECONDS = 30 * 60


def _get_inflight_lock():
    global _inflight_lock
    if _inflight_lock is None:
        _inflight_lock = asyncio.Lock()
    return _inflight_lock


def _fmt_clock(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


# ═══════════════════════════════════════════════════════════════════
#  Keyboards
# ═══════════════════════════════════════════════════════════════════

def lang_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f1fb\U0001f1f3 Ti\u1ebfng Vi\u1ec7t", callback_data="lang_vi"),
         InlineKeyboardButton("\U0001f1ec\U0001f1e7 English", callback_data="lang_en")],
    ])


def main_keyboard(lang, user_id=None):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_loginlink", lang), callback_data="loginlink_input"),
         InlineKeyboardButton(t("btn_tv", lang), callback_data="tv_input")],
    ])


def back_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_back", lang), callback_data="back")],
    ])


def join_group_keyboard(lang):
    """Keyboard shown when user hasn't joined the group yet."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Tham Gia Nhóm", url=f"https://t.me/{GROUP_USERNAME}")],
        [InlineKeyboardButton("🔄 Kiểm Tra Lại", callback_data="check_joined")],
    ])


# ═══════════════════════════════════════════════════════════════════
#  Group check
# ═══════════════════════════════════════════════════════════════════

async def check_user_in_group(bot, user_id):
    try:
        member = await bot.get_chat_member(f"@{GROUP_USERNAME}", user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False


def _new_session_id(user_id):
    return f"{user_id}-{int(time.time())}"


def _save_active_session(user_id, lang, payload):
    session_id = _new_session_id(user_id)
    _active_sessions[user_id] = {
        "session_id": session_id,
        "lang": lang,
        "created_at": int(time.time()),
        **(payload or {}),
    }
    return session_id


def _schedule_feedback_prompt(job_queue, user_id, lang, session_id):
    old = _feedback_jobs.get(user_id)
    if old:
        try:
            old.schedule_removal()
        except Exception:
            pass

    job = job_queue.run_once(
        _send_feedback_prompt,
        when=FEEDBACK_DELAY_SECONDS,
        data={"user_id": user_id, "lang": lang, "session_id": session_id},
        name=f"feedback_{user_id}",
    )
    _feedback_jobs[user_id] = job


def _cancel_feedback_job(user_id):
    old = _feedback_jobs.pop(user_id, None)
    if old:
        try:
            old.schedule_removal()
        except Exception:
            pass


async def _send_feedback_prompt(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data or {}
    user_id = data.get("user_id")
    lang = data.get("lang") or "vi"
    session_id = data.get("session_id")
    active = _active_sessions.get(user_id)
    if not active or active.get("session_id") != session_id:
        return

    # Auto-recheck session after 30 minutes
    try:
        await context.bot.send_message(chat_id=user_id, text="⏳ Đang kiểm tra lại phiên đăng nhập sau 30 phút...")
    except Exception:
        return

    loop = asyncio.get_event_loop()
    re_status, re_text, re_cookie_file_text, re_payload = await loop.run_in_executor(
        _executor, _recheck_active_cookie, active, user_id
    )

    if re_status == "LIVE":
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ Phiên đăng nhập trước đó vẫn còn hoạt động.",
            )
        except Exception:
            pass
        _cancel_feedback_job(user_id)
        return

    if re_status == "DEAD":
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "⚠️ Phiên đăng nhập trước đó không còn hoạt động.\n\n"
                    "🔗 Dùng /loginlink hoặc nút Lấy Link để tạo link mới.\n"
                    "📺 Nếu cần đăng nhập TV, dùng /tv <mã_TV> hoặc nút Login TV."
                ),
            )
        except Exception:
            pass
        _cancel_feedback_job(user_id)
        return

    # ERROR or other status
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ Tạm thời chưa kiểm tra lại được phiên đăng nhập này. Bạn thử lại sau ít phút.",
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
#  /start -- Language picker or Welcome
# ═══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    lang = get_user_lang(user.id)
    if not lang:
        await msg.reply_text(
            "\U0001f310 Ch\u1ecdn ng\u00f4n ng\u1eef / Choose language:",
            reply_markup=lang_keyboard(),
        )
        return

    # Check if user has joined the group
    in_group = await check_user_in_group(context.bot, user.id)
    if not in_group:
        await msg.reply_text(
            f"⚠️ <b>Bạn chưa tham gia nhóm!</b>\n\n"
            f"📢 Bạn cần tham gia nhóm @{GROUP_USERNAME} trước khi sử dụng bot.\n\n"
            f"👉 Ấn nút bên dưới để vào nhóm, sau đó ấn <b>🔄 Kiểm Tra Lại</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=join_group_keyboard(lang),
            disable_web_page_preview=True,
        )
        return

    name = user.first_name or user.username or "User"
    await msg.reply_text(
        t("welcome", lang, name=name, group=GROUP_USERNAME),
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(lang, user.id),
        disable_web_page_preview=True,
    )


# ═══════════════════════════════════════════════════════════════════
#  Cookie check & format (NO login link in output)
# ═══════════════════════════════════════════════════════════════════

HTTPONLY_COOKIE_NAMES = {"NetflixId", "SecureNetflixId", "gsid"}
SECURE_COOKIE_NAMES = {"SecureNetflixId", "NetflixId", "gsid"}
NON_SECURE_COOKIE_NAMES = {"netflix-sans-normal-3-loaded", "netflix-sans-bold-3-loaded", "profilesNewSession", "flwssn", "nfvdid", "OptanonConsent"}


def _cookie_sort_key(name):
    priority = {
        "NetflixId": 0,
        "SecureNetflixId": 1,
        "nfvdid": 2,
        "gsid": 3,
    }
    return (priority.get(name, 99), name.lower())


def _to_netscape_cookie_line(name, value, expiry_epoch):
    domain = ".netflix.com"
    include_subdomains = "TRUE"
    path = "/"
    http_only = name in HTTPONLY_COOKIE_NAMES
    is_secure = "TRUE" if (http_only or name in SECURE_COOKIE_NAMES) else "FALSE"
    domain_field = f"#HttpOnly_{domain}" if http_only else domain
    return f"{domain_field}\t{include_subdomains}\t{path}\t{is_secure}\t{expiry_epoch}\t{name}\t{value}"


def _build_cookie_file_text(cookie_dict):
    clean_items = []
    for name, value in (cookie_dict or {}).items():
        if value is None:
            continue
        sval = str(value).strip().replace("\t", "%09").replace("\r", "").replace("\n", "")
        if not sval or sval == "-":
            continue
        clean_items.append((str(name), sval))

    clean_items.sort(key=lambda kv: _cookie_sort_key(kv[0]))
    expiry_epoch = int(time.time()) + (180 * 24 * 60 * 60)

    lines = [
        "# Netscape HTTP Cookie File",
        "# http://curl.haxx.se/rfc/cookie_spec.html",
        "# This file was generated by Cookie-Editor",
        "",
    ]

    for name, value in clean_items:
        lines.append(_to_netscape_cookie_line(name, value, expiry_epoch))

    lines.append("")
    return "\n".join(lines)


def _check_and_format(raw_cookie, user_id=None):
    """
    Check cookie and format account output.
    v3.0.2: Login link is NOT included in the output (separate /loginlink command).
    """
    from checker import check_cookie, parse_cookie_line

    def safe(val):
        if val is None:
            return "-"
        return escape(str(val))

    netflix_id, secure_id, extras = parse_cookie_line(raw_cookie)
    if not netflix_id:
        return None, "INVALID", None, None

    info = check_cookie(netflix_id, secure_id)
    
    # Kiểm tra status trực tiếp từ checker
    if info["status"] == "DEAD":
        membership = str(info.get("membershipStatus", "")).upper()
        # ANONYMOUS, FORMER_MEMBER, NEVER_MEMBER, NON_MEMBER → xóa vĩnh viễn ngay
        if membership in ("ANONYMOUS", "FORMER_MEMBER", "NEVER_MEMBER", "NON_MEMBER"):
            logger.info(f"Cookie PERM_DEAD - membershipStatus: {membership}")
            return None, "PERM_DEAD", None, None
        logger.info(f"Cookie DEAD detected by checker")
        return None, "DEAD", None, None
    if info["status"] == "ERROR":
        return None, "ERROR", None, None
    if str(info.get("membershipStatus", "")).upper() in ("FORMER_MEMBER", "ANONYMOUS", "NEVER_MEMBER", "NON_MEMBER"):
        logger.info(f"Membership shows {info.get('membershipStatus')}, marking PERM_DEAD")
        return None, "PERM_DEAD", None, None

    plan = str(info.get("plan", "")).lower()
    quality = str(info.get("videoQuality", "")).upper()  

    logger.info(f"Cookie is alive - {info.get('plan', 'Unknown')} ({quality})")

    cookie_dict = {"NetflixId": netflix_id}
    if secure_id:
        cookie_dict["SecureNetflixId"] = secure_id
    cookie_dict.update(extras)
    cookie_dict.update(info.get("_cookies") or {})

    country = info.get("country", "-")
    currency = CURRENCY_MAP.get(country, "?")
    membership = info.get("membershipStatus", "-")
    status_text = "Active" if membership in ("CURRENT_MEMBER", "-", "") else membership

    profiles = info.get("profiles", "-")
    profile_list = [p.strip() for p in str(profiles).split(",") if p.strip()] if profiles not in ("-", "") else []
    first_profile = profile_list[0] if profile_list else "-"

    num_profiles = int(info.get("numProfiles", 0) or 0)
    if num_profiles == 0 and profile_list:
        num_profiles = len(profile_list)

    owner = info.get("owner", "-")
    if owner == "-":
        owner = info.get("displayName", "-")

    phone = info.get("phone", "-")
    if phone == "-":
        phone = info.get("phoneNumber", "-")

    extra_members = "Yes" if info.get("extraMembers") else "No"

    # v3.0.2: Simple output - chỉ hiển thị PLAN
    lines = [
        "🎬 <b>NETFLIX ACCOUNT</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📋 <b>Plan:</b> {safe(info.get('plan', '-'))} ({safe(info.get('videoQuality', '-'))})",
        f"🌍 <b>Region:</b> <code>{safe(country)}</code> ({safe(currency)})",
        f"👤 <b>Owner:</b> {safe(owner)}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "<i>Dùng /loginlink để lấy link đăng nhập</i>",
    ]

    cookie_file_text = _build_cookie_file_text(cookie_dict)
    payload = {
        "netflix_id": netflix_id,
        "secure_id": secure_id,
        "cookie_dict": cookie_dict,
        "auth_url": info.get("authURL"),
    }
    return "\n".join(lines), "LIVE", cookie_file_text, payload


def _generate_login_link(active_session):
    """
    Generate Netflix login link from active session cookies.
    Uses 3 API methods (iOS, Android, Web) like v3.0.2.
    """
    if not active_session:
        return None, "Không có session hoạt động"

    cookie_dict = active_session.get("cookie_dict") or {}
    netflix_id = active_session.get("netflix_id") or cookie_dict.get("NetflixId")
    secure_id = active_session.get("secure_id") or cookie_dict.get("SecureNetflixId")

    if not netflix_id:
        return None, "Không tìm thấy cookie. Vui lòng lấy acc mới."

    from checker import generate_nftoken

    # Ensure cookie_dict has required fields
    if "NetflixId" not in cookie_dict and netflix_id:
        cookie_dict["NetflixId"] = netflix_id
    if "SecureNetflixId" not in cookie_dict and secure_id:
        cookie_dict["SecureNetflixId"] = secure_id

    token, error = generate_nftoken(cookie_dict)
    if token:
        login_link = f"https://netflix.com/?nftoken={token}"
        return login_link, None
    return None, error


def _find_and_generate_login_link(user_id):
    """
    Auto-find a random live cookie and generate login link.
    Returns (link, error, payload) — payload for saving active session.
    """
    from checker import parse_cookie_line, check_cookie, generate_nftoken

    stats = get_cookie_stats(user_id=user_id)
    max_tries = min(stats["remaining"], 100)
    attempts = 0
    idle_waits = 0

    while attempts < max_tries:
        idx = get_random_index(user_id=user_id)
        if idx is None:
            idle_waits += 1
            if idle_waits > 10:
                break
            time.sleep(0.05)
            continue
        idle_waits = 0

        raw = get_cookie_line(idx, user_id=user_id)
        if not raw:
            release_index(idx, user_id=user_id)
            continue

        attempts += 1
        logger.info(f"[LoginLink] Trying cookie #{idx + 1}... (attempt {attempts}/{max_tries})")

        netflix_id, secure_id, extras = parse_cookie_line(raw)
        if not netflix_id:
            release_index(idx, user_id=user_id)
            continue

        info = check_cookie(netflix_id, secure_id)

        if info.get("status") == "DEAD":
            mark_dead(idx, user_id=user_id)
            continue
        if info.get("status") == "ERROR":
            release_index(idx, user_id=user_id)
            time.sleep(1)
            continue
        if str(info.get("membershipStatus", "")).upper() == "FORMER_MEMBER":
            mark_permanent_dead(idx, user_id=user_id)
            save_cookies_for(user_id=user_id)
            continue

        # Cookie is LIVE — build cookie dict and generate nftoken
        cookie_dict = {"NetflixId": netflix_id}
        if secure_id:
            cookie_dict["SecureNetflixId"] = secure_id
        cookie_dict.update(extras)
        cookie_dict.update(info.get("_cookies") or {})

        token, error = generate_nftoken(cookie_dict)

        release_index(idx, user_id=user_id)

        if token:
            login_link = f"https://netflix.com/?nftoken={token}"
            payload = {
                "netflix_id": netflix_id,
                "secure_id": secure_id,
                "cookie_dict": cookie_dict,
                "auth_url": info.get("authURL"),
                "_cookie_index": idx,
                "source_index": idx,
                "raw_cookie": raw,
            }
            record_account_usage(idx, user_id=user_id)
            return login_link, None, payload
        else:
            # Token generation failed for this cookie, try next
            logger.info(f"[LoginLink] Cookie #{idx + 1} LIVE but nftoken failed: {error}")
            continue

    return None, "Không tìm thấy cookie hoạt động. Thử lại sau.", None


def _recheck_active_cookie(active_session, user_id=None):
    """Re-check the exact cookie previously given to user."""
    if not active_session:
        return "ERROR", None, None, None



    idx = active_session.get("source_index")
    if idx is None:
        idx = active_session.get("_cookie_index")
    raw = None
    if idx is not None:
        raw = get_cookie_line(int(idx), user_id=user_id)
    if not raw:
        raw = active_session.get("raw_cookie")
    if not raw:
        return "ERROR", None, None, None

    text, status, cookie_file_text, payload = _check_and_format(raw, user_id=user_id)
    if status == "LIVE":
        payload = payload or {}
        payload["source_index"] = idx
        payload["_cookie_index"] = idx
        payload["raw_cookie"] = raw
        return "LIVE", text, cookie_file_text, payload

    if status in ("DEAD", "INVALID", "PERM_DEAD"):
        if idx is not None:
            mark_permanent_dead(int(idx), user_id=user_id)
            save_cookies_for(user_id=user_id)
        return "DEAD", None, None, None

    return "ERROR", None, None, None


def _find_live_account(user_id=None):
    """
    Find live account from single pool.
    """
    dead_found = False
    permanent_dead_found = False
    stats = get_cookie_stats(user_id=user_id)
    max_tries = min(stats["remaining"], 180)
    attempts = 0
    idle_waits = 0

    while attempts < max_tries:
        idx = get_random_index(user_id=user_id)
        if idx is None:
            idle_waits += 1
            if idle_waits > 10:
                break
            time.sleep(0.05)  # minimal wait, non-blocking friendly
            continue
        idle_waits = 0

        raw = get_cookie_line(idx, user_id=user_id)
        if not raw:
            release_index(idx, user_id=user_id)
            continue

        attempts += 1
        logger.info(f"Trying cookie #{idx + 1}... (attempt {attempts}/{max_tries})")

        text, status, cookie_file_text, payload = _check_and_format(raw, user_id=user_id)

        if status == "LIVE":
            logger.info(f"Cookie #{idx + 1} -> LIVE!")
            record_account_usage(idx, user_id=user_id)
            release_index(idx, user_id=user_id)
            # Chỉ lưu khi có permanent dead cookies
            if permanent_dead_found:
                save_cookies_for(user_id=user_id)
            payload = payload or {}
            payload["_cookie_index"] = idx
            payload["source_index"] = idx
            payload["raw_cookie"] = raw
            return text, cookie_file_text, payload

        logger.info(f"Cookie #{idx + 1} -> {status}")
        if status in ("DEAD", "INVALID"):  # Chỉ xóa thực sự dead cookies
            mark_dead(idx, user_id=user_id)
            dead_found = True
        elif status == "PERM_DEAD":
            mark_permanent_dead(idx, user_id=user_id)
            permanent_dead_found = True
        elif status == "ERROR":
            # Lỗi mạng/timeout → không đánh dấu dead, chỉ release để thử lại sau
            release_index(idx, user_id=user_id)
            logger.warning(f"Cookie #{idx + 1} ERROR - released (not marked dead)")
            time.sleep(2)  # Đợi thêm khi gặp lỗi
            release_index(idx, user_id=user_id)
            logger.info(f"Cookie #{idx + 1} LIVE but NOT Premium - skipped")
        else:
            release_index(idx, user_id=user_id)

        # No blocking sleep -- each cookie is a different account,
        # concurrent requests from different users proceed in parallel

    # Chỉ lưu khi có permanent dead cookies, không lưu khi chỉ có temporary dead
    if permanent_dead_found:
        save_cookies_for(user_id=user_id)
    return None


# ═══════════════════════════════════════════════════════════════════
#  Button handler
# ═══════════════════════════════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    lang = get_user_lang(user.id) or "vi"
    user_limit = DAILY_LIMIT

    # -- "Check Joined" button: verify group membership --
    if data == "check_joined":
        in_group = await check_user_in_group(context.bot, user.id)
        if in_group:
            name = user.first_name or user.username or "User"
            await query.edit_message_text(
                f"✅ Đã xác nhận! Chào mừng bạn đến với bot.\n\n"
                + t("welcome", lang, name=name, group=GROUP_USERNAME),
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(lang, user.id),
                disable_web_page_preview=True,
            )
        else:
            await query.edit_message_text(
                f"⚠️ <b>Bạn chưa tham gia nhóm!</b>\n\n"
                f"📢 Bạn cần tham gia nhóm @{GROUP_USERNAME} trước khi sử dụng bot.\n\n"
                f"👉 Ấn nút bên dưới để vào nhóm, sau đó ấn <b>🔄 Kiểm Tra Lại</b>.",
                parse_mode=ParseMode.HTML,
                reply_markup=join_group_keyboard(lang),
                disable_web_page_preview=True,
            )
        return

    # -- Group membership gate: block all actions if not in group --
    # Allow: language selection, back button
    if data not in ("lang_vi", "lang_en", "change_lang", "back"):
        in_group = await check_user_in_group(context.bot, user.id)
        if not in_group:
            await query.edit_message_text(
                f"⚠️ <b>Bạn chưa tham gia nhóm!</b>\n\n"
                f"📢 Bạn cần tham gia nhóm @{GROUP_USERNAME} trước khi sử dụng bot.\n\n"
                f"👉 Ấn nút bên dưới để vào nhóm, sau đó ấn <b>🔄 Kiểm Tra Lại</b>.",
                parse_mode=ParseMode.HTML,
                reply_markup=join_group_keyboard(lang),
                disable_web_page_preview=True,
            )
            return

    # -- Language selection --
    if data in ("lang_vi", "lang_en"):
        chosen = "vi" if data == "lang_vi" else "en"
        set_user_lang(user.id, chosen)
        name = user.first_name or user.username or "User"
        await query.edit_message_text(
            t("welcome", chosen, name=name, group=GROUP_USERNAME),
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(chosen, user.id),
            disable_web_page_preview=True,
        )
        return

    if data == "change_lang":
        await query.edit_message_text(
            "\U0001f310 Ch\u1ecdn ng\u00f4n ng\u1eef / Choose language:",
            reply_markup=lang_keyboard(),
        )
        return

    if data == "tv_input":
        context.user_data["await_tv_code"] = True
        await context.bot.send_message(
            chat_id=user.id,
            text="📺 Vui lòng nhập mã TV ở dưới (ví dụ: ABCD1234).",
        )
        return

    if data == "loginlink_input":
        # Check remaining uses
        uses_left_val = get_uses_left(user.id)
        if uses_left_val <= 0:
            await query.edit_message_text(
                f"❌ Bạn đã hết lượt hôm nay.\n"
                f"⏰ Quay lại sau 00:00 để lấy link mới.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard(lang),
            )
            return

        await query.edit_message_text(
            "⏳ Đang tự động tìm cookie và tạo Login Link...",
            parse_mode=ParseMode.HTML,
        )

        loop = asyncio.get_event_loop()
        link, error, payload = await loop.run_in_executor(
            _executor, _find_and_generate_login_link, user.id
        )

        try:
            if link:
                # Consume use
                if consume_use(user.id, 1):
                    record_use(user.id, username=user.username, first_name=user.first_name)

                await context.bot.send_message(
                    chat_id=user.id,
                    text=(
                        "🔗 <b>NETFLIX LOGIN LINK</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"<code>{escape(link)}</code>\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "💡 <i>Link có hiệu lực ~1 giờ</i>\n"
                        "📌 <i>Mở link trên trình duyệt để đăng nhập</i>\n"
                        "📱 <i>Hỗ trợ iOS & Android</i>"
                    ),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )

                # Save active session
                if payload:
                    payload["mode"] = "loginlink"
                    session_id = _save_active_session(user.id, lang, payload)
                    if context.job_queue:
                        _schedule_feedback_prompt(context.job_queue, user.id, lang, session_id)

                uses_left_val = get_uses_left(user.id)
                try:
                    await context.bot.send_message(
                        chat_id=user.id,
                        text=(
                            f"🍪 Còn lại: {uses_left_val}/{user_limit} lượt hôm nay\n"
                            f"⏰ Reset lúc 00:00 đêm nay"
                        ),
                    )
                except Exception:
                    pass
            else:
                short_err = str(error or "Unknown")
                if "access denied" in short_err.lower():
                    short_err = "Account blocked auto-login token"
                await context.bot.send_message(
                    chat_id=user.id,
                    text=f"❌ Không thể tạo Login Link: {escape(short_err)}\n\n💡 Thử lại sau ít phút.",
                    parse_mode=ParseMode.HTML,
                )

            # Restore main menu
            name = user.first_name or user.username or "User"
            await context.bot.send_message(
                chat_id=user.id,
                text=t("welcome", lang, name=name, group=GROUP_USERNAME),
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(lang, user.id),
                disable_web_page_preview=True,
            )
        except Forbidden:
            logger.warning("User %s has blocked the bot or never started it.", user.id)
        return

    # -- Back --
    if data == "back":
        name = user.first_name or user.username or "User"
        await query.edit_message_text(
            t("welcome", lang, name=name, group=GROUP_USERNAME),
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(lang, user.id),
            disable_web_page_preview=True,
        )
        return

    if data in {"get", "stats", "ref", "help", "buy_uses", "buy_5", "buy_20", "buy_100", "redeem_input"}:
        await query.edit_message_text(
            (
                "⚠️ Các chức năng cũ đã được gỡ khỏi bot này.\n\n"
                "Bot hiện chỉ còn:\n"
                "🔗 Lấy Link đăng nhập\n"
                "📺 Login TV"
            ),
            reply_markup=main_keyboard(lang, user.id),
        )
        return



# ═══════════════════════════════════════════════════════════════════
#  Admin: /reload
# ═══════════════════════════════════════════════════════════════════

async def cmd_addluot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return

    if not context.args:
        await msg.reply_text(
            "Cach dung:\n/addluot <so_luot>\n/addluot <user_id> <so_luot>"
        )
        return

    try:
        if len(context.args) == 1:
            target_id = user.id
            amount = int(context.args[0])
        else:
            target_id = int(context.args[0])
            amount = int(context.args[1])
    except ValueError:
        await msg.reply_text("Sai dinh dang. Vi du: /addluot 123456789 5")
        return

    if amount <= 0:
        await msg.reply_text("So luot phai > 0")
        return

    new_total = add_uses(target_id, amount)
    await msg.reply_text(
        f"✅ Da cong {amount} luot cho user <code>{target_id}</code>\n"
        f"Luot hien tai: <b>{new_total}</b>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_addcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return

    if len(context.args) < 2:
        await msg.reply_text(
            "Cach dung:\n/addcode <CODE> <SO_LUOT> [SO_NGUOI_DUNG]\n"
            "Vi du: /addcode ANHYEUEM 5 1"
        )
        return

    code = context.args[0].strip()
    try:
        uses = int(context.args[1])
    except ValueError:
        await msg.reply_text("So luot khong hop le.")
        return

    claims = 1
    if len(context.args) >= 3:
        try:
            claims = int(context.args[2])
        except ValueError:
            await msg.reply_text("So nguoi dung code khong hop le.")
            return

    ok, err_msg, ncode = create_gift_code(code, uses, created_by=user.id, max_claims=claims)
    if not ok:
        await msg.reply_text(f"❌ {err_msg}")
        return

    await msg.reply_text(
        "✅ Tao gift code thanh cong\n"
        f"Code: <code>{ncode}</code>\n"
        f"So luot cong: <b>{uses}</b>\n"
        f"So luot nhap code: <b>{claims}</b>",
        parse_mode=ParseMode.HTML,
    )


# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
#  /loginlink command -- Generate login link from active session
# ═══════════════════════════════════════════════════════════════════

async def cmd_loginlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    lang = get_user_lang(user.id) or "vi"
    user_limit = DAILY_LIMIT

    # Check remaining uses
    uses_left_val = get_uses_left(user.id)
    if uses_left_val <= 0:
        await msg.reply_text(
            f"❌ Bạn đã hết lượt hôm nay.\n"
            f"⏰ Quay lại sau 00:00 để lấy link mới.",
            parse_mode=ParseMode.HTML,
        )
        return

    await msg.reply_text(
        f"⏳ Đang tự động tìm cookie và tạo Login Link...\n\n"
        f"<i>Vui lòng đợi, đang kiểm tra cookies...</i>",
        parse_mode=ParseMode.HTML,
    )

    loop = asyncio.get_event_loop()
    link, error, payload = await loop.run_in_executor(
        _executor, _find_and_generate_login_link, user.id
    )

    if link:
        # Consume use
        if consume_use(user.id, 1):
            record_use(user.id, username=user.username, first_name=user.first_name)

        user_info = f"@{user.username}" if user.username else user.first_name or str(user.id)
        logger.info(f"🔗 LOGIN LINK GIVEN to {user_info} (ID: {user.id})")

        await msg.reply_text(
            "🔗 <b>NETFLIX LOGIN LINK</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<code>{escape(link)}</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Link có hiệu lực ~1 giờ</i>\n"
            "📌 <i>Mở link trên trình duyệt để đăng nhập</i>\n"
            "📱 <i>Hỗ trợ iOS & Android</i>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

        # Save active session for later re-check
        if payload:
            payload["mode"] = "loginlink"
            session_id = _save_active_session(user.id, lang, payload)
            if context.job_queue:
                _schedule_feedback_prompt(context.job_queue, user.id, lang, session_id)

        uses_left_val = get_uses_left(user.id)
        try:
            await msg.reply_text(
                f"🍪 Còn lại: {uses_left_val}/{user_limit} lượt hôm nay\n"
                f"⏰ Reset lúc 00:00 đêm nay",
            )
        except Exception:
            pass
    else:
        short_err = str(error or "Unknown")
        if "access denied" in short_err.lower():
            short_err = "Account blocked auto-login token"
        await msg.reply_text(
            f"❌ Không thể tạo Login Link: {escape(short_err)}\n\n"
            "💡 Thử lại sau ít phút.",
            parse_mode=ParseMode.HTML,
        )


# ═══════════════════════════════════════════════════════════════════
#  TV Login
# ═══════════════════════════════════════════════════════════════════

def _find_and_tv_login(user_id, tv_code):
    """
    Auto-find a random live cookie and login TV with the given code.
    Returns (ok, message, payload).
    """
    from checker import parse_cookie_line, check_cookie, tv_login_with_code

    stats = get_cookie_stats(user_id=user_id)
    max_tries = min(stats["remaining"], 100)
    attempts = 0
    idle_waits = 0

    while attempts < max_tries:
        idx = get_random_index(user_id=user_id)
        if idx is None:
            idle_waits += 1
            if idle_waits > 10:
                break
            time.sleep(0.05)
            continue
        idle_waits = 0

        raw = get_cookie_line(idx, user_id=user_id)
        if not raw:
            release_index(idx, user_id=user_id)
            continue

        attempts += 1
        logger.info(f"[TV] Trying cookie #{idx + 1}... (attempt {attempts}/{max_tries})")

        netflix_id, secure_id, extras = parse_cookie_line(raw)
        if not netflix_id:
            release_index(idx, user_id=user_id)
            continue

        info = check_cookie(netflix_id, secure_id)

        if info.get("status") == "DEAD":
            mark_dead(idx, user_id=user_id)
            continue
        if info.get("status") == "ERROR":
            release_index(idx, user_id=user_id)
            time.sleep(1)
            continue
        if str(info.get("membershipStatus", "")).upper() in ("FORMER_MEMBER", "ANONYMOUS", "NEVER_MEMBER", "NON_MEMBER"):
            mark_permanent_dead(idx, user_id=user_id)
            save_cookies_for(user_id=user_id)
            continue

        # Cookie is LIVE — build cookie dict
        cookie_dict = {"NetflixId": netflix_id}
        if secure_id:
            cookie_dict["SecureNetflixId"] = secure_id
        cookie_dict.update(extras)
        cookie_dict.update(info.get("_cookies") or {})

        auth_url = info.get("authURL")
        if not auth_url or auth_url == "-":
            release_index(idx, user_id=user_id)
            logger.info(f"[TV] Cookie #{idx + 1} LIVE but no authURL - skipped")
            continue

        # Try TV login
        ok, tv_msg = tv_login_with_code(auth_url, tv_code, cookie_dict)
        release_index(idx, user_id=user_id)

        if ok:
            record_account_usage(idx, user_id=user_id)
            payload = {
                "netflix_id": netflix_id,
                "secure_id": secure_id,
                "cookie_dict": cookie_dict,
                "auth_url": auth_url,
                "_cookie_index": idx,
                "source_index": idx,
                "raw_cookie": raw,
            }
            return True, tv_msg, payload
        else:
            logger.info(f"[TV] Cookie #{idx + 1} LIVE but TV login failed: {tv_msg}")
            continue

    return False, "Không tìm thấy cookie hoạt động. Thử lại sau.", None


async def _run_tv_login(update: Update, context: ContextTypes.DEFAULT_TYPE, tv_code: str):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    tv_code = (tv_code or "").strip()
    if len(tv_code) < 6:
        await msg.reply_text("❌ Mã TV không hợp lệ (cần ít nhất 6 ký tự).")
        return

    lang = get_user_lang(user.id) or "vi"
    user_limit = DAILY_LIMIT

    # Check remaining uses
    uses_left_val = get_uses_left(user.id)
    if uses_left_val <= 0:
        await msg.reply_text(
            f"❌ Bạn đã hết lượt hôm nay.\n"
            f"⏰ Quay lại sau 00:00 để dùng lại Login TV.",
            parse_mode=ParseMode.HTML,
        )
        return

    await msg.reply_text(
        f"📺 Đang tự động tìm cookie và login TV...\n"
        f"🔑 Mã TV: <code>{escape(tv_code)}</code>\n\n"
        f"<i>Vui lòng đợi, đang kiểm tra cookies...</i>",
        parse_mode=ParseMode.HTML,
    )

    loop = asyncio.get_event_loop()
    ok, tv_msg, payload = await loop.run_in_executor(
        _executor, _find_and_tv_login, user.id, tv_code
    )

    if ok:
        # Consume use
        if consume_use(user.id, 1):
            record_use(user.id, username=user.username, first_name=user.first_name)

        user_info = f"@{user.username}" if user.username else user.first_name or str(user.id)
        logger.info(f"📺 TV LOGIN GIVEN to {user_info} (ID: {user.id})")

        await msg.reply_text(
            "📺 <b>TV LOGIN THÀNH CÔNG!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔑 Mã TV: <code>{escape(tv_code)}</code>\n"
            f"✅ {escape(str(tv_msg))}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>TV của bạn đã được đăng nhập Netflix</i>\n"
            "📌 <i>Kiểm tra TV để xác nhận</i>",
            parse_mode=ParseMode.HTML,
        )

        # Save active session
        if payload:
            payload["mode"] = "tv"
            session_id = _save_active_session(user.id, lang, payload)
            if context.job_queue:
                _schedule_feedback_prompt(context.job_queue, user.id, lang, session_id)

        uses_left_val = get_uses_left(user.id)
        try:
            await msg.reply_text(
                f"🍪 Còn lại: {uses_left_val}/{user_limit} lượt hôm nay\n"
                f"⏰ Reset lúc 00:00 đêm nay",
            )
        except Exception:
            pass
    else:
        short_err = str(tv_msg or "Unknown")
        await msg.reply_text(
            f"❌ TV Login thất bại: {escape(short_err)}\n\n"
            "💡 Thử lại sau ít phút.",
            parse_mode=ParseMode.HTML,
        )


async def cmd_tv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    if not context.args:
        await msg.reply_text(
            "📺 <b>TV LOGIN</b>\n\n"
            "Cách dùng: <code>/tv &lt;mã_TV&gt;</code>\n"
            "Ví dụ: <code>/tv ABCD1234</code>\n\n"
            "💡 Bot sẽ tự tìm cookie và đăng nhập TV cho bạn.",
            parse_mode=ParseMode.HTML,
        )
        return
    await _run_tv_login(update, context, context.args[0])


# ═══════════════════════════════════════════════════════════════════
#  Text input handler
# ═══════════════════════════════════════════════════════════════════

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text:
        return

    if bool(context.user_data.get("await_tv_code")):
        context.user_data["await_tv_code"] = False
        tv_code = msg.text.strip()
        await _run_tv_login(update, context, tv_code)
        return

    if bool(context.user_data.get("await_redeem_code")):
        context.user_data["await_redeem_code"] = False
        await msg.reply_text(
            "⚠️ Redeem code đã được gỡ. Bot hiện chỉ còn /loginlink và /tv.",
        )
        return


async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return
    count = load_cookies()
    total_stats = get_total_cookie_stats()
    await msg.reply_text(
        f"✅ Đã reload cookies!\n"
        f"🍪 Tổng: {total_stats['total']} cookies\n"
        f"✅ Còn lại: {total_stats['remaining']} cookies",
        parse_mode=ParseMode.HTML,
    )


# ═══════════════════════════════════════════════════════════════════
#  /ref command
# ═══════════════════════════════════════════════════════════════════

async def cmd_ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    user_limit = DAILY_LIMIT
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user.id}"
    ref_count = get_ref_count(user.id)
    ref_bonus = get_ref_bonus(user.id)
    total_limit = user_limit + ref_bonus

    await msg.reply_text(
        t("ref_info", lang,
          ref_link=ref_link, ref_count=ref_count,
          ref_bonus=ref_bonus, total_limit=total_limit,
          max_ref=MAX_REF_BONUS),
        parse_mode=ParseMode.HTML,
    )


# ═══════════════════════════════════════════════════════════════════
#  Admin: /msg -- Broadcast message to all users
# ═══════════════════════════════════════════════════════════════════

async def cmd_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return

    if not context.args:
        await msg.reply_text(
            "📢 <b>Cách dùng:</b>\n"
            "<code>/msg nội dung tin nhắn</code>\n\n"
            "<b>Ví dụ:</b>\n"
            "<code>/msg Bot cập nhật phiên bản mới!</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    content = " ".join(context.args)
    all_uids = get_all_user_ids()
    if not all_uids:
        await msg.reply_text("⚠️ Chưa có user nào trong hệ thống.")
        return

    await msg.reply_text(
        f"📢 Đang gửi tin nhắn tới {len(all_uids)} users...",
    )

    broadcast_text = (
        "📢 <b>THÔNG BÁO TỪ ADMIN</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{content}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    sent = 0
    failed = 0
    for uid in all_uids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=broadcast_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            sent += 1
        except Exception:
            failed += 1
        # Tránh bị rate limit bởi Telegram
        await asyncio.sleep(0.05)

    await msg.reply_text(
        f"✅ Đã gửi xong!\n"
        f"📨 Thành công: {sent}/{len(all_uids)}\n"
        f"❌ Thất bại: {failed}",
    )

# ═══════════════════════════════════════════════════════════════════
#  Admin: /notify -- Gửi thông báo duy trì server tới tất cả users
# ═══════════════════════════════════════════════════════════════════

async def cmd_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return

    all_uids = get_all_user_ids()
    if not all_uids:
        await msg.reply_text("⚠️ Chưa có user nào trong hệ thống.")
        return

    notify_text = (
        "🎬 <b>[THÔNG BÁO QUAN TRỌNG]</b>\n"
        "<b>DUY TRÌ SERVER NETFLIX FREE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ Anh em lưu ý: <b>VPS của hệ thống chỉ còn 1 ngày nữa là hết hạn.</b>\n"
        "Để tiếp tục duy trì server và giữ Netflix free cho mọi người, "
        "rất mong nhận được sự ủng hộ từ anh em 🙏\n\n"
        "💰 <b>Chi phí duy trì cực nhẹ:</b>\n"
        "👉 Chỉ <b>2.000 VND / 1 người</b>\n"
        "👉 Góp một chút là đủ giữ server chạy ổn định lâu dài\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔥 <b>CẬP NHẬT QUAN TRỌNG:</b>\n"
        "❌ Từ giờ <b>KHÔNG BÁN</b> Netflix nữa\n"
        "✅ Chuyển sang <b>SHARE FREE</b> cho mọi người\n"
        "💎 Toàn bộ đều là acc cao cấp – <b>Premium UHD</b> xịn sò\n\n"
        "⚡ <b>QUYỀN LỢI VẪN GIỮ NGUYÊN:</b>\n"
        "✅ Cookie sống tỷ lệ cao\n"
        "✅ Login nhanh, mượt\n"
        "✅ Hệ thống hoạt động 24/7\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Thông Tin Ủng Hộ:</b>\n"
        "🏦 Ngân hàng: <b>MB BANK</b>\n"
        "💳 STK: <code>081220061983</code>\n"
        "👤 Tên TK: <b>PHAM VU TUAN ANH</b>\n"
        "📝 Nội dung CK: <code>UNGHO</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "❤️ Mong anh em ủng hộ để cộng đồng vẫn có Netflix "
        "chất lượng cao dùng free lâu dài!\n\n"
        "🍿 <i>Cảm ơn anh em – Chúc mọi người xem phim vui vẻ!</i>"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❤️ Ủng Hộ Ngay", url="tg://user?id=5898054839")],
        [InlineKeyboardButton("📩 Liên hệ Admin", url="https://t.me/phamtuan812")],
    ])

    await msg.reply_text(f"📢 Đang gửi thông báo tới {len(all_uids)} users...")

    sent = 0
    failed = 0
    qr_path = os.path.join(BASE_DIR, "qr.png")
    has_qr = os.path.exists(qr_path)

    for uid in all_uids:
        try:
            if has_qr:
                with open(qr_path, "rb") as qr_file:
                    await context.bot.send_photo(
                        chat_id=uid,
                        photo=qr_file,
                        caption="💳 QR Code Thanh Toán",
                    )
            await context.bot.send_message(
                chat_id=uid,
                text=notify_text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
                disable_web_page_preview=True,
            )
            sent += 1
        except Forbidden:
            failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.1)

    await msg.reply_text(
        f"✅ Đã gửi thông báo xong!\n"
        f"📨 Thành công: {sent}/{len(all_uids)}\n"
        f"❌ Thất bại: {failed}",
    )


# ═══════════════════════════════════════════════════════════════════
#  Error handler
# ═══════════════════════════════════════════════════════════════════

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling update:", exc_info=context.error)
