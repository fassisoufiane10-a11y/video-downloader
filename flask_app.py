import os
import logging
import sys
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import json

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from flask import Flask, request, jsonify, send_file, Response
import httpx

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "index.html")

logger = logging.getLogger("lumora")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.info("LUMORA SERVER STARTED")

DAILY_LIMIT = 5
API_KEY = os.environ.get("API_KEY")
API1_HOST = "tiktok-downloader-download-tiktok-videos-without-watermark.p.rapidapi.com"
API2_HOST = "social-video-downloader3.p.rapidapi.com"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin2026")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

UPSTASH_URL = os.environ.get("UPSTASH_REDIS_URL", "")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_TOKEN", "")

def redis_get(key):
    try:
        r = httpx.get(f"{UPSTASH_URL}/get/{key}", headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"}, timeout=5)
        return r.json().get("result")
    except:
        return None

def redis_incr(key):
    try:
        httpx.get(f"{UPSTASH_URL}/incr/{key}", headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"}, timeout=5)
    except:
        pass

def redis_expire(key, seconds):
    try:
        httpx.get(f"{UPSTASH_URL}/expire/{key}/{seconds}", headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"}, timeout=5)
    except:
        pass

def redis_keys(pattern):
    try:
        r = httpx.get(f"{UPSTASH_URL}/keys/{pattern}", headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"}, timeout=5)
        return r.json().get("result", [])
    except:
        return []

def check_limit(ip):
    today = str(date.today())
    key = f"limit:{ip}:{today}"
    try:
        count = redis_get(key)
        count = int(count) if count else 0
        if count >= DAILY_LIMIT:
            return False
        redis_incr(key)
        redis_expire(key, 86400)
        return True
    except Exception as e:
        logger.error(f"LIMIT ERROR: {str(e)}")
    return True

def get_remaining(ip):
    today = str(date.today())
    key = f"limit:{ip}:{today}"
    try:
        count = redis_get(key)
        return max(0, DAILY_LIMIT - int(count)) if count else DAILY_LIMIT
    except:
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
            thumbnail = cover_list[0] if cover_list else ""
            return {
                "status": "success",
                "title": result.get("author", ["Video"])[0],
                "description": result.get("description", [""])[0] if result.get("description") else "",
                "thumbnail": thumbnail,
                "download_url": video_list[0]
            }
    except Exception as e:
        logger.error(f"API1 ERROR: {str(e)}")
    return None

def try_api2(url):
    try:
        headers = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": API2_HOST}
        encoded_url = quote(url, safe=':/?=&')
        with httpx.Client(timeout=10, follow_redirects=True) as client:
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

def generate_with_gemini(title, description, platform):
    try:
        prompt = f"""You are a social media content expert. Based on this video:
Title/Author: {title}
Description: {description}
Platform: {platform}

Generate the following in JSON format only, no markdown, no code blocks:
{{
  "titles": ["title1", "title2", "title3"],
  "caption": "engaging caption for the video",
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5", "#tag6", "#tag7", "#tag8", "#tag9", "#tag10"],
  "shorts_idea": "idea for a short/reel version of this content"
}}"""

        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-8b:generateContent?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30
        )
        result = response.json()
        logger.info(f"GEMINI STATUS: {response.status_code}")
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        logger.error(f"GEMINI ERROR: {str(e)}")
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
        r = httpx.get(img_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.instagram.com/"
        }, timeout=15, follow_redirects=True)
        return Response(r.content, content_type=r.headers.get("content-type", "image/jpeg"))
    except Exception as e:
        logger.error(f"THUMB ERROR: {str(e)}")
        return "Image Error", 500

@app.route("/remaining")
def remaining():
    ip = request.remote_addr
    return jsonify({"remaining": get_remaining(ip)})

@app.route("/studio", methods=["POST"])
def studio():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"status": "error", "message": "Please enter a valid link"}), 400

    video_info = None
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(try_api1, url): "api1",
            executor.submit(try_api2, url): "api2"
        }
        for future in as_completed(futures):
            res = future.result()
            if res and not video_info:
                video_info = res

    if not video_info:
        return jsonify({"status": "error", "message": "Could not fetch video. Try another link."}), 500

    platform = "TikTok" if "tiktok" in url else "Instagram" if "instagram" in url else "YouTube"

    ai_result = generate_with_gemini(
        video_info.get("title", ""),
        video_info.get("description", ""),
        platform
    )

    if not ai_result:
        return jsonify({"status": "error", "message": "AI analysis failed. Please try again."}), 500

    return jsonify({
        "status": "success",
        "video_title": video_info.get("title", ""),
        "thumbnail": video_info.get("thumbnail", ""),
        "titles": "<br>".join([f"• {t}" for t in ai_result.get("titles", [])]),
        "caption": ai_result.get("caption", ""),
        "hashtags": ai_result.get("hashtags", []),
        "shorts": ai_result.get("shorts_idea", "")
    })

@app.route("/admin")
def admin():
    password = request.args.get("key", "")
    if password != ADMIN_PASSWORD:
        return "Access Denied", 403

    today = str(date.today())
    total_today = 0
    keys = redis_keys(f"limit:*:{today}")
    total_users = len(keys)
    for k in keys:
        val = redis_get(k)
        if val:
            total_today += int(val)

    redis_ok = UPSTASH_URL != "" and UPSTASH_TOKEN != ""

    html = f"""<html><head><title>Admin — LUMORA</title>
    <meta charset="UTF-8">
    <style>
    body{{background:#0a0a18;color:#e2e8f0;font-family:Arial;padding:20px}}
    h1{{color:#a855f7;margin-bottom:20px}}
    .stats{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}}
    .stat{{background:#1a1a2e;padding:16px 24px;border-radius:10px;border:1px solid rgba(168,85,247,0.2)}}
    .stat-num{{font-size:28px;font-weight:900;color:#a855f7}}
    .stat-label{{font-size:11px;color:#475569;margin-top:4px}}
    .badge{{padding:8px 16px;border-radius:6px;font-size:12px;margin-bottom:16px;display:inline-block}}
    </style></head>
    <body>
    <h1>🔐 Admin Panel — LUMORA</h1>
    <div class="badge" style="background:{'rgba(16,185,129,0.1);color:#10b981;border:1px solid rgba(16,185,129,0.2)' if redis_ok else 'rgba(239,68,68,0.1);color:#f87171;border:1px solid rgba(239,68,68,0.2)'}">
        Upstash: {'✅ Configured' if redis_ok else '❌ Not Configured'}
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
        return jsonify({"status": "error", "message": "Daily limit reached. Come back tomorrow!"}), 429

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