import os
import logging
import sys
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from flask import Flask, request, jsonify, send_file, Response
import httpx
import redis

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "index.html")

# Logging
logger = logging.getLogger("prodown")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.info("SERVER STARTED")

DAILY_LIMIT = 5
API_KEY = os.environ.get("API_KEY")
API1_HOST = "tiktok-downloader-download-tiktok-videos-without-watermark.p.rapidapi.com"
API2_HOST = "social-video-downloader3.p.rapidapi.com"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin2026")

# Redis connection
# Redis connection
try:
    redis_url = os.environ.get("UPSTASH_REDIS_URL", "")
    redis_token = os.environ.get("UPSTASH_REDIS_TOKEN", "")
    if redis_token and "://" in redis_url:
        parts = redis_url.split("://")
        redis_url = f"{parts[0]}://:{redis_token}@{parts[1]}"
    rdb = redis.from_url(redis_url, decode_responses=True)
    rdb.ping()
    logger.info("REDIS CONNECTED")
except Exception as e:
    logger.error(f"REDIS ERROR: {str(e)}")
    rdb = None

def check_limit(ip):
    today = str(date.today())
    key = f"limit:{ip}:{today}"
    try:
        if rdb:
            count = rdb.get(key)
            count = int(count) if count else 0
            if count >= DAILY_LIMIT:
                return False
            rdb.incr(key)
            rdb.expire(key, 86400)
            return True
    except Exception as e:
        logger.error(f"REDIS LIMIT ERROR: {str(e)}")
    return True

def get_remaining(ip):
    today = str(date.today())
    key = f"limit:{ip}:{today}"
    try:
        if rdb:
            count = rdb.get(key)
            return max(0, DAILY_LIMIT - int(count)) if count else DAILY_LIMIT
    except:
        pass
    return DAILY_LIMIT

def try_api1(url):
    try:
        headers = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": API1_HOST}
        with httpx.Client(timeout=15) as client:
            response = client.get(f"https://{API1_HOST}/index", params={"url": url}, headers=headers)
        result = response.json()
        logger.info(f"API1 RESPONSE keys: {list(result.keys())}")
        video_list = result.get("video", [])
        cover_list = result.get("cover", [])
        if video_list:
            return {
                "status": "success",
                "title": result.get("author", ["Video"])[0],
                "description": result.get("description", [""])[0] if result.get("description") else "",
                "thumbnail": cover_list[0] if cover_list else "",
                "download_url": video_list[0]
            }
    except Exception as e:
        logger.error(f"API1 ERROR: {str(e)}")
    return None

def try_api2(url):
    try:
        headers = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": API2_HOST}
        encoded_url = quote(url, safe=':/?=&')
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            response = client.get(f"https://{API2_HOST}/download", params={"url": encoded_url}, headers=headers)
        logger.info(f"API2 STATUS: {response.status_code}")
        result = response.json()
        if not result.get("success"):
            return None
        data = result.get("data", {})
        thumbnail = data.get("thumbnail", "")
        return {
            "status": "success",
            "title": data.get("title", "Video"),
            "description": data.get("description", ""),
            "thumbnail": f"/thumb?url={quote(thumbnail, safe='')}" if thumbnail else "",
            "download_url": data.get("url", "")
        }
    except Exception as e:
        logger.error(f"API2 ERROR: {str(e)}")
    return None

@app.route("/")
def home():
    if os.path.exists(HTML_PATH):
        return send_file(HTML_PATH)
    return "index.html not found", 404

@app.route("/thumb")
def proxy_thumb():
    img_url = request.args.get("url")
    if not img_url:
        return "No URL", 400
    try:
        r = httpx.get(img_url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.instagram.com/"}, timeout=15, follow_redirects=True)
        return Response(r.content, content_type=r.headers.get("content-type", "image/jpeg"))
    except Exception as e:
        logger.error(f"THUMB ERROR: {str(e)}")
        return "Image Error", 500

@app.route("/admin")
def admin():
    password = request.args.get("key", "")
    if password != ADMIN_PASSWORD:
        return "Access Denied", 403

    today = str(date.today())
    total_today = 0
    total_users = 0

    try:
        if rdb:
            keys = rdb.keys(f"limit:*:{today}")
            total_users = len(keys)
            for k in keys:
                val = rdb.get(k)
                if val:
                    total_today += int(val)
    except:
        pass

    html = f"""<html><head><title>Admin — Pro Downloader</title>
    <meta charset="UTF-8">
    <style>
    body{{background:#0a0a18;color:#e2e8f0;font-family:Arial;padding:20px}}
    h1{{color:#a855f7;margin-bottom:20px}}
    .stats{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}}
    .stat{{background:#1a1a2e;padding:16px 24px;border-radius:10px;border:1px solid rgba(168,85,247,0.2)}}
    .stat-num{{font-size:28px;font-weight:900;color:#a855f7}}
    .stat-label{{font-size:11px;color:#475569;margin-top:4px}}
    .redis-status{{padding:8px 16px;border-radius:6px;font-size:12px;margin-bottom:16px;display:inline-block}}
    </style></head>
    <body>
    <h1>🔐 Admin Panel — Pro Downloader</h1>
    <div class="redis-status" style="background:{'rgba(16,185,129,0.1);color:#10b981;border:1px solid rgba(16,185,129,0.2)' if rdb else 'rgba(239,68,68,0.1);color:#f87171;border:1px solid rgba(239,68,68,0.2)'}">
        Redis: {'✅ Connected' if rdb else '❌ Not Connected'}
    </div>
    <div class="stats">
        <div class="stat"><div class="stat-num">{total_users}</div><div class="stat-label">Users Today</div></div>
        <div class="stat"><div class="stat-num">{total_today}</div><div class="stat-label">Downloads Today</div></div>
    </div>
    </body></html>"""
    return html

@app.route("/download", methods=["POST"])
def download_video():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    ip = request.remote_addr
    logger.info(f"NEW REQUEST | IP={ip} | URL={url}")

    if not url:
        return jsonify({"status": "error", "message": "Please enter a valid link"}), 400

    if not check_limit(ip):
        return jsonify({"status": "error", "message": "Daily limit reached. Upgrade to Pro!"}), 429

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(try_api1, url): "api1",
            executor.submit(try_api2, url): "api2"
        }
        result = None
        for future in as_completed(futures):
            res = future.result()
            if res and not result:
                result = res

    if result:
        result["remaining"] = get_remaining(ip)
        return jsonify(result)

    logger.error(f"FAILED | IP={ip} | URL={url}")
    return jsonify({"status": "error", "message": "Could not fetch video. Try another link."}), 500

if __name__ == "__main__":
    app.run(debug=True)