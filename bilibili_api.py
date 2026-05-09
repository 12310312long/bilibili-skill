"""
B站 API helper. Uses cookies from CDP browser or Netscape cookie file.
Handles: video info, like, favorite, comment, download.
"""
import json, re, os, time, urllib.request, http.cookiejar, hashlib, functools
from urllib.parse import urlencode
from http.cookiejar import MozillaCookieJar

SESSION = None
COOKIE_FILE = os.path.expanduser("~/tmp/bilibili_cookies.txt") if os.name == "posix" else "D:/tmp/bilibili_cookies.txt"
_WBI_MIXIN_KEY = None

# WBI salt table — B站 updates this periodically. Extract from frontend JS if broken.
_WBI_SALT = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
             27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13]


@functools.lru_cache(maxsize=1)
def _get_wbi_keys():
    """Fetch img_key and sub_key from B站 nav API. Cached for session."""
    s = _get_session()
    r = s.get("https://api.bilibili.com/x/web-interface/nav")
    data = r.json()
    if data["code"] != 0:
        raise Exception(f"Failed to get wbi keys: {data['message']}")
    wbi_img = data["data"]["wbi_img"]
    # Keys are in URL filenames: .../7cd084941338484aae1ad9425b84077c.png
    img_key = wbi_img["img_url"].rsplit("/", 1)[-1].split(".")[0]
    sub_key = wbi_img["sub_url"].rsplit("/", 1)[-1].split(".")[0]
    return img_key, sub_key


def _wbi_sign(params):
    """Add w_rid and wts to params dict. Mutates and returns params."""
    global _WBI_MIXIN_KEY
    if _WBI_MIXIN_KEY is None:
        img_key, sub_key = _get_wbi_keys()
        combined = img_key + sub_key
        _WBI_MIXIN_KEY = "".join(combined[i] for i in _WBI_SALT if i < len(combined))
    params["wts"] = int(time.time())
    # Sort keys, form query string, append mixin key, MD5
    sorted_params = sorted(params.items(), key=lambda x: x[0])
    query = urlencode(sorted_params)
    params["w_rid"] = hashlib.md5((query + _WBI_MIXIN_KEY).encode()).hexdigest()
    return params

def _get_session():
    """Get or create a requests session with B站 cookies."""
    global SESSION
    if SESSION:
        return SESSION
    import requests
    SESSION = requests.Session()
    SESSION.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.bilibili.com/",
    })
    # Try loading cookies from file (Netscape format via CDP export)
    # Check multiple possible locations
    cookie_paths = [
        COOKIE_FILE,
        "D:/tmp/bilibili_cookies.txt",
        "/tmp/bilibili_cookies.txt",
    ]
    for cp in cookie_paths:
        if os.path.exists(cp):
            load_cookies_from_file(cp)
            break
    return SESSION


def _csrf():
    """Get CSRF token from cookies."""
    s = _get_session()
    for c in s.cookies:
        if c.name == "bili_jct":
            return c.value
    return ""


def _get_cookies_dict():
    """Export cookies as dict for yt-dlp."""
    s = _get_session()
    return {c.name: c.value for c in s.cookies}


def export_cookies_for_ytdlp(path=None):
    """Export cookies to Netscape format for yt-dlp."""
    if path is None:
        path = COOKIE_FILE
    s = _get_session()
    cj = MozillaCookieJar()
    for c in s.cookies:
        cj.set_cookie(c)
    cj.save(path, ignore_discard=True, ignore_expires=True)
    return path


