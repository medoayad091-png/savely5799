import os, uuid, threading, time, glob
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "/tmp/viddown"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
jobs = {}

def cleanup_file(path, delay=600):
    def _d():
        time.sleep(delay)
        try: os.remove(path)
        except: pass
    threading.Thread(target=_d, daemon=True).start()

def do_download(job_id, url, fmt, quality):
    jobs[job_id]["status"] = "downloading"
    out_template = os.path.join(DOWNLOAD_DIR, job_id)

    if fmt == "mp3":
        ydl_opts = {
            "outtmpl": out_template + ".%(ext)s",
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "postprocessors": [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}],
        }
    else:
        # Build format string based on quality
        if quality == "best":
            fmt_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        else:
            q = int(quality)
            fmt_str = (
                f"bestvideo[height={q}][ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo[height<={q}][ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo[height<={q}]+bestaudio"
                f"/best[height<={q}]/best"
            )
        ydl_opts = {
            "outtmpl": out_template + ".%(ext)s",
            "format": fmt_str,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")
            ext = "mp3" if fmt == "mp3" else "mp4"
            # Find the actual output file
            matches = glob.glob(out_template + ".*")
            if not matches:
                raise Exception("لم يتم إنشاء الملف")
            filename = matches[0]
            # Rename to correct extension if needed
            final = out_template + "." + ext
            if filename != final:
                os.rename(filename, final)
            jobs[job_id].update({"status":"done","filename":final,"title":title,"ext":ext})
            cleanup_file(final, 600)
    except Exception as e:
        jobs[job_id].update({"status":"error","error":str(e)})

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.json or {}
    url = data.get("url","").strip()
    fmt = data.get("format","mp4")
    quality = data.get("quality","best")
    if not url:
        return jsonify({"error":"الرجاء إدخال رابط"}), 400
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status":"pending"}
    threading.Thread(target=do_download, args=(job_id,url,fmt,quality), daemon=True).start()
    return jsonify({"job_id": job_id})

@app.route("/api/status/<job_id>")
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error":"not found"}), 404
    return jsonify(job)

@app.route("/api/file/<job_id>")
def serve_file(job_id):
    job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        return jsonify({"error":"not ready"}), 400
    filename = job["filename"]
    title = job.get("title","video")
    ext = job.get("ext","mp4")
    safe = "".join(c for c in title if c.isalnum() or c in " _-")[:60]
    return send_file(filename, as_attachment=True, download_name=f"{safe}.{ext}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)
