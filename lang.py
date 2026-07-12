"""
Language strings — Vietnamese & English
"""

STRINGS = {
    "vi": {
        # ── Language picker ──
        "lang_prompt": "🌐 Chọn ngôn ngữ / Choose language:",
        "lang_vi": "🇻🇳 Tiếng Việt",
        "lang_en": "🇬🇧 English",
        "lang_set": "✅ Đã chọn Tiếng Việt!",

        # ── Welcome ──
        "welcome": (
            "🎬 <b>NETFLIX LOGIN BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "👋 Chào <b>{name}</b>!\n\n"
            "🔗 Lấy link đăng nhập Netflix nhanh\n"
            "📺 Hỗ trợ login TV bằng mã TV\n"
            "📌 Yêu cầu: Tham gia nhóm @{group}\n\n"
            "💡 <i>Chọn một nút bên dưới để tiếp tục</i>"
        ),

        # ── Buttons ──
        "btn_get": "🎁 Lấy Acc",
        "btn_stats": "📊 Thống Kê",
        "btn_ref": "🔗 Giới Thiệu",
        "btn_help": "❓ Hướng Dẫn",
        "btn_lang": "🌐 Ngôn Ngữ",
        "btn_tv": "📺 Login TV",
        "btn_redeem": "🎁 Redeem Code",
        "btn_back": "🔙 Quay Lại",
        "btn_join": "📢 Tham Gia Nhóm",
        "btn_vip": "💎 VIP",
        "btn_loginlink": "🔗 Lấy Link",
        "btn_reload": "🔄 Reload Cookies",

        # ── Get account ──
        "checking": "⏳ Đang tìm tài khoản LIVE...\n\n<i>Vui lòng đợi, đang kiểm tra cookies...</i>",
        "no_acc": "😔 Không tìm thấy tài khoản LIVE.\n\nVui lòng thử lại sau hoặc liên hệ Admin.",
        "join_first": "⚠️ Bạn cần tham gia nhóm @{group} trước!",
        "daily_limit": "⏳ Bạn đã hết lượt hôm nay ({used}/{limit}).\n\n🔄 Reset sau: <b>{reset}</b>\n🔗 Giới thiệu bạn bè để có thêm lượt!",

        # ── Stats ──
        "stats": (
            "📊 <b>Trạng thái của bạn</b>\n"
            "────────────────────────\n\n"
            "👤 User: <b>{name}</b>\n"
            "📅 Hôm nay: {today}\n"
            "🍪 Đã nhận: {used}/{limit}\n"
            "✅ Còn lại: {remaining} lượt\n"
            "⏰ Reset sau: {reset}\n\n"
            "🔥 Chuỗi ngày: {streak} ngày liên tục (bonus: +{streak_bonus})\n"
            "────────────────────────\n"
            "🔗 Muốn thêm lượt? Giới thiệu bạn bè!\n"
            "• Mỗi 1 ref = +1 lượt/ngày (tối đa +{max_ref})\n"
            "• Ref hiện tại: {ref_count} (bonus: +{ref_bonus})\n"
        ),

        # ── Referral ──
        "ref_info": (
            "🔗 <b>GIỚI THIỆU BẠN BÈ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📎 Link giới thiệu của bạn:\n"
            "<code>{ref_link}</code>\n\n"
            "👥 Đã giới thiệu: <b>{ref_count}</b> người\n"
            "🎁 Bonus lượt/ngày: <b>+{ref_bonus}</b>\n"
            "📊 Tổng lượt/ngày: <b>{total_limit}</b>\n\n"
            "────────────────────────\n"
            "💡 <i>Gửi link cho bạn bè. Khi họ nhấn /start qua link,\n"
            "bạn sẽ nhận thêm +1 lượt/ngày (tối đa +{max_ref})</i>"
        ),
        "ref_new": "🎉 {name} đã giới thiệu bạn! Chào mừng!",
        "ref_got": "🔔 Bạn được +1 lượt/ngày! ({ref_count}/{max_ref}) nhờ giới thiệu {name}.",

        # ── Help ──
        "help": (
            "❓ <b>HƯỚNG DẪN SỬ DỤNG</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "1️⃣ Tham gia nhóm @{group}\n"
            "2️⃣ Nhấn 🎁 Lấy Acc\n"
            "3️⃣ Copy link login và mở trên trình duyệt\n"
            "4️⃣ Mỗi ngày được {limit} lượt (+ bonus ref)\n\n"
            "🧭 <b>Lệnh nhanh:</b>\n"
            "• <code>/start</code> mở menu\n"
            "• <code>/ref</code> lấy link giới thiệu\n"
            "• <code>/tv &lt;maTV&gt;</code> login TV tự động\n"
            "• <code>/addluot</code> cộng lượt (Admin)\n"
            "• <code>/addcode &lt;code&gt; &lt;luot&gt; [claims]</code> tạo gift code (Admin)\n"
            "• <code>/reload</code> reload cookies (Admin)\n"
            "• Bot: @{bot}\n\n"
            "📘 <b>Hướng dẫn sử dụng Cookie Netflix Premium</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>Bước 1 — Cài đặt Cookie Editor</b>\n"
            "└ Tải tiện ích mở rộng Cookie Editor cho Chrome/Edge: "
            "<a href='https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm'>Cookie Editor</a>.\n\n"
            "<b>Bước 2 — Truy cập Netflix</b>\n"
            "└ Mở trình duyệt và vào <a href='https://www.netflix.com/'>netflix.com</a>.\n"
            "└ Nếu đang đăng nhập tài khoản khác, hãy đăng xuất trước.\n\n"
            "<b>Bước 3 — Mở Cookie Editor</b>\n"
            "└ Nhấn biểu tượng Extensions trên thanh công cụ.\n"
            "└ Chọn Cookie Editor từ danh sách.\n\n"
            "<b>Bước 4 — Xóa cookie cũ</b>\n"
            "└ Trong Cookie Editor, nhấn Delete All.\n"
            "└ Bước này giúp tránh xung đột cookie Netflix cũ.\n\n"
            "<b>Bước 5 — Import cookie mới</b>\n"
            "└ Nhấn Import.\n"
            "└ Mở file <code>cookie.txt</code> bot đã gửi, copy toàn bộ nội dung.\n"
            "└ Dán vào ô Import và xác nhận.\n\n"
            "<b>Bước 6 — Hoàn tất</b>\n"
            "└ Nhấn F5 hoặc tải lại trang Netflix.\n"
            "└ Bạn sẽ được đăng nhập vào tài khoản Premium.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚠️ <b>Lưu ý quan trọng:</b>\n"
            "• Cookie có thể hết hạn bất cứ lúc nào.\n"
            "• Không thay đổi mật khẩu hoặc thông tin tài khoản.\n"
            "• Nên dùng chế độ ẩn danh để an toàn hơn.\n"
            "• Nếu cookie không hoạt động, hãy bấm 🎁 Lấy Acc để lấy cookie mới.\n\n"
            "📌 <b>Lưu ý:</b>\n"
            "• Link login có hiệu lực ~1 giờ\n"
            "• Không chia sẻ tài khoản cho người khác\n"
            "• Giới thiệu bạn bè để có thêm lượt\n\n"
            "📩 Gặp vấn đề? Liên hệ <a href='tg://user?id=5898054839'>Admin</a>"
        ),

        # ── VIP Info ──
        "vip_offer": (
            "💎 <b>QUYỀN LỢI VIP</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⭐ <b>5 lượt lấy acc Premium/ngày</b>\n"
            "🛡 Bảo hành loginlink trong 24h\n"
            "🎯 Cookie Netflix Premium chất lượng cao\n"
            "📞 Hỗ trợ đăng nhập trên các thiết bị\n"
            "💰 Hoàn tiền nếu không khắc phục được\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📩 Liên hệ Admin để nâng cấp VIP:\n"
            "<a href='tg://user?id=5898054839'>Admin</a>\n\n"
            "👉 Bot: @{bot}"
        ),

        # ── Cookie stats ──
        "cookie_stats": (
            "📊 <b>THỐNG KÊ BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🍪 Cookies: {remaining}/{total}\n"
            "👥 Tổng users: {users}\n"
        ),

        # ── Account format ──
        "acc_header": "🎁 <b>NETFLIX ACCOUNT</b>",
        "acc_footer": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Link login có hiệu lực ~1 giờ</i>\n"
            "📩 <i>Gặp vấn đề? Liên hệ</i> <a href='tg://user?id=5898054839'>Admin</a>"
        ),

        # ── Admin ──
        "reload_ok": "✅ Đã reload {count} cookies!",
        "reload_fail": "❌ Reload thất bại!",
        "not_admin": "⛔ Bạn không phải Admin.",
    },

    "en": {
        # ── Language picker ──
        "lang_prompt": "🌐 Chọn ngôn ngữ / Choose language:",
        "lang_vi": "🇻🇳 Tiếng Việt",
        "lang_en": "🇬🇧 English",
        "lang_set": "✅ Language set to English!",

        # ── Welcome ──
        "welcome": (
            "🎬 <b>NETFLIX LOGIN BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "👋 Hello <b>{name}</b>!\n\n"
            "🔗 Get a Netflix login link quickly\n"
            "📺 Use your TV code for TV login\n"
            "📌 Required: Join group @{group}\n\n"
            "💡 <i>Choose an option below to continue</i>"
        ),

        # ── Buttons ──
        "btn_get": "🎁 Get Acc",
        "btn_stats": "📊 Stats",
        "btn_ref": "🔗 Referral",
        "btn_help": "❓ Help",
        "btn_lang": "🌐 Language",
        "btn_tv": "📺 TV Login",
        "btn_redeem": "🎁 Redeem Code",
        "btn_back": "🔙 Back",
        "btn_join": "📢 Join Group",
        "btn_vip": "💎 VIP",
        "btn_loginlink": "🔗 Get Link",
        "btn_reload": "🔄 Reload Cookies",

        # ── Get account ──
        "checking": "⏳ Finding a LIVE account...\n\n<i>Please wait, checking cookies...</i>",
        "no_acc": "😔 No LIVE account found.\n\nPlease try again later or contact Admin.",
        "join_first": "⚠️ You must join @{group} first!",
        "daily_limit": "⏳ Daily limit reached ({used}/{limit}).\n\n🔄 Resets in: <b>{reset}</b>\n🔗 Refer friends for more uses!",

        # ── Stats ──
        "stats": (
            "📊 <b>Your Status</b>\n"
            "────────────────────────\n\n"
            "👤 User: <b>{name}</b>\n"
            "📅 Today: {today}\n"
            "🍪 Used: {used}/{limit}\n"
            "✅ Remaining: {remaining} uses\n"
            "⏰ Resets in: {reset}\n\n"
            "🔥 Streak: {streak} days (bonus: +{streak_bonus})\n"
            "────────────────────────\n"
            "🔗 Want more uses? Refer friends!\n"
            "• Each ref = +1 use/day (max +{max_ref})\n"
            "• Current refs: {ref_count} (bonus: +{ref_bonus})\n"
        ),

        # ── Referral ──
        "ref_info": (
            "🔗 <b>REFERRALS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📎 Your referral link:\n"
            "<code>{ref_link}</code>\n\n"
            "👥 Referred: <b>{ref_count}</b> people\n"
            "🎁 Bonus uses/day: <b>+{ref_bonus}</b>\n"
            "📊 Total uses/day: <b>{total_limit}</b>\n\n"
            "────────────────────────\n"
            "💡 <i>Share the link with friends. When they /start via your link,\n"
            "you get +1 use/day (max +{max_ref})</i>"
        ),
        "ref_new": "🎉 {name} referred you! Welcome!",
        "ref_got": "🔔 You got +1 use/day! ({ref_count}/{max_ref}) thanks to {name}.",

        # ── Help ──
        "help": (
            "❓ <b>HOW TO USE</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "1️⃣ Join group @{group}\n"
            "2️⃣ Press 🎁 Get Acc\n"
            "3️⃣ Copy login link and open in browser\n"
            "4️⃣ {limit} uses per day (+ ref bonus)\n\n"
            "🧭 <b>Quick Commands:</b>\n"
            "• <code>/start</code> open menu\n"
            "• <code>/ref</code> get referral link\n"
            "• <code>/tv &lt;TVCode&gt;</code> auto TV login\n"
            "• <code>/addluot</code> add uses (Admin)\n"
            "• <code>/addcode &lt;code&gt; &lt;uses&gt; [claims]</code> create gift code (Admin)\n"
            "• <code>/reload</code> reload cookies (Admin)\n"
            "• Bot: @{bot}\n\n"
            "📌 <b>Notes:</b>\n"
            "• Login link valid for ~1 hour\n"
            "• Don't share the account\n"
            "• Refer friends for more uses\n\n"
            "📩 Issues? Contact <a href='tg://user?id=5898054839'>Admin</a>"
        ),

        # -- VIP Info --
        "vip_offer": (
            "💎 <b>VIP BENEFITS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⭐ <b>5 Premium accounts per day</b>\n"
            "🛡 Login link warranty for 24h\n"
            "🎯 High-quality Netflix Premium cookies\n"
            "📱 Login support on all devices\n"
            "💰 Refund if issue cannot be resolved\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📩 Contact Admin to upgrade VIP:\n"
            "<a href='tg://user?id=5898054839'>Admin</a>\n\n"
            "👉 Bot: @{bot}"
        ),

        # ── Cookie stats ──
        "cookie_stats": (
            "📊 <b>BOT STATS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🍪 Cookies: {remaining}/{total}\n"
            "👥 Total users: {users}\n"
        ),

        # ── Account format ──
        "acc_header": "🎁 <b>NETFLIX ACCOUNT</b>",
        "acc_footer": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Login link valid for ~1 hour</i>\n"
            "📩 <i>Issues?</i> <a href='tg://user?id=5898054839'>Admin</a>"
        ),

        # ── Admin ──
        "reload_ok": "✅ Reloaded {count} cookies!",
        "reload_fail": "❌ Reload failed!",
        "not_admin": "⛔ You are not an Admin.",
    },
}


def t(key, lang="vi", **kwargs):
    """Get translated string."""
    s = STRINGS.get(lang, STRINGS["vi"]).get(key, STRINGS["vi"].get(key, key))
    if kwargs:
        try:
            return s.format(**kwargs)
        except (KeyError, IndexError):
            return s
    return s
