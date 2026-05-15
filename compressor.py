#!/usr/bin/env python3
"""
Discord Video Compressor — Local Server
Run: python compressor.py
Open: http://localhost:5000
"""

import json
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static")

# ─── Configuration ───────────────────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 5000
# Starting directory for the file browser
if platform.system() == "Windows":
    DEFAULT_ROOT = str(Path.home() / "Videos")
else:
    DEFAULT_ROOT = str(Path.home())

# ─── Job queue ───────────────────────────────────────────────────────────────
jobs: dict[str, dict] = {}  # job_id -> job state
jobs_lock = threading.Lock()
current_process: subprocess.Popen | None = None
process_lock = threading.Lock()
worker_thread: threading.Thread | None = None


# ─── Routes: Static ─────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


# ─── Routes: File Browser ───────────────────────────────────────────────────
@app.route("/api/browse")
def browse():
    """List files and folders in a directory."""
    req_path = request.args.get("path", DEFAULT_ROOT)

    # Resolve path
    p = Path(req_path).resolve()
    if not p.exists():
        return jsonify({"error": f"Path does not exist: {p}"}), 404
    if not p.is_dir():
        return jsonify({"error": "Not a directory"}), 400

    items = []
    try:
        for entry in sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            # Skip hidden files
            if entry.name.startswith("."):
                continue
            try:
                is_dir = entry.is_dir()
                size = 0 if is_dir else entry.stat().st_size
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": is_dir,
                    "size": size,
                    "ext": entry.suffix.lower() if not is_dir else "",
                })
            except PermissionError:
                continue
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403

    # Get parent
    parent = str(p.parent) if p.parent != p else None

    # Get drives on Windows
    drives = []
    if platform.system() == "Windows":
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if bitmask & 1:
                drives.append(f"{letter}:\\")
            bitmask >>= 1

    return jsonify({
        "path": str(p),
        "parent": parent,
        "drives": drives,
        "items": items,
    })


# ─── Routes: ffprobe ────────────────────────────────────────────────────────
@app.route("/api/probe", methods=["POST"])
def probe():
    """Run ffprobe on a file and return full JSON."""
    data = request.get_json()
    filepath = data.get("path", "")

    if not filepath or not Path(filepath).exists():
        return jsonify({"error": "File not found"}), 404

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-hide_banner",
                "-show_format", "-show_streams", "-show_chapters",
                "-show_private_data", "-print_format", "json",
                filepath,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return jsonify({"error": f"ffprobe error: {result.stderr.strip()}"}), 500

        probe_data = json.loads(result.stdout)

        # Extract key info for convenience
        video_stream = None
        audio_stream = None
        for s in probe_data.get("streams", []):
            if s.get("codec_type") == "video" and video_stream is None:
                video_stream = s
            elif s.get("codec_type") == "audio" and audio_stream is None:
                audio_stream = s

        info = {"raw": probe_data}

        if video_stream:
            fps_str = video_stream.get("r_frame_rate", "30/1")
            try:
                num, den = fps_str.split("/")
                fps = round(int(num) / int(den), 3)
            except Exception:
                fps = 30

            field_order = video_stream.get("field_order", "progressive")
            is_interlaced = field_order not in ("progressive", "unknown", "")

            info["video"] = {
                "codec": video_stream.get("codec_name"),
                "codec_long": video_stream.get("codec_long_name"),
                "width": video_stream.get("width"),
                "height": video_stream.get("height"),
                "fps": fps,
                "fps_raw": fps_str,
                "pix_fmt": video_stream.get("pix_fmt"),
                "field_order": field_order,
                "interlaced": is_interlaced,
                "sar": video_stream.get("sample_aspect_ratio"),
                "dar": video_stream.get("display_aspect_ratio"),
                "bit_rate": video_stream.get("bit_rate"),
                "duration": video_stream.get("duration"),
                "profile": video_stream.get("profile"),
            }

        if audio_stream:
            info["audio"] = {
                "codec": audio_stream.get("codec_name"),
                "codec_long": audio_stream.get("codec_long_name"),
                "sample_rate": audio_stream.get("sample_rate"),
                "channels": audio_stream.get("channels"),
                "channel_layout": audio_stream.get("channel_layout"),
                "bit_rate": audio_stream.get("bit_rate"),
            }

        fmt = probe_data.get("format", {})
        info["format"] = {
            "name": fmt.get("format_name"),
            "long_name": fmt.get("format_long_name"),
            "duration": float(fmt.get("duration", 0)),
            "size": int(fmt.get("size", 0)),
            "bit_rate": fmt.get("bit_rate"),
        }

        return jsonify(info)

    except FileNotFoundError:
        return jsonify({"error": "ffprobe not found. Is ffmpeg installed and in PATH?"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "ffprobe timed out"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Routes: Job management ─────────────────────────────────────────────────
@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    """List all jobs."""
    with jobs_lock:
        return jsonify(list(jobs.values()))


@app.route("/api/jobs", methods=["POST"])
def add_job():
    """Add one or more jobs to the queue."""
    data = request.get_json()
    items = data if isinstance(data, list) else [data]

    added = []
    with jobs_lock:
        for item in items:
            job_id = str(uuid.uuid4())[:8]
            job = {
                "id": job_id,
                "input": item["input"],
                "output": item["output"],
                "command": item["command"],  # full ffmpeg command(s) as list of strings
                "status": "queued",  # queued | running | done | error | cancelled
                "progress": 0,
                "fps_speed": 0,
                "current_time": 0,
                "duration": item.get("duration", 0),
                "error": None,
                "filename": Path(item["input"]).name,
                "output_size": 0,
            }
            jobs[job_id] = job
            added.append(job)

    # Start worker if not running
    _ensure_worker()

    return jsonify(added)


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def cancel_job(job_id):
    """Cancel or remove a job."""
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        if job["status"] == "running":
            job["status"] = "cancelled"
            with process_lock:
                if current_process and current_process.poll() is None:
                    try:
                        current_process.terminate()
                    except Exception:
                        pass
        elif job["status"] == "queued":
            job["status"] = "cancelled"

    return jsonify({"ok": True})


@app.route("/api/jobs/clear", methods=["POST"])
def clear_jobs():
    """Remove finished/cancelled/error jobs."""
    with jobs_lock:
        to_remove = [jid for jid, j in jobs.items() if j["status"] in ("done", "error", "cancelled")]
        for jid in to_remove:
            del jobs[jid]
    return jsonify({"removed": len(to_remove)})


# ─── Routes: Progress SSE ───────────────────────────────────────────────────
@app.route("/api/progress")
def progress_stream():
    """Server-Sent Events stream for real-time job updates."""
    def generate():
        last_state = ""
        while True:
            with jobs_lock:
                state = json.dumps(list(jobs.values()))
            if state != last_state:
                yield f"data: {state}\n\n"
                last_state = state
            time.sleep(0.3)

    return Response(generate(), mimetype="text/event-stream")


# ─── Worker ──────────────────────────────────────────────────────────────────
def _ensure_worker():
    global worker_thread
    if worker_thread and worker_thread.is_alive():
        return
    worker_thread = threading.Thread(target=_worker_loop, daemon=True)
    worker_thread.start()


def _worker_loop():
    global current_process

    while True:
        # Find next queued job
        job = None
        with jobs_lock:
            for j in jobs.values():
                if j["status"] == "queued":
                    j["status"] = "running"
                    job = j
                    break

        if job is None:
            time.sleep(0.5)
            # Check if any jobs are still queued
            with jobs_lock:
                has_queued = any(j["status"] == "queued" for j in jobs.values())
            if not has_queued:
                break
            continue

        _run_job(job)


def _run_job(job):
    global current_process
    commands = job["command"]  # list of command strings
    duration = job["duration"]

    for i, cmd in enumerate(commands):
        if job["status"] == "cancelled":
            return

        is_last_pass = (i == len(commands) - 1)

        try:
            # Parse command string to list
            # Use shell=True on Windows for proper path handling
            use_shell = platform.system() == "Windows"

            with process_lock:
                current_process = subprocess.Popen(
                    cmd if use_shell else _split_cmd(cmd),
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    shell=use_shell,
                    universal_newlines=True,
                    encoding="utf-8",
                    errors="replace",
                )

            # Parse ffmpeg progress from stderr
            line_buffer = ""
            while True:
                if job["status"] == "cancelled":
                    with process_lock:
                        if current_process and current_process.poll() is None:
                            current_process.terminate()
                    return

                char = current_process.stderr.read(1)
                if not char:
                    break

                if char in ("\r", "\n"):
                    _parse_progress_line(line_buffer, job, duration, is_last_pass, len(commands))
                    line_buffer = ""
                else:
                    line_buffer += char

            current_process.wait()

            if current_process.returncode != 0 and job["status"] != "cancelled":
                with jobs_lock:
                    job["status"] = "error"
                    job["error"] = f"ffmpeg exited with code {current_process.returncode}"
                return

        except Exception as e:
            with jobs_lock:
                job["status"] = "error"
                job["error"] = str(e)
            return

    # Done
    if job["status"] == "running":
        with jobs_lock:
            job["status"] = "done"
            job["progress"] = 100
            # Get output file size
            try:
                job["output_size"] = Path(job["output"]).stat().st_size
            except Exception:
                pass


def _parse_progress_line(line: str, job: dict, duration: float, is_last_pass: bool, total_passes: int):
    """Parse ffmpeg stderr progress line like 'frame= 150 fps= 45 ... time=00:00:05.00 ...'"""
    # Extract time
    m = re.search(r"time=(\d+):(\d+):(\d+\.?\d*)", line)
    if m and duration > 0:
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        pass_progress = min(t / duration * 100, 100)

        # If two-pass, first pass = 0-50%, second = 50-100%
        if total_passes > 1:
            base = 0 if not is_last_pass else 50
            overall = base + pass_progress * 0.5
        else:
            overall = pass_progress

        with jobs_lock:
            job["progress"] = round(overall, 1)
            job["current_time"] = round(t, 2)

    # Extract speed/fps
    m_fps = re.search(r"fps=\s*(\d+\.?\d*)", line)
    if m_fps:
        with jobs_lock:
            job["fps_speed"] = float(m_fps.group(1))


def _split_cmd(cmd: str) -> list[str]:
    """Split a command string respecting quotes."""
    import shlex
    return shlex.split(cmd)


# ─── Startup ────────────────────────────────────────────────────────────────
def main():
    # Check ffmpeg/ffprobe
    for tool in ("ffmpeg", "ffprobe"):
        try:
            subprocess.run([tool, "-version"], capture_output=True, timeout=5)
        except FileNotFoundError:
            print(f"[ERROR] {tool} not found in PATH!")
            print("Install ffmpeg: https://ffmpeg.org/download.html")
            sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════╗
║   Discord Video Compressor                   ║
║   http://{HOST}:{PORT}                       ║
║   Press Ctrl+C to stop                       ║
╚══════════════════════════════════════════════╝
""")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
