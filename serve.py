#!/usr/bin/env python3
"""
Local Tools server — serves Tools/*.html and runs Python caption/frame jobs.

  python serve.py
  start.cmd

UI: http://127.0.0.1:8765/Tools/
API: POST /api/captions , POST /api/extract-frame
"""

from __future__ import annotations

import json
import mimetypes
import sys
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "Tools"
OUT = ROOT / "out"
SCRIPTS = ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))

HOST = "127.0.0.1"
PORT = 8765


def _json_body(handler: BaseHTTPRequestHandler) -> dict:
  length = int(handler.headers.get("Content-Length") or 0)
  raw = handler.rfile.read(length) if length else b"{}"
  try:
    data = json.loads(raw.decode("utf-8"))
  except json.JSONDecodeError as e:
    raise ValueError(f"Invalid JSON: {e}") from e
  if not isinstance(data, dict):
    raise ValueError("JSON body must be an object")
  return data


def run_captions(payload: dict) -> dict:
  from download_youtube_captions import (
    captions_as_text,
    download_playlist,
    fetch_captions_yt_dlp,
    fetch_youtube_captions,
    parse_playlist_id,
    parse_youtube_id,
  )

  lang = payload.get("lang") or "auto"
  if lang not in ("te", "en", "auto"):
    raise ValueError("lang must be auto, te, or en")
  engine = payload.get("engine") or "innertube"
  if engine not in ("innertube", "yt-dlp"):
    raise ValueError("engine must be innertube or yt-dlp")

  playlist = (payload.get("playlist") or "").strip()
  video = (payload.get("video") or "").strip()
  OUT.mkdir(parents=True, exist_ok=True)
  folder_tag = lang if lang != "auto" else "auto"

  try:
    if playlist:
      playlist_id = parse_playlist_id(playlist)
      if not playlist_id:
        raise ValueError("Enter a YouTube playlist ID or URL (list=…).")
      out_dir = OUT / f"{playlist_id}-{folder_tag}-captions"
      zip_path = download_playlist(playlist, lang, engine, out_dir, int(payload.get("maxVideos") or 80))
      zip_name = f"{playlist_id}-{folder_tag}-captions.zip"
      dest = OUT / zip_name
      src = Path(zip_path)
      if src.resolve() != dest.resolve():
        dest.write_bytes(src.read_bytes())
        try:
          src.unlink(missing_ok=True)
        except OSError:
          pass
      return {
        "ok": True,
        "kind": "playlist",
        "downloadUrl": f"/download/{urllib.parse.quote(dest.name)}",
        "filename": dest.name,
        "message": f"Playlist zip ready: {dest.name}",
      }

    if not video:
      raise ValueError("Provide video or playlist.")
    video_id = parse_youtube_id(video)
    if not video_id:
      raise ValueError("Enter a YouTube video ID or URL.")

    if engine == "yt-dlp":
      cues, used_lang = fetch_captions_yt_dlp(video_id, lang, ROOT / ".yt-dlp-cache" / video_id)
    else:
      cues, used_lang = fetch_youtube_captions(video_id, lang)
    text = captions_as_text(cues)
    filename = f"{video_id}-{used_lang}-captions.txt"
    dest = OUT / filename
    dest.write_text(text, encoding="utf-8", newline="\n")
    return {
      "ok": True,
      "kind": "video",
      "downloadUrl": f"/download/{urllib.parse.quote(filename)}",
      "filename": filename,
      "cueCount": len(cues),
      "language": used_lang,
      "preview": "\n".join(text.splitlines()[:12]),
      "message": f"Downloaded {len(cues)} caption lines ({used_lang}).",
    }
  except SystemExit as e:
    raise ValueError(str(e) if e.args else "Caption download failed.") from e


def run_extract_frame(payload: dict) -> dict:
  from extract_youtube_frame import (
    extract_frame,
    extract_youtube_id,
    format_hms_label,
    parse_timestamp,
  )

  video = (payload.get("video") or "").strip()
  time = (payload.get("time") or "").strip()
  fmt = payload.get("format") or "jpg"
  if not video or not time:
    raise ValueError("video and time are required.")

  vid = extract_youtube_id(video)
  if not vid:
    raise ValueError("Enter a YouTube video ID or URL.")
  seconds = parse_timestamp(time)
  if not (seconds == seconds) or seconds < 0:
    raise ValueError("Enter a valid time (e.g. 00:01:30 or 90).")
  fmt = "png" if fmt == "png" else "jpg"
  filename = f"yt_{vid}_{format_hms_label(seconds)}.{fmt}"
  OUT.mkdir(parents=True, exist_ok=True)
  dest = OUT / filename
  try:
    extract_frame(video, time, fmt, dest)
  except SystemExit as e:
    raise ValueError(str(e) if e.args else "Frame extract failed.") from e

  return {
    "ok": True,
    "downloadUrl": f"/download/{urllib.parse.quote(filename)}",
    "filename": filename,
    "message": f"Frame saved: {filename}",
  }


class Handler(BaseHTTPRequestHandler):
  server_version = "QLUNewsletterTools/1.0"

  def log_message(self, fmt: str, *args) -> None:
    sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

  def _cors(self) -> None:
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")

  def _send_json(self, code: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    self.send_response(code)
    self._cors()
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)

  def _send_bytes(self, code: int, data: bytes, content_type: str, filename: str | None = None) -> None:
    self.send_response(code)
    self._cors()
    self.send_header("Content-Type", content_type)
    self.send_header("Content-Length", str(len(data)))
    if filename:
      self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    self.end_headers()
    self.wfile.write(data)

  def do_OPTIONS(self) -> None:
    self.send_response(204)
    self._cors()
    self.end_headers()

  def do_GET(self) -> None:
    parsed = urllib.parse.urlparse(self.path)
    path = urllib.parse.unquote(parsed.path)

    if path in ("/", "/Tools", "/Tools/"):
      self.send_response(302)
      self.send_header("Location", "/Tools/index.html")
      self.end_headers()
      return

    if path == "/api/health":
      self._send_json(200, {"ok": True, "out": str(OUT)})
      return

    if path.startswith("/download/"):
      name = path[len("/download/") :]
      # prevent path traversal
      safe = Path(name).name
      file_path = OUT / safe
      if not file_path.is_file():
        self._send_json(404, {"ok": False, "error": "File not found. Run a job first."})
        return
      data = file_path.read_bytes()
      ctype = mimetypes.guess_type(safe)[0] or "application/octet-stream"
      self._send_bytes(200, data, ctype, safe)
      return

    # Static files from Tools/ or repo root README
    if path.startswith("/Tools/"):
      rel = path[len("/Tools/") :]
      target = (TOOLS / rel).resolve()
      if not str(target).startswith(str(TOOLS.resolve())) or not target.is_file():
        self._send_json(404, {"ok": False, "error": "Not found"})
        return
      data = target.read_bytes()
      ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
      if target.suffix.lower() == ".html":
        ctype = "text/html; charset=utf-8"
      self._send_bytes(200, data, ctype)
      return

    if path == "/README.md" and (ROOT / "README.md").is_file():
      data = (ROOT / "README.md").read_bytes()
      self._send_bytes(200, data, "text/markdown; charset=utf-8")
      return

    self._send_json(404, {"ok": False, "error": f"No route for {path}"})

  def do_POST(self) -> None:
    parsed = urllib.parse.urlparse(self.path)
    path = parsed.path
    try:
      payload = _json_body(self)
      if path == "/api/captions":
        result = run_captions(payload)
        self._send_json(200, result)
        return
      if path == "/api/extract-frame":
        result = run_extract_frame(payload)
        self._send_json(200, result)
        return
      self._send_json(404, {"ok": False, "error": f"No API {path}"})
    except (ValueError, RuntimeError, OSError) as e:
      traceback.print_exc()
      self._send_json(400, {"ok": False, "error": str(e) or e.__class__.__name__})
    except Exception as e:
      traceback.print_exc()
      self._send_json(500, {"ok": False, "error": str(e) or e.__class__.__name__})


def main(argv: list[str] | None = None) -> None:
  import argparse

  parser = argparse.ArgumentParser(description="QLU Newsletter Tools local server")
  parser.add_argument("--host", default=HOST)
  parser.add_argument("--port", type=int, default=PORT)
  parser.add_argument("--no-browser", action="store_true", help="Do not open a browser tab")
  args = parser.parse_args(argv)

  OUT.mkdir(parents=True, exist_ok=True)
  if not TOOLS.is_dir():
    raise SystemExit(f"Missing Tools folder: {TOOLS}")

  server = ThreadingHTTPServer((args.host, args.port), Handler)
  url = f"http://{args.host}:{args.port}/Tools/index.html"
  print(f"QLU Newsletter Tools → {url}")
  print(f"Outputs → {OUT}")
  print("Press Ctrl+C to stop.")
  if not args.no_browser:
    try:
      webbrowser.open(url)
    except Exception:
      pass
  try:
    server.serve_forever()
  except KeyboardInterrupt:
    print("\nStopped.")
    server.server_close()


if __name__ == "__main__":
  main()

