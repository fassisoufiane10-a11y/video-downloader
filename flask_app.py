import os
import logging
import sys
import json
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from flask import Flask, request, jsonify, send_file, Response
from collections import defaultdict
import httpx

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "index.html")
LOG_FILE = os.path.join(BASE_DIR, "downloads.log")
LIMITS_FILE = os.path.join(BASE_DIR, "limits.json")

# Logging على console + ملف معاً
logger = logging.getLogger("prodown")
logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# File handler
try:
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except:
    pass

logger.info("SERVER STARTED")

DAILY_LIMIT = 5
API_KEY = "8ae11fb2dcmshc861331abad3af0p15ae2cjsn7676c624702f"
API1_HOST = "tiktok-downloader-download-tiktok-videos-without-watermark.p.rapidapi.com"
API2_HOST = "social-video-downloader3.p.rapidapi.com"
ADMIN_PASSWORD = "Fs7#Kp92@Lx"

# تحميل الـ limits من الملف
def load_limits():
    try:
        if os.path.exists(LIMITS_FILE):
            with open(LIMITS_FILE, "r") as f:
                return json.load(f)
    except:
        pass
    return {}

def save_limits(data):
    try:
        with open(LIMITS_FILE, "w") as f:
            json.dump(data, f)
    except:
        pass

limits_data = load_limits()

def check_limit(ip):
    today = str(date.today())
    if ip not in limits_data or limits_data[ip]["date"] != today:
        limits_data[ip] = {"count": 0, "date": today}
    if limits_data[ip]["count"] >= DAILY_LIMIT:
        return False
    limits_data[ip]["count"] += 1
    save_limits(limits_data)
    return True

def get_remaining(ip):
    today = str(date.today())
    if ip not in limits_data or limits_data[ip]["date"] != today:
        return DAILY_LIMIT
    return max(0, DAILY_LIMIT - limits_data[ip]["count"])

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
    today_users = {ip: d for ip, d in limits_data.items() if d.get("date") == today}
    total_today = sum(d["count"] for d in today_users.values())
    total_users = len(today_users)

    errors_only = request.args.get("errors") == "1"

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_logs = f.readlines()
        if errors_only:
            logs = "".join([l for l in all_logs if "ERROR" in l or "FAILED" in l])
        else:
            logs = "".join(all_logs[-100:])
    except:
        logs = "No logs yet"

    html = f"""<html><head><title>Admin — Pro Downloader</title>
    <meta charset="UTF-8">
    <style>
    body{{background:#0a0a18;color:#e2e8f0;font-family:Arial;padding:20px;margin:0}}
    h1{{color:#a855f7;margin-bottom:20px}}
    h2{{color:#c084fc;margin:20px 0 10px}}
    .stats{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}}
    .stat{{background:#1a1a2e;padding:16px 24px;border-radius:10px;border:1px solid rgba(168,85,247,0.2);min-width:120px}}
    .stat-num{{font-size:28px;font-weight:900;color:#a855f7}}
    .stat-label{{font-size:11px;color:#475569;margin-top:4px}}
    .actions{{display:flex;gap:8px;margin-bottom:16px}}
    .btn{{padding:8px 16px;border-radius:6px;border:none;cursor:pointer;font-size:12px;font-weight:700;text-decoration:none}}
    .btn-all{{background:rgba(168,85,247,0.2);color:#c084fc}}
    .btn-err{{background:rgba(239,68,68,0.2);color:#f87171}}
    pre{{background:#060610;padding:16px;border-radius:10px;overflow:auto;font-size:11px;max-height:500px;border:1px solid rgba(168,85,247,0.1);line-height:1.6}}
    .top-users{{background:#0d0d1a;border-radius:10px;padding:16px;border:1px solid rgba(168,85,247,0.15)}}
    .user-row{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(168,85,247,0.08);font-size:12px}}
    .user-ip{{color:#94a3b8}}
    .user-count{{color:#a855f7;font-weight:700}}
    </style></head>
    <body>
    <h1>🔐 Admin Panel — Pro Downloader</h1>
    <div class="stats">
        <div class="stat"><div class="stat-num">{total_users}</div><div class="stat-label">Users Today</div></div>
        <div class="stat"><div class="stat-num">{total_today}</div><div class="stat-label">Downloads Today</div></div>
        <div class="stat"><div class="stat-num">{len(limits_data)}</div><div class="stat-label">Total Users</div></div>
    </div>
    <h2>Top Users Today</h2>
    <div class="top-users">
    {"".join([f'<div class="user-row"><span class="user-ip">{ip}</span><span class="user-count">{d["count"]} downloads</span></div>' for ip, d in sorted(today_users.items(), key=lambda x: x[1]["count"], reverse=True)[:10]]) or "<p style='color:#475569;font-size:12px'>No users today</p>"}
    </div>
    <h2>Logs</h2>
    <div class="actions">
        <a href="/admin?key={ADMIN_PASSWORD}" class="btn btn-all">All Logs</a>
        <a href="/admin?key={ADMIN_PASSWORD}&errors=1" class="btn btn-err">Errors Only</a>
    </div>
    <pre>{logs}</pre>
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

    logger.info(f"FINAL RESULT = {result}")

    if result:
        result["remaining"] = get_remaining(ip)
        return jsonify(result)

    logger.error(f"FAILED | IP={ip} | URL={url}")
    return jsonify({"status": "error", "message": "Could not fetch video. Try another link."}), 500

if __name__ == "__main__":
    app.run(debug=True)