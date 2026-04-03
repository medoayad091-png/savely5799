import os, uuid, threading, time, json, glob, hashlib
from flask import Flask, request, jsonify, send_file, render_template, Response, stream_with_context
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "/tmp/viddown"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# job store: job_id -> {status, progress, speed, eta, filename, title, ext, error}
jobs = {}
# cache: url_key -> job_id of a completed job
cache = {}

def url_key(url, fmt, quality):
    return hashlib.md5(f"{url}|{fmt}|{quality}".encode()).hexdigest()

def cleanup_file(path, delay=900):
    def _d():
        time.sleep(delay)
        try: os.remove(path)
        except: pass
    threading.Thread(target=_d, daemon=True).start()

class ProgressLogger:
    def __init__(self, job_id):
        self.job_id = job_id

    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg):
        jobs[self.job_id]['error'] = msg

def make_progress_hook(job_id):
    def hook(d):
        job = jobs.get(job_id, {})
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            pct = (downloaded / total * 100) if total > 0 else 0
            speed = d.get('speed', 0) or 0
            eta = d.get('eta', 0) or 0
            job.update({
                'status': 'downloading',
                'progress': round(pct, 1),
                'speed': round(speed / 1024 / 1024, 2),  # MB/s
                'eta': int(eta),
                'downloaded': downloaded,
                'total': total,
            })
        elif d['status'] == 'finished':
            job.update({'status': 'merging', 'progress': 95})
    return hook

def do_download(job_id, url, fmt, quality, cache_key):
    out_template = os.path.join(DOWNLOAD_DIR, job_id)

    if fmt == "mp3":
        ydl_opts = {
            "outtmpl": out_template + ".%(ext)s",
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "logger": ProgressLogger(job_id),
            "progress_hooks": [make_progress_hook(job_id)],
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
            "concurrent_fragment_downloads": 4,
        }
    else:
        if quality == "best":
            fmt_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        else:
            q = int(quality)
            fmt_str = (
                f"bestvideo[height={q}][ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo[height<={q}][ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo[height<={q}]+bestaudio/best[height<={q}]/best"
            )
        ydl_opts = {
            "outtmpl": out_template + ".%(ext)s",
            "format": fmt_str,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "logger": ProgressLogger(job_id),
            "progress_hooks": [make_progress_hook(job_id)],
            # Speed optimizations
            "concurrent_fragment_downloads": 8,
            "buffersize": 1024 * 16,
            "http_chunk_size": 10485760,  # 10MB chunks
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")
            ext = "mp3" if fmt == "mp3" else "mp4"
            matches = glob.glob(out_template + ".*")
            if not matches:
                raise Exception("لم يتم إنشاء الملف")
            filename = matches[0]
            final = out_template + "." + ext
            if filename != final:
                try: os.rename(filename, final)
                except: final = filename
            jobs[job_id].update({
                "status": "done",
                "progress": 100,
                "filename": final,
                "title": title,
                "ext": ext,
            })
            cache[cache_key] = job_id
            cleanup_file(final, 900)
    except Exception as e:
        jobs[job_id].update({"status": "error", "error": str(e)})

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.json or {}
    url = data.get("url", "").strip()
    fmt = data.get("format", "mp4")
    quality = data.get("quality", "best")

    if not url:
        return jsonify({"error": "الرجاء إدخال رابط"}), 400

    # Check cache first
    ck = url_key(url, fmt, quality)
    cached_id = cache.get(ck)
    if cached_id and jobs.get(cached_id, {}).get("status") == "done":
        j = jobs[cached_id]
        if os.path.exists(j.get("filename", "")):
            return jsonify({"job_id": cached_id, "cached": True})

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "pending", "progress": 0, "speed": 0, "eta": 0}
    threading.Thread(target=do_download, args=(job_id, url, fmt, quality, ck), daemon=True).start()
    return jsonify({"job_id": job_id, "cached": False})

@app.route("/api/status/<job_id>")
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify({k: v for k, v in job.items() if k != "filename"})

# SSE endpoint for real-time progress
@app.route("/api/progress/<job_id>")
def job_progress(job_id):
    def generate():
        last_status = None
        for _ in range(600):  # max 10 min
            job = jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'not found'})}\n\n"
                break
            payload = {k: v for k, v in job.items() if k != "filename"}
            if payload != last_status:
                yield f"data: {json.dumps(payload)}\n\n"
                last_status = payload.copy()
            if job.get("status") in ("done", "error"):
                break
            time.sleep(1)
    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/file/<job_id>")
def serve_file(job_id):
    job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        return jsonify({"error": "not ready"}), 400
    filename = job["filename"]
    if not os.path.exists(filename):
        return jsonify({"error": "الملف انتهت صلاحيته"}), 410
    title = job.get("title", "video")
    ext = job.get("ext", "mp4")
    safe = "".join(c for c in title if c.isalnum() or c in " _-")[:60].strip()
    return send_file(filename, as_attachment=True, download_name=f"{safe}.{ext}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)
