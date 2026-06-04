import os
import tempfile
from flask import Flask, request, jsonify, send_file, Response
from collections import defaultdict
from datetime import date
import yt_dlp

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, 'index.html')

DAILY_LIMIT = 5
user_downloads = defaultdict(lambda: {"count": 0, "date": str(date.today())})

def check_limit(ip):
    today = str(date.today())
    if user_downloads[ip]["date"] != today:
        user_downloads[ip] = {"count": 0, "date": today}
    if user_downloads[ip]["count"] >= DAILY_LIMIT:
        return False
    user_downloads[ip]["count"] += 1
    return True

@app.route('/')
def home():
    if os.path.exists(HTML_PATH):
        return send_file(HTML_PATH)
    return "Error: index.html is missing.", 404

@app.route('/download', methods=['POST'])
def download_video():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({"status": "error", "message": "الرجاء إدخال رابط صحيح"}), 400
    ip = request.remote_addr
    if not check_limit(ip):
        return jsonify({"status": "error", "message": "وصلت للحد اليومي، ارجع بكره"}), 429
    try:
        opts = {
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        video_url = info.get("url", "")
        thumbnail = info.get("thumbnail", "")
        title = info.get("title", "فيديو تيك توك")
        return jsonify({
            "status": "success",
            "title": title,
            "thumbnail": thumbnail,
            "download_url": video_url,
            "remaining": DAILY_LIMIT - user_downloads[ip]["count"]
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"خطأ: {str(e)}"}), 500

@app.route('/proxy')
def proxy_video():
    url = request.args.get('url', '')
    if not url:
        return "No URL", 400
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4', dir='/tmp')
        tmp.close()
        opts = {
            "quiet": True,
            "outtmpl": tmp.name,
            "format": "best",
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        return send_file(tmp.name, as_attachment=True, download_name='video.mp4', mimetype='video/mp4')
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(debug=True)