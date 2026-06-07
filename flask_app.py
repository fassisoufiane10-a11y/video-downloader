import os
import logging
import sys
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
from flask import Flask, request, jsonify, send_file, Response
from collections import defaultdict
from datetime import date
import httpx

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "index.html")
LOG_FILE = os.path.join(BASE_DIR, "downloads.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8"
)

logging.info("SERVER STARTED")

DAILY_LIMIT = 5
user_downloads = defaultdict(lambda: {"count": 0, "date": str(date.today())})

API_KEY = "88e4bd1c94msh209df9927beaafcp10fbdejsn05050b2447fb"
API1_HOST = "tiktok-downloader-download-tiktok-videos-without-watermark.p.rapidapi.com"
API2_HOST = "social-video-downloader3.p.rapidapi.com"
ADMIN_PASSWORD = "admin2026"

def check_limit(ip):
    today = str(date.today())
    if user_downloads[ip]["date"] != today:
        user_downloads[ip] = {"count": 0, "date": today}
    if user_downloads[ip]["count"] >= DAILY_LIMIT:
        return False
    user_downloads[ip]["count"] += 1
    return True

def try_api1(url):
    try:
        headers = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": API1_HOST}
        with httpx.Client(timeout=15) as client:
            response = client.get(f"https://{API1_HOST}/index", params={"url": url}, headers=headers)
        result = response.json()
        logging.info(f"API1 RESPONSE keys: {list(result.keys())}")
        video_list = result.get("video", [])
        cover_list = result.get("cover", [])
        if video_list:
            return {
                "status": "success",
                "title": result.get("author", ["Video"])[0],
                "thumbnail": cover_list[0] if cover_list else "",
                "download_url": video_list[0]
            }
    except Exception as e:
        logging.error(f"API1 ERROR: {str(e)}")
    return None

def try_api2(url):
    try:
        headers = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": API2_HOST}
        encoded_url = quote(url, safe=':/?=&')
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            response = client.get(f"https://{API2_HOST}/download", params={"url": encoded_url}, headers=headers)
        logging.info(f"API2 STATUS: {response.status_code}")
        result = response.json()
        if not result.get("success"):
            return None
        data = result.get("data", {})
        thumbnail = data.get("thumbnail", "")
        return {
            "status": "success",
            "title": data.get("title", "Video"),
            "thumbnail": f"/thumb?url={quote(thumbnail, safe='')}" if thumbnail else "",
            "download_url": data.get("url", "")
        }
    except Exception as e:
        logging.error(f"API2 ERROR: {str(e)}")
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
        logging.error(f"THUMB ERROR: {str(e)}")
        return "Image Error", 500

@app.route("/admin")
def admin():
    password = request.args.get("key", "")
    if password != ADMIN_PASSWORD:
        return "Access Denied", 403
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = f.read()
        total = sum(v["count"] for v in user_downloads.values())
        html = f"""<html><head><title>Admin</title>
        <style>body{{background:#0a0a18;color:#e2e8f0;font-family:Arial;padding:20px}}
        h1{{color:#a855f7}}pre{{background:#111;padding:15px;border-radius:8px;overflow:auto;font-size:12px;max-height:500px}}
        .stat{{background:#1a1a2e;padding:15px;border-radius:8px;margin-bottom:10px;display:inline-block;margin-right:10px}}
        .stat-num{{font-size:24px;font-weight:bold;color:#a855f7}}</style></head>
        <body><h1>Admin Panel — Pro Downloader</h1>
        <div class="stat"><div class="stat-num">{len(user_downloads)}</div>Users Today</div>
        <div class="stat"><div class="stat-num">{total}</div>Downloads Today</div>
        <h2 style="margin-top:20px;color:#c084fc">Latest Logs</h2>
        <pre>{logs[-3000:] if len(logs) > 3000 else logs}</pre>
        </body></html>"""
        return html
    except:
        return "No logs yet", 200

@app.route("/download", methods=["POST"])
def download_video():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    logging.info(f"NEW REQUEST | IP={request.remote_addr} | URL={url}")
    if not url:
        return jsonify({"status": "error", "message": "Please enter a valid link"}), 400
    ip = request.remote_addr
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

    logging.info(f"FINAL RESULT = {result}")
    if result:
        result["remaining"] = DAILY_LIMIT - user_downloads[ip]["count"]
        return jsonify(result)
    logging.error(f"FAILED | IP={ip} | URL={url}")
    return jsonify({"status": "error", "message": "Could not fetch video. Try another link."}), 500

if __name__ == "__main__":
    app.run(debug=True)