def ensure_cdp_browser():
    """Ensure a CDP-enabled browser with the user's real profile is running.

    Launches Edge with --remote-debugging-port=9222 using the default user
    profile (where B站 login cookies live), then starts the CDP proxy.
    Safe to call even if the proxy is already running.
    """
    import subprocess, os, time, json

    # Check if CDP proxy is already running AND connected to a browser
    try:
        r = subprocess.run(
            ["curl", "-s", "--connect-timeout", "2", "http://localhost:3456/health"],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=5
        )
        if r.returncode == 0:
            try:
                health = json.loads(r.stdout)
                if health.get("connected") and health.get("chromePort"):
                    return  # proxy running and connected
            except json.JSONDecodeError:
                pass
    except Exception:
        pass

    local_appdata = os.environ.get("LOCALAPPDATA", "")
    user_data = os.path.join(local_appdata, "Microsoft", "Edge", "User Data")
    port_file = os.path.join(user_data, "DevToolsActivePort")

    # Check if CDP browser is already accessible on port 9222
    cdp_ready = False
    try:
        r = subprocess.run(
            ["curl", "-s", "--connect-timeout", "2", "http://localhost:9222/json/version"],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=5
        )
        if r.returncode == 0 and "Browser" in r.stdout:
            cdp_ready = True
    except Exception:
        pass

    if not cdp_ready:
        # Kill existing Edge processes (PowerShell is more reliable than taskkill)
        subprocess.run(["powershell", "-Command",
            "Get-Process -Name '*edge*' -ErrorAction SilentlyContinue | Stop-Process -Force"],
            capture_output=True, timeout=15)
        time.sleep(5)

        # Remove old DevToolsActivePort to avoid stale reads
        try:
            os.remove(port_file)
        except OSError:
            pass

        # Find Edge executable
        edge_paths = [
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        ]
        edge_exe = None
        for p in edge_paths:
            if os.path.exists(p):
                edge_exe = p
                break
        if not edge_exe:
            raise Exception("Edge browser not found")

        # Launch Edge with default profile + CDP
        subprocess.Popen(
            [edge_exe, "--remote-debugging-port=9222", "https://www.bilibili.com"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        # Wait for Edge CDP to become ready
        for _ in range(10):
            time.sleep(2)
            try:
                r = subprocess.run(
                    ["curl", "-s", "--connect-timeout", "2", "http://localhost:9222/json/version"],
                    capture_output=True, text=True, encoding='utf-8', errors='replace',
                    timeout=5
                )
                if r.returncode == 0 and "Browser" in r.stdout:
                    cdp_ready = True
                    break
            except Exception:
                pass

        if not cdp_ready:
            raise Exception("Edge failed to start with CDP port 9222")

    # Ensure DevToolsActivePort file exists for CDP proxy discovery
    if not os.path.exists(port_file):
        try:
            r = subprocess.run(
                ["curl", "-s", "http://localhost:9222/json/version"],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=5
            )
            ver = json.loads(r.stdout)
            ws_url = ver.get("webSocketDebuggerUrl", "")
            # Extract UUID path from ws://127.0.0.1:9222/devtools/browser/<uuid>
            import re
            m = re.search(r'/devtools/browser/([\w-]+)', ws_url)
            if m:
                os.makedirs(user_data, exist_ok=True)
                with open(port_file, 'w') as f:
                    f.write(f"9222\n/devtools/browser/{m.group(1)}")
        except Exception:
            pass  # CDP proxy can still scan port 9222 without this file

    # Kill any stale CDP proxy (not connected) and restart
    try:
        r = subprocess.run(
            ["curl", "-s", "--connect-timeout", "2", "http://localhost:3456/health"],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=5
        )
        if r.returncode == 0:
            health = json.loads(r.stdout)
            if not health.get("connected"):
                # Proxy is running but not connected — kill it
                subprocess.run(["powershell", "-Command",
                    "Get-NetTCPConnection -LocalPort 3456 -ErrorAction SilentlyContinue | "
                    "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"],
                    capture_output=True, timeout=10)
                time.sleep(2)
    except Exception:
        pass

    # Check again if proxy is healthy
    try:
        r = subprocess.run(
            ["curl", "-s", "--connect-timeout", "2", "http://localhost:3456/health"],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=5
        )
        if r.returncode == 0:
            health = json.loads(r.stdout)
            if health.get("connected"):
                return  # healthy proxy already running
    except Exception:
        pass

    # Start CDP proxy
    script_dir = os.path.dirname(os.path.abspath(__file__))
    proxy_path = os.path.normpath(os.path.join(
        script_dir, "..", "web-access", "scripts", "cdp-proxy.mjs"))
    if not os.path.exists(proxy_path):
        raise Exception(f"CDP proxy not found at {proxy_path}")

    subprocess.Popen(
        ["node", proxy_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(4)

    # Verify proxy is responding and connected
    try:
        r = subprocess.run(
            ["curl", "-s", "--connect-timeout", "3", "http://localhost:3456/health"],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=10
        )
        if r.returncode != 0:
            raise Exception("CDP proxy failed to start")
        health = json.loads(r.stdout)
        if not health.get("connected"):
            # Give it another moment to connect, then check again
            time.sleep(3)
            r = subprocess.run(
                ["curl", "-s", "--connect-timeout", "3", "http://localhost:3456/health"],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=10
            )
            health = json.loads(r.stdout)
            if not health.get("connected"):
                raise Exception("CDP proxy started but failed to connect to browser")
    except subprocess.TimeoutExpired:
        raise Exception("CDP proxy startup timed out")


def load_cookies_from_cdp():
    """Extract B站 cookies from CDP browser and save to file.
    Automatically ensures CDP browser and proxy are running.
    """
    import subprocess

    ensure_cdp_browser()

    # Find a bilibili tab
    result = subprocess.run(
        ["curl", "-s", "http://localhost:3456/targets"],
        capture_output=True, text=True, encoding='utf-8', errors='replace'
    )
    try:
        targets = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("No CDP targets found. Is proxy running?")
        return None

    bili_target = None
    for t in targets:
        if "bilibili.com" in t.get("url", ""):
            bili_target = t.get("targetId") or t.get("id")
            break

    if not bili_target:
        print("No bilibili tab found. Open one in your browser first.")
        return None

    # Get ALL cookies via CDP Network.getCookies (includes HttpOnly like SESSDATA)
    resp = subprocess.run(
        ["curl", "-s", f"http://localhost:3456/cookies?target={bili_target}"],
        capture_output=True, text=True, encoding='utf-8', errors='replace'
    )
    try:
        cookies = json.loads(resp.stdout)
    except json.JSONDecodeError:
        print("Failed to parse cookies from CDP")
        return None

    if not cookies:
        print("No cookies found in bilibili tab. Are you logged in?")
        return None

    # Build Netscape cookie jar from CDP cookie objects
    cj = MozillaCookieJar()
    from http.cookiejar import Cookie
    for c in cookies:
        expires = c.get("expires", 0)
        if expires and expires < 0:
            expires = None  # session cookie
        cookie = Cookie(
            version=0, name=c.get("name", ""), value=c.get("value", ""),
            port=None, port_specified=False,
            domain=c.get("domain", ".bilibili.com"), domain_specified=True,
            domain_initial_dot=c.get("domain", "").startswith("."),
            path=c.get("path", "/"), path_specified=True,
            secure=c.get("secure", False), expires=expires,
            discard=(expires is None), comment=None, comment_url=None,
            rest={"httpOnly": c.get("httpOnly", False)}, rfc2109=False
        )
        cj.set_cookie(cookie)

    cj.save(COOKIE_FILE, ignore_discard=True, ignore_expires=True)
    # Also reload into session
    load_cookies_from_file(COOKIE_FILE)

    # Verify key auth cookie is present
    s = _get_session()
    has_dedeuserid = any(c.name == "DedeUserID" for c in s.cookies)
    if not has_dedeuserid:
        print("WARNING: DedeUserID cookie not found. You may not be logged into B站.")

    print(f"Cookies saved to {COOKIE_FILE}")
    return COOKIE_FILE


def load_cookies_from_file(path=None):
    """Load cookies from Netscape/EFF format file into session.
    Supports both MozillaCookieJar format and raw tab-separated cookies.
    """
    if path is None:
        path = COOKIE_FILE
    s = _get_session()
    try:
        with open(path) as f:
            content = f.read()
        # Try MozillaCookieJar first
        if content.startswith("# Netscape HTTP Cookie File") or content.startswith("# HTTP Cookie File"):
            from io import StringIO
            cj = MozillaCookieJar()
            cj._really_load(StringIO(content), "", ignore_discard=True, ignore_expires=True)
            for c in cj:
                s.cookies.set(c.name, c.value, domain=c.domain, path=c.path or "/")
            return True
        # Manual parse: tab-separated Netscape format
        for line in content.strip().split("\n"):
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain, _, path, _, expires, name, value = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], parts[6]
                s.cookies.set(name, value, domain=domain, path=path)
        return True
    except Exception as e:
        print(f"Failed to load cookies: {e}")
        return False


def video_info(bvid=None, aid=None):
    """Get video info. Returns dict with title, aid, bvid, cid, duration, etc."""
    s = _get_session()
    if bvid:
        params = {"bvid": bvid}
    elif aid:
        params = {"aid": aid}
    else:
        raise ValueError("Need bvid or aid")

    r = s.get("https://api.bilibili.com/x/web-interface/view", params=params)
    data = r.json()
    if data["code"] != 0:
        raise Exception(f"API error: {data['message']}")
    return data["data"]


def like_video(bvid=None, aid=None, like=True):
    """Like (or unlike) a video. Returns True on success."""
    if bvid:
        info = video_info(bvid=bvid)
        aid = info["aid"]
    s = _get_session()
    csrf = _csrf()
    if not csrf:
        raise Exception("No CSRF token. Load cookies first.")

    r = s.post("https://api.bilibili.com/x/web-interface/archive/like", data={
        "aid": aid,
        "like": 1 if like else 2,
        "csrf": csrf,
    })
    data = r.json()
    if data["code"] != 0:
        raise Exception(f"Like failed: {data['message']}")
    return True


def favorite_video(bvid=None, aid=None, add_media_ids=None):
    """Add video to favorites. add_media_ids: list of folder IDs (default=[1] for default folder).
    Returns True on success. To get folder list, use favorite_folders().
    """
    if add_media_ids is None:
        add_media_ids = [1]  # 默认收藏夹

    if bvid:
        info = video_info(bvid=bvid)
        aid = info["aid"]

    s = _get_session()
    csrf = _csrf()
    if not csrf:
        raise Exception("No CSRF token. Load cookies first.")

    r = s.post("https://api.bilibili.com/x/v3/fav/resource/deal", data={
        "rid": aid,
        "type": 2,
        "add_media_ids": ",".join(str(f) for f in add_media_ids),
        "csrf": csrf,
    })
    data = r.json()
    if data["code"] != 0:
        raise Exception(f"Favorite failed: {data['message']}")
    return True


def favorite_folders():
    """Get list of favorite folders for current user."""
    s = _get_session()
    r = s.get("https://api.bilibili.com/x/v3/fav/folder/created/list-all")
    data = r.json()
    if data["code"] != 0:
        raise Exception(f"API error: {data['message']}")
    folders = []
    for f in data["data"]["list"]:
        folders.append({
            "id": f["id"],
            "title": f["title"],
            "media_count": f["media_count"],
        })
    return folders


def like_and_favorite_video(bvid):
    """Like AND favorite a video in one shot. Uses default folder."""
    info = video_info(bvid=bvid)
    aid = info["aid"]
    like_video(aid=aid)
    favorite_video(aid=aid)
    return {"aid": aid, "title": info["title"], "bvid": bvid}


def post_comment(bvid=None, aid=None, message="", root=None, parent=None):
    """Post a comment on a video.
    root: root comment ID (for replying to a comment thread)
    parent: parent comment ID (for replying to a specific comment)
    """
    if bvid:
        info = video_info(bvid=bvid)
        aid = info["aid"]

    s = _get_session()
    csrf = _csrf()
    if not csrf:
        raise Exception("No CSRF token. Load cookies first.")

    data = {
        "oid": aid,
        "type": 1,
        "message": message,
        "plat": 1,
        "csrf": csrf,
    }
    if root:
        data["root"] = root
    if parent:
        data["parent"] = parent

    r = s.post("https://api.bilibili.com/x/v2/reply/add", data=data)
    resp = r.json()
    if resp["code"] != 0:
        raise Exception(f"Comment failed: {resp['message']}")
    return resp["data"]


def get_comments(bvid=None, aid=None, page=1, sort=1):
    """Get comments for a video.
    sort: 1=按热度, 0=按时间, 2=按时间倒序
    Returns list of comments with rpid, mid, message, etc.
    """
    if bvid:
        info = video_info(bvid=bvid)
        oid = info["aid"]
        aid = info["aid"]
    elif aid:
        oid = aid
    else:
        raise ValueError("Need bvid or aid")

    s = _get_session()
    r = s.get("https://api.bilibili.com/x/v2/reply", params={
        "oid": oid,
        "type": 1,
        "pn": page,
        "sort": sort,
    })
    data = r.json()
    if data["code"] != 0:
        raise Exception(f"API error: {data['message']}")

    comments = []
    for reply in data["data"].get("replies", []):
        comments.append({
            "rpid": reply["rpid"],
            "mid": reply["mid"],
            "uname": reply["member"]["uname"],
            "message": reply["content"]["message"],
            "ctime": reply["ctime"],
            "like": reply["like"],
            "rcount": reply["rcount"],
        })
    return comments


def download_video(bvid, output_dir=".", output_name=None):
    """Download a B站 video. Uses __playinfo__ via CDP for charged videos.
    For regular videos, falls back to yt-dlp.

    Requires CDP proxy (node cdp-proxy.mjs) and at least one bilibili tab open.

    Returns: path to downloaded file.
    """
    import subprocess, urllib.request

    info = video_info(bvid=bvid)
    title = info["title"]
    safe_title = re.sub(r'[\\/:*?"<>|]', '', title)

    if output_name is None:
        output_name = safe_title

    # Try CDP __playinfo__ approach (works for charged videos too)
    result = subprocess.run(
        ["curl", "-s", "http://localhost:3456/targets"],
        capture_output=True, text=True, encoding='utf-8', errors='replace'
    )
    targets = json.loads(result.stdout) if result.stdout.strip() else []

    bili_target = None
    for t in targets:
        if "bilibili.com" in t.get("url", ""):
            bili_target = t.get("targetId") or t.get("id")
            break

    if not bili_target:
        print("No bilibili tab. Opening one...")
        resp = subprocess.run(
            ["curl", "-s", f"http://localhost:3456/new?url=https://www.bilibili.com/video/{bvid}"],
            capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        try:
            new_tab = json.loads(resp.stdout)
            bili_target = new_tab.get("targetId") or new_tab.get("id")
            time.sleep(5)  # Wait for page load
        except Exception:
            raise Exception("Failed to open bilibili tab. Is CDP proxy running?")

    # Extract playinfo
    print(f"Extracting stream URLs for {bvid}...")
    js_code = """
    (function() {
        try {
            var p = window.__playinfo__;
            if (!p) return 'NO_PLAYINFO';
            return JSON.stringify({
                video: p.data.dash.video.map(function(v) {
                    return {url: v.baseUrl || v.base_url, quality: v.id, codecs: v.codecs}
                }),
                audio: p.data.dash.audio.map(function(a) {
                    return {url: a.baseUrl || a.base_url, quality: a.id, codecs: a.codecs}
                }),
                duration: p.data.dash.duration
            });
        } catch(e) { return 'ERROR: ' + e.message; }
    })()
    """

    resp = subprocess.run(
        ["curl", "-s", "-X", "POST",
         f"http://localhost:3456/eval?target={bili_target}",
         "-d", js_code],
        capture_output=True, text=True, encoding='utf-8', errors='replace'
    )

    try:
        playinfo = json.loads(resp.stdout.strip())
    except json.JSONDecodeError:
        raise Exception(f"Failed to get playinfo. Is video page loaded?\nResponse: {resp.stdout[:200]}")

    if "video" not in playinfo:
        raise Exception(f"No video streams in playinfo: {playinfo}")

    # Download best video + audio
    best_video = playinfo["video"][0]["url"]
    best_audio = playinfo["audio"][0]["url"]

    v_path = os.path.join(output_dir, f"_v_{safe_title}.m4s")
    a_path = os.path.join(output_dir, f"_a_{safe_title}.m4s")
    out_path = os.path.join(output_dir, f"{output_name}.mp4")

    print(f"Downloading video stream...")
    s = _get_session()
    headers = {"Referer": f"https://www.bilibili.com/video/{bvid}"}

    urllib.request.urlretrieve(best_video, v_path)

    print(f"Downloading audio stream...")
    urllib.request.urlretrieve(best_audio, a_path)

    print(f"Merging with ffmpeg...")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", v_path, "-i", a_path,
        "-c", "copy", out_path
    ], capture_output=True)

    os.remove(v_path)
    os.remove(a_path)

    file_size = os.path.getsize(out_path)
    print(f"Downloaded: {out_path} ({file_size/1e6:.0f} MB)")
    return out_path


def user_info(uid):
    """Get B站 user info by UID."""
    s = _get_session()
    params = _wbi_sign({"mid": str(uid)})
    r = s.get("https://api.bilibili.com/x/space/wbi/acc/info", params=params)
    data = r.json()
    if data["code"] != 0:
        raise Exception(f"API error: {data['message']}")
    return data["data"]


def _dev_id():
    """Generate a consistent device ID from UID."""
    import hashlib
    s = _get_session()
    uid = "0"
    for c in s.cookies:
        if c.name == "DedeUserID":
            uid = c.value
            break
    raw = hashlib.md5(f"bili_dev_{uid}_2024".encode()).hexdigest().upper()
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def send_private_message(receiver_id, message, from_firework=0):
    """Send a private message to a B站 user.

    Args:
        receiver_id: target user UID (mid)
        message: text content to send
        from_firework: 0=normal, 1=bypass one-message limit for new contacts

    Returns: API response dict with code=0 on success.
    """
    s = _get_session()
    csrf = _csrf()
    if not csrf:
        raise Exception("No CSRF token. Load cookies first.")

    my_uid = "0"
    for c in s.cookies:
        if c.name == "DedeUserID":
            my_uid = c.value
            break
    if my_uid == "0":
        raise Exception("Cannot determine your UID. Are you logged in?")

    dev = _dev_id()
    ts = int(time.time())

    # Build query params for WBI signing
    query_params = {
        "w_sender_uid": my_uid,
        "w_receiver_id": str(receiver_id),
        "w_dev_id": dev,
    }
    signed = _wbi_sign(query_params)

    # Build form body
    body = {
        "msg[sender_uid]": my_uid,
        "msg[receiver_type]": "1",
        "msg[receiver_id]": str(receiver_id),
        "msg[msg_type]": "1",
        "msg[msg_status]": "0",
        "msg[content]": json.dumps({"content": message}, ensure_ascii=False),
        "msg[new_face_version]": "0",
        "msg[canal_token]": "",
        "msg[dev_id]": dev,
        "msg[timestamp]": str(ts),
        "from_firework": str(from_firework),
        "build": "0",
        "mobi_app": "web",
        "csrf": csrf,
    }

    r = s.post(
        "https://api.vc.bilibili.com/web_im/v1/web_im/send_msg",
        params=signed,
        data=body,
    )
    resp = r.json()
    if resp["code"] != 0:
        raise Exception(f"发送私信失败: {resp.get('message', '未知错误')}")
    return resp["data"]


def user_videos(uid, page=1, page_size=30):
    """Get user's video list."""
    s = _get_session()
    params = _wbi_sign({"mid": str(uid), "pn": str(page), "ps": str(page_size)})
    r = s.get("https://api.bilibili.com/x/space/wbi/arc/search", params=params)
    data = r.json()
    if data["code"] != 0:
        raise Exception(f"API error: {data['message']}")
    videos = []
    for v in data["data"]["list"].get("vlist", data["data"]["list"]):
        videos.append({
            "bvid": v.get("bvid", ""),
            "aid": v.get("aid", 0),
            "title": v.get("title", ""),
            "play": v.get("play", 0),
            "created": v.get("created", 0),
            "length": v.get("length", ""),
            "description": v.get("description", ""),
        })
    return videos


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if len(sys.argv) < 2:
        print("Usage: python bilibili_api.py <command> [args]")
        print("Commands: info <bvid>, like <bvid>, fav <bvid>, like-fav <bvid>,")
        print("  comments <bvid>, download <bvid>, user <uid>, user-videos <uid>")
        print("  send-msg <uid> <message>, load-cookies (from CDP), export-cookies [path]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "info":
        print(json.dumps(video_info(bvid=sys.argv[2]), ensure_ascii=False, indent=2))
    elif cmd == "like":
        print(like_video(bvid=sys.argv[2]))
    elif cmd == "fav":
        print(favorite_video(bvid=sys.argv[2]))
    elif cmd == "like-fav":
        print(json.dumps(like_and_favorite_video(sys.argv[2]), ensure_ascii=False, indent=2))
    elif cmd == "comments":
        for c in get_comments(bvid=sys.argv[2]):
            print(f"[{c['uname']}] {c['message'][:100]} | {c['like']}赞")
    elif cmd == "download":
        download_video(sys.argv[2], output_dir=".")
    elif cmd == "user":
        print(json.dumps(user_info(sys.argv[2]), ensure_ascii=False, indent=2))
    elif cmd == "user-videos":
        for v in user_videos(sys.argv[2]):
            print(f"[{v['bvid']}] {v['title']} | {v['play']}播放")
    elif cmd == "send-msg":
        if len(sys.argv) < 4:
            print("Usage: python bilibili_api.py send-msg <uid> <message>")
            sys.exit(1)
        uid = sys.argv[2]
        msg = sys.argv[3]
        print(f"Sending to {uid}: {msg}")
        send_private_message(uid, msg)
        print("Sent!")
    elif cmd == "load-cookies":
        load_cookies_from_cdp()
    elif cmd == "export-cookies":
        path = sys.argv[2] if len(sys.argv) > 2 else None
        print(export_cookies_for_ytdlp(path))
