import os
from flask import Flask, request, jsonify, send_file, Response
from collections import defaultdict
from datetime import date
import httpx

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, 'index.html')

DAILY_LIMIT = 5
user_downloads = defaultdict(lambda: {"count": 0, "date": str(date.today())})

API_KEY = "88e4bd1c94msh209df9927beaafcp10fbdejsn05050b2447fb"
API_HOST = "tiktok-downloader-download-tiktok-videos-without-watermark.p.rapidapi.com"

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
        headers = {
            "x-rapidapi-key": API_KEY,
            "x-rapidapi-host": API_HOST
        }
        with httpx.Client(timeout=15) as client:
            response = client.get(
                f"https://{API_HOST}/index",
                params={"url": url},
                headers=headers
            )
            result = response.json()
        video_list = result.get("video", [])
        cover_list = result.get("cover", [])
        video_url = video_list[0] if video_list else ""
        thumbnail = cover_list[0] if cover_list else ""
        title = result.get("author", ["فيديو تيك توك"])[0]
        if not video_url:
            return jsonify({"status": "error", "message": "لم يتم العثور على رابط التحميل"}), 500
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
    video_url = request.args.get('url', '')
    if not video_url:
        return "No URL", 400
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            r = client.get(video_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.tiktok.com/",
                "Accept": "*/*"
            })
            return Response(
                r.content,
                content_type="video/mp4",
                headers={"Content-Disposition": "attachment; filename=video.mp4"}
            )
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(debug=True)