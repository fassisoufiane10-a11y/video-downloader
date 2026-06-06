import os
from flask import Flask, request, jsonify, send_file
from collections import defaultdict
from datetime import date
import httpx

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, 'index.html')

DAILY_LIMIT = 5
user_downloads = defaultdict(lambda: {"count": 0, "date": str(date.today())})

API_KEY = "88e4bd1c94msh209df9927beaafcp10fbdejsn05050b2447fb"
API1_HOST = "tiktok-downloader-download-tiktok-videos-without-watermark.p.rapidapi.com"
API2_HOST = "social-video-downloader3.p.rapidapi.com"

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
        video_list = result.get("video", [])
        cover_list = result.get("cover", [])
        if video_list:
            return {
                "status": "success",
                "title": result.get("author", ["Video"])[0],
                "thumbnail": cover_list[0] if cover_list else "",
                "download_url": video_list[0]
            }
    except:
        pass
    return None

def try_api2(url):
    try:
        headers = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": API2_HOST, "Content-Type": "application/json"}
        with httpx.Client(timeout=15) as client:
            response = client.get(f"https://{API2_HOST}/download", params={"url": url}, headers=headers)
            result = response.json()
        print("API2 Response:", result)
        data = result.get("data", {})
        video_url = data.get("url") or result.get("url") or result.get("download_url")
        thumbnail = data.get("thumbnail", "") or result.get("thumbnail", "")
        title = data.get("title", "Video") or result.get("title", "Video")
        if isinstance(video_url, list):
            video_url = video_url[0]
        if video_url:
            return {
                "status": "success",
                "title": title,
                "thumbnail": thumbnail,
                "download_url": video_url
            }
    except Exception as e:
        print("API2 Error:", str(e))
    return None

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
        return jsonify({"status": "error", "message": "Please enter a valid link"}), 400
    ip = request.remote_addr
    if not check_limit(ip):
        return jsonify({"status": "error", "message": "Daily limit reached. Upgrade to Pro!"}), 429

    result = try_api1(url)
    if not result:
        result = try_api2(url)

    if result:
        result["remaining"] = DAILY_LIMIT - user_downloads[ip]["count"]
        return jsonify(result)

    return jsonify({"status": "error", "message": "Could not fetch video. Try another link."}), 500

if __name__ == '__main__':
    app.run(debug=True)