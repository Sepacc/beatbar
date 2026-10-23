"""
web/app.py - Web Server Backend for Beatbar Viewer.

Provides:
- Library page serving and API
- Full HTTP 206 Partial Content (Range request) video streaming for smooth Android playback
- Real-time .beat and .json beatmap parsing
- Dynamic thumbnail generation and serving
- QR code generation for 1-tap mobile pairing
"""

import os
import sys
import io
import json
import socket
import argparse

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
from typing import List, Optional, Dict, Any
from flask import Flask, request, jsonify, send_file, send_from_directory, render_template, abort, make_response
from werkzeug.exceptions import HTTPException

try:
    import qrcode
except ImportError:
    qrcode = None

from web.beat_parser import parse_beat_file, find_matching_beat_file
from web.video_scanner import VideoScanner, THUMBNAIL_DIR
from web.skin_manager import (
    list_skins,
    get_skin,
    get_skin_asset,
    get_video_pack_skin,
    get_video_pack_skin_asset,
    SKINS_DIR
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DEFAULT_VIDEOS_DIR = os.path.join(ROOT_DIR, "videos")

app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "static"),
    template_folder=os.path.join(BASE_DIR, "templates")
)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.jinja_env.auto_reload = True


@app.after_request
def add_cache_headers(response):
    if "text/html" in response.headers.get("Content-Type", ""):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Global scanner instance
video_folder = DEFAULT_VIDEOS_DIR
scanner = VideoScanner(video_folder)


def get_lan_ips() -> List[str]:
    """Returns list of local area network IP addresses for mobile access."""
    lan_ips = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                lan_ips.append(ip)
    except Exception:
        pass
    # Fallback via UDP socket trick
    if not lan_ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and ip not in lan_ips:
                lan_ips.append(ip)
        except Exception:
            pass
    return lan_ips or ["127.0.0.1"]


@app.after_request
def add_cors_and_cache_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Range, Content-Type, Accept"
    response.headers["Access-Control-Expose-Headers"] = "Content-Range, Accept-Ranges, Content-Length"
    response.headers["Accept-Ranges"] = "bytes"
    return response


@app.errorhandler(400)
def handle_bad_request(e):
    msg = str(e.description if hasattr(e, "description") else e)
    return jsonify({"success": False, "error": msg}), 400


@app.errorhandler(404)
def handle_not_found(e):
    if request.path.startswith("/api/"):
        msg = str(e.description if hasattr(e, "description") else e)
        return jsonify({"success": False, "error": msg}), 404
    return e


@app.errorhandler(500)
def handle_server_error(e):
    err_obj = getattr(e, "original_exception", getattr(e, "description", e))
    return jsonify({"success": False, "error": f"Internal server error: {err_obj}"}), 500


@app.errorhandler(Exception)
def handle_uncaught_exception(e):
    if isinstance(e, HTTPException):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": e.description}), e.code
        return e
    return jsonify({"success": False, "error": f"Server error: {str(e)}"}), 500


# ------------------------------------------------------------------------------
# Frontend Routes
# ------------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ------------------------------------------------------------------------------
# API Routes
# ------------------------------------------------------------------------------

@app.route("/api/config")
def api_config():
    lan_ips = get_lan_ips()
    port = request.host.split(":")[-1] if ":" in request.host else "8080"
    mobile_urls = [f"http://{ip}:{port}" for ip in lan_ips]
    ver_path = os.path.join(ROOT_DIR, "web", ".version")
    ver_str = "1.2.0"
    if os.path.exists(ver_path):
        try:
            with open(ver_path, "r", encoding="utf-8") as vf:
                ver_str = vf.read().strip()
        except Exception:
            pass
    return jsonify({
        "version": ver_str,
        "videos_folder": video_folder,
        "lan_ips": lan_ips,
        "mobile_urls": mobile_urls,
        "active_mobile_url": mobile_urls[0] if mobile_urls else f"http://localhost:{port}"
    })


@app.route("/api/library")
def api_library():
    force_refresh = request.args.get("refresh", "false").lower() == "true"
    videos = scanner.scan(force_refresh=force_refresh)
    return jsonify({
        "folder": video_folder,
        "total_videos": len(videos),
        "videos": videos
    })


@app.route("/api/rescan", methods=["POST"])
def api_rescan():
    videos = scanner.scan(force_refresh=True)
    return jsonify({
        "success": True,
        "total_videos": len(videos),
        "videos": videos
    })


@app.route("/api/beats/<filename>")
def api_beats(filename):
    """
    Returns parsed beatmap data (beats, zones, settings) for a video file or beat file.
    """
    direct_path = os.path.join(video_folder, filename)
    matched_beat = None

    if os.path.isfile(direct_path) and (filename.lower().endswith(".beat") or filename.lower().endswith(".json")):
        matched_beat = direct_path
    elif os.path.exists(direct_path):
        matched_beat = find_matching_beat_file(direct_path)
    else:
        base_name = os.path.splitext(filename)[0]
        cand_beat = os.path.join(video_folder, f"{base_name}.beat")
        if os.path.isfile(cand_beat):
            matched_beat = cand_beat
        else:
            matched_beat = find_matching_beat_file(os.path.join(video_folder, filename))

    if not matched_beat:
        return jsonify({
            "has_beats": False,
            "error": f"No matching beatmap found for {filename}",
            "beats": [],
            "zones": [],
            "settings": {}
        }), 404

    try:
        data = parse_beat_file(matched_beat)
        data["has_beats"] = True
        data["beat_file"] = os.path.basename(matched_beat)
        return jsonify(data)
    except Exception as e:
        return jsonify({
            "has_beats": False,
            "error": f"Failed to parse beatmap {os.path.basename(matched_beat)}: {str(e)}",
            "beats": [],
            "zones": [],
            "settings": {}
        }), 400


@app.route("/api/video/<filename>")
@app.route("/api/stream/<filename>")
def api_video(filename):
    """
    Streams video with support for HTTP 206 Partial Content (Byte Range requests).
    Essential for seeking on mobile browsers and Android media framework.
    Supports regular video files as well as extracted videos from .beat bundles.
    """
    file_path = os.path.join(video_folder, filename)

    # 1. If filename is a .beat file, stream its extracted video
    if filename.lower().endswith(".beat") and os.path.isfile(file_path):
        extracted = scanner.get_extracted_video_path(file_path)
        if extracted and os.path.isfile(extracted):
            file_path = extracted
        else:
            return jsonify({
                "success": False,
                "error": f"No playable video found or extracted from .beat bundle '{filename}'"
            }), 404
    elif not os.path.isfile(file_path):
        # 2. If video was requested by base name or .mp4, check if a matching .beat bundle exists
        base_name, _ = os.path.splitext(filename)
        cand_beat = os.path.join(video_folder, f"{base_name}.beat")
        if os.path.isfile(cand_beat):
            extracted = scanner.get_extracted_video_path(cand_beat)
            if extracted and os.path.isfile(extracted):
                file_path = extracted

    if not os.path.isfile(file_path):
        abort(404)

    # Determine mimetype
    ext = os.path.splitext(file_path)[1].lower()
    mimes = {
        ".mp4": "video/mp4",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo"
    }
    mimetype = mimes.get(ext, "video/mp4")

    # Use Flask's conditional send_file which supports HTTP Range requests natively
    return send_file(
        file_path,
        mimetype=mimetype,
        as_attachment=False,
        conditional=True,
        download_name=os.path.basename(file_path)
    )


@app.route("/api/preview/<filename>")
@app.route("/api/preview_clip/<filename>")
def api_preview_clip(filename):
    """
    Returns a lightweight 5-second 480p preview clip for fast looping in Web Library.
    Downloads in ~10ms and plays natively in memory without blocking HTTP sockets.
    Falls back to streaming video if generation is not available.
    """
    clip_path = scanner.ensure_preview_clip_for_filename(filename)
    if clip_path and os.path.isfile(clip_path):
        return send_file(
            clip_path,
            mimetype="video/mp4",
            as_attachment=False,
            conditional=True,
            download_name=os.path.basename(clip_path)
        )

    # Fallback to streaming the source video
    return api_video(filename)


@app.route("/api/thumbnail/<filename>")
def api_thumbnail(filename):
    name_no_ext, _ = os.path.splitext(filename)
    img_exts = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp"
    }
    for ext, mime in img_exts.items():
        thumb_path = os.path.join(THUMBNAIL_DIR, f"{name_no_ext}{ext}")
        if os.path.isfile(thumb_path):
            return send_file(thumb_path, mimetype=mime)

    # Generate if not exists
    video_path = os.path.join(video_folder, filename)
    if not os.path.isfile(video_path):
        cand_beat = os.path.join(video_folder, f"{name_no_ext}.beat")
        if os.path.isfile(cand_beat):
            video_path = cand_beat

    if os.path.isfile(video_path):
        generated = scanner.ensure_thumbnail(video_path, filename, 10.0)
        if os.path.isfile(generated):
            ext = os.path.splitext(generated)[1].lower()
            return send_file(generated, mimetype=img_exts.get(ext, "image/jpeg"))

    abort(404)


@app.route("/api/cache/stats")
def api_cache_stats():
    """Returns storage metrics and counts for previews, thumbnails, and extracted videos."""
    return jsonify(scanner.get_cache_stats())


@app.route("/api/cache/clean_unused", methods=["POST"])
def api_cache_clean_unused():
    """Prunes orphaned previews, thumbnails, and extracted bundles whose source videos were deleted."""
    res = scanner.clean_unused_cache()
    return jsonify(res)


@app.route("/api/cache/clear_previews", methods=["POST"])
def api_cache_clear_previews():
    """Purges all generated preview clips so they can be regenerated fresh on demand."""
    res = scanner.clear_all_previews()
    return jsonify(res)


@app.route("/api/upload_beat/<filename>", methods=["POST"])
def api_upload_beat(filename):
    """
    Allows uploading and attaching a .beat or .json file to a video.
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "No file selected"}), 400

    orig_name = file.filename
    ext = os.path.splitext(orig_name)[1].lower()
    if ext not in [".beat", ".json"]:
        return jsonify({"success": False, "error": "Only .beat and .json files are supported"}), 400

    # Save into video folder
    dest_path = os.path.join(video_folder, orig_name)
    file.save(dest_path)

    # Verify parsing
    try:
        data = parse_beat_file(dest_path)
        # Rescan
        scanner.scan(force_refresh=True)
        return jsonify({
            "success": True,
            "message": f"Successfully attached {orig_name} ({data['total_beats']} beats)",
            "beat_info": {
                "has_beats": True,
                "beat_filename": orig_name,
                "beat_count": data["total_beats"],
                "zone_count": data["total_zones"],
                "bpm": data["settings"].get("bpm", 120.0),
                "format": data["format"]
            }
        })
    except Exception as e:
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except OSError:
                pass
        return jsonify({"success": False, "error": f"Uploaded file is corrupt or invalid: {str(e)}"}), 400


@app.route("/api/qrcode")
def api_qrcode():
    """Generates PNG QR code for the mobile LAN URL."""
    if not qrcode:
        abort(501)

    lan_ips = get_lan_ips()
    port = request.host.split(":")[-1] if ":" in request.host else "8080"
    url = f"http://{lan_ips[0]}:{port}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=3,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#be2edd", back_color="#0c0c0e")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# ------------------------------------------------------------------------------
# Skin Customization API (.beat skins from web/skins)
# ------------------------------------------------------------------------------

@app.route("/api/skins")
def api_skins():
    """Returns list of available .beat skins from project skin directories."""
    skins = list_skins()
    response = jsonify({
        "success": True,
        "skins_folder": SKINS_DIR,
        "total_skins": len(skins),
        "skins": skins
    })
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/skin/<skin_id>")
def api_skin_detail(skin_id):
    """Returns detailed configuration and asset URLs for a specific skin."""
    skin = get_skin(skin_id)
    if not skin:
        abort(404)
    response = jsonify(skin)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.route("/api/skin/<skin_id>/asset/<path:asset_name>")
def api_skin_asset(skin_id, asset_name):
    """Streams component SVG/image from a skin .beat archive with no-cache headers."""
    res = get_skin_asset(skin_id, asset_name)
    if not res:
        abort(404)
    data, mimetype = res
    response = make_response(data)
    response.headers["Content-Type"] = mimetype
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/video_skin/<filename>")
def api_video_skin(filename):
    """Returns embedded skin if present in video's .beat archive."""
    video_path = os.path.join(video_folder, filename)
    skin = get_video_pack_skin(video_path)
    if not skin:
        return jsonify({"has_pack_skin": False}), 404
    skin["has_pack_skin"] = True
    response = jsonify(skin)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.route("/api/video_skin/<filename>/asset/<path:asset_name>")
def api_video_skin_asset(filename, asset_name):
    """Streams embedded skin component from video's .beat archive."""
    video_path = os.path.join(video_folder, filename)
    res = get_video_pack_skin_asset(video_path, asset_name)
    if not res:
        abort(404)
    data, mimetype = res
    response = make_response(data)
    response.headers["Content-Type"] = mimetype
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ------------------------------------------------------------------------------
# Server Runner
# ------------------------------------------------------------------------------

def create_app(folder: Optional[str] = None):
    global video_folder, scanner
    if folder and os.path.isdir(folder):
        video_folder = os.path.abspath(folder)
        scanner = VideoScanner(video_folder)
    return app


def run_server(host: str = "0.0.0.0", port: int = 8080, folder: Optional[str] = None, debug: bool = False):
    global video_folder, scanner
    if folder and os.path.isdir(folder):
        video_folder = os.path.abspath(folder)
    scanner = VideoScanner(video_folder)

    lan_ips = get_lan_ips()
    print("=" * 65)
    print("        BEATBAR WEB VIEWER (Android & Desktop)")
    print("=" * 65)
    print(f" * Video Folder: {video_folder}")
    print(f" * Local PC URL: http://localhost:{port}")
    print(" * Connect from Android (same Wi-Fi):")
    for ip in lan_ips:
        print(f"   -> http://{ip}:{port}")
    print("=" * 65)

    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Beatbar Web Viewer Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default 8080)")
    parser.add_argument("--folder", default=DEFAULT_VIDEOS_DIR, help="Video directory path")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port, folder=args.folder, debug=args.debug)
