import os
import logging
import sys
import sqlite3
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from flask import Flask, request, jsonify, send_file, Response
import httpx

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "index.html")
DB_FILE = "/data/prodown.db"

# Logging
logger = logging.getLogger("prodown")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
try:
    file_handler = logging.FileHandler(os.path.join(BASE_DIR, "downloads.log"), encoding="utf-8")
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

# إنشاء قاعدة البيانات
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS limits (
        ip TEXT PRIMARY KEY,
        count INTEGER DEFAULT 0,
        last_date TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        level TEXT,
        ip TEXT,
        url TEXT,
        status TEXT,
        message TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def check_limit(ip):
    today = str(date.today())
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT count, last_date FROM limits WHERE ip=?", (ip,))
    row = c.fetchone()
    if not row or row[1] != today:
        c.execute("INSERT OR REPLACE INTO limits (ip, count, last_date) VALUES (?,?,?)", (ip, 1, today))
        conn.commit()
        conn.close()
        return True
    if row[0] >= DAILY_LIMIT:
        conn.close()
        return False
    c.execute("UPDATE limits SET count=count+1 WHERE ip=?", (ip,))
    conn.commit()
    conn.close()
    return True

def get_remaining(ip):
    today = str(date.today())
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT count, last_date FROM limits WHERE ip=?", (ip,))
    row = c.fetchone()
    conn.close()
    if not row or row[1] != today:
        return DAILY_LIMIT
    return max(0, DAILY_LIMIT - row[0])

def log_request(ip, url, status, message=""):
    try:
        from datetime import datetime
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO logs (timestamp, level, ip, url, status, message) VALUES (?,?,?,?,?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "INFO" if status == "success" else "ERROR", ip, url, status, message))
        conn.commit()
        conn.close()
    except:
        pass

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
    errors_only = request.args.get("errors") == "1"

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM limits WHERE last_date=?", (today,))
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(count) FROM limits WHERE last_date=?", (today,))
    total_downloads = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM limits")
    all_users = c.fetchone()[0]
    c.execute("SELECT ip, count FROM limits WHERE last_date=? ORDER BY count DESC LIMIT 10", (today,))
    top_users = c.fetchall()
    if errors_only:
        c.execute("SELECT timestamp, ip, url, message FROM logs WHERE level='ERROR' ORDER BY id DESC LIMIT 50")
    else:
        c.execute("SELECT timestamp, level, ip, url, status FROM logs ORDER BY id DESC LIMIT 100")
    logs = c.fetchall()
    conn.close()

    logs_html = ""
    for log in logs:
        color = "#f87171" if "ERROR" in str(log) else "#94a3b8"
        logs_html += f'<div style="color:{color};padding:3px 0;border-bottom:1px solid rgba(168,85,247,0.05);font-size:11px">{" | ".join(str(x) for x in log)}</div>'

    html = f"""<html><head><title>Admin — Pro Downloader</title>
    <meta charset="UTF-8">
    <style>
    body{{background:#0a0a18;color:#e2e8f0;font-family:Arial;padding:20px;margin:0}}
    h1{{color:#a855f7;margin-bottom:20px}}
    h2{{color:#c084fc;margin:20px 0 10px;font-size:15px}}
    .stats{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}}
    .stat{{background:#1a1a2e;padding:16px 24px;border-radius:10px;border:1px solid rgba(168,85,247,0.2)}}
    .stat-num{{font-size:28px;font-weight:900;color:#a855f7}}
    .stat-label{{font-size:11px;color:#475569;margin-top:4px}}
    .actions{{display:flex;gap:8px;margin-bottom:12px}}
    .btn{{padding:7px 14px;border-radius:6px;border:none;cursor:pointer;font-size:11px;font-weight:700;text-decoration:none;display:inline-block}}
    .btn-all{{background:rgba(168,85,247,0.2);color:#c084fc}}
    .btn-err{{background:rgba(239,68,68,0.2);color:#f87171}}
    .logs-box{{background:#060610;padding:16px;border-radius:10px;max-height:500px;overflow:auto;border:1px solid rgba(168,85,247,0.1)}}
    .top-users{{background:#0d0d1a;border-radius:10px;padding:16px;border:1px solid rgba(168,85,247,0.15);margin-bottom:16px}}
    .user-row{{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid rgba(168,85,247,0.08);font-size:12px}}
    </style></head>
    <body>
    <h1>🔐 Admin Panel — Pro Downloader</h1>
    <div class="stats">
        <div class="stat"><div class="stat-num">{total_users}</div><div class="stat-label">Users Today</div></div>
        <div class="stat"><div class="stat-num">{total_downloads}</div><div class="stat-label">Downloads Today</div></div>
        <div class="stat"><div class="stat-num">{all_users}</div><div class="stat-label">Total Users</div></div>
    </div>
    <h2>Top Users Today</h2>
    <div class="top-users">
    {"".join([f'<div class="user-row"><span style="color:#94a3b8">{ip}</span><span style="color:#a855f7;font-weight:700">{count} downloads</span></div>' for ip, count in top_users]) or "<p style='color:#475569;font-size:12px'>No data</p>"}
    </div>
    <h2>Logs</h2>
    <div class="actions">
        <a href="/admin?key={ADMIN_PASSWORD}" class="btn btn-all">All Logs</a>
        <a href="/admin?key={ADMIN_PASSWORD}&errors=1" class="btn btn-err">Errors Only</a>
    </div>
    <div class="logs-box">{logs_html or "<p style='color:#475569'>No logs yet</p>"}</div>
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
        log_request(ip, url, "error", "Daily limit reached")
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
        log_request(ip, url, "success", result.get("title", ""))
        result["remaining"] = get_remaining(ip)
        return jsonify(result)

    log_request(ip, url, "error", "All APIs failed")
    logger.error(f"FAILED | IP={ip} | URL={url}")
    return jsonify({"status": "error", "message": "Could not fetch video. Try another link."}), 500

if __name__ == "__main__":
    app.run(debug=True)