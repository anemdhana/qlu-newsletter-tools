#!/usr/bin/env python3
"""
Local Tools server — serves Tools/*.html and runs Python caption/frame/whisper jobs.

  python serve.py
  start.cmd

UI: http://127.0.0.1:8765/Tools/
API: POST /api/captions , POST /api/extract-frame , POST /api/pick-portrait , POST /api/whisper
"""

from __future__ import annotations

import json
import mimetypes
import re
import sys
import tempfile
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
# Mic / lecture clips can be large; Whisper can take minutes on CPU.
MAX_UPLOAD_BYTES = 80 * 1024 * 1024


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


def _parse_multipart(handler: BaseHTTPRequestHandler) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
  """Minimal multipart/form-data parser → (fields, files{name: (filename, bytes)})."""
  ctype = handler.headers.get("Content-Type") or ""
  m = re.search(r"boundary=([^;]+)", ctype, flags=re.I)
  if not m:
    raise ValueError("Expected multipart/form-data with boundary")
  boundary = m.group(1).strip().strip('"').encode("ascii", "ignore")
  length = int(handler.headers.get("Content-Length") or 0)
  if length <= 0:
    raise ValueError("Empty upload")
  if length > MAX_UPLOAD_BYTES:
    raise ValueError(f"Upload too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)")
  body = handler.rfile.read(length)
  sep = b"--" + boundary
  fields: dict[str, str] = {}
  files: dict[str, tuple[str, bytes]] = {}
  for part in body.split(sep):
    if not part or part in (b"--\r\n", b"--", b"--\n"):
      continue
    if part.startswith(b"\r\n"):
      part = part[2:]
    if part.endswith(b"\r\n"):
      part = part[:-2]
    if part == b"--":
      continue
    header_blob, _, content = part.partition(b"\r\n\r\n")
    if not _:
      header_blob, _, content = part.partition(b"\n\n")
    if content.endswith(b"\r\n"):
      content = content[:-2]
    elif content.endswith(b"\n"):
      content = content[:-1]
    headers = header_blob.decode("utf-8", "replace")
    name_m = re.search(r'name="([^"]+)"', headers)
    if not name_m:
      continue
    name = name_m.group(1)
    file_m = re.search(r'filename="([^"]*)"', headers)
    if file_m is not None:
      files[name] = (file_m.group(1) or "audio.bin", content)
    else:
      fields[name] = content.decode("utf-8", "replace")
  return fields, files


def run_captions(payload: dict) -> dict:
  from download_youtube_captions import (
    captions_as_text,
    download_playlist,
    fetch_captions_yt_dlp,
    fetch_video_title,
    fetch_youtube_captions,
    parse_playlist_id,
    parse_youtube_id,
    safe_caption_filename,
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

    title = fetch_video_title(video_id)
    if engine == "yt-dlp":
      cues, used_lang = fetch_captions_yt_dlp(video_id, lang, ROOT / ".yt-dlp-cache" / video_id)
    else:
      cues, used_lang = fetch_youtube_captions(video_id, lang)
    text = captions_as_text(cues)
    if title and title != video_id:
      text = (
        f"# {title}\n"
        f"# https://www.youtube.com/watch?v={video_id}\n"
        f"# language={used_lang}\n\n"
        f"{text}"
      )
    filename = safe_caption_filename(None, video_id, title, used_lang)
    dest = OUT / filename
    dest.write_text(text, encoding="utf-8", newline="\n")
    return {
      "ok": True,
      "kind": "video",
      "downloadUrl": f"/download/{urllib.parse.quote(filename)}",
      "filename": filename,
      "title": title,
      "cueCount": len(cues),
      "language": used_lang,
      "preview": "\n".join(text.splitlines()[:12]),
      "message": f"Downloaded {len(cues)} caption lines ({used_lang}) · {filename}",
    }
  except SystemExit as e:
    raise ValueError(str(e) if e.args else "Caption download failed.") from e


def run_extract_frame(payload: dict) -> dict:
  from extract_youtube_frame import (
    extract_frame,
    extract_youtube_id,
    fetch_video_title,
    parse_timestamp,
    safe_frame_filename,
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
  title = fetch_video_title(vid)
  filename = safe_frame_filename(vid, title, seconds, fmt)
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
    "title": title,
    "message": f"Frame saved: {filename}",
  }


def run_pick_portrait(payload: dict) -> dict:
  from pick_best_portrait_frame import (
    pick_best_portraits,
    pick_playlist_portraits,
    zip_paths,
  )

  playlist = (payload.get("playlist") or "").strip()
  video = (payload.get("video") or "").strip()
  fmt = "png" if payload.get("format") == "png" else "jpg"
  try:
    top = max(1, min(10, int(payload.get("top") or 1)))
  except (TypeError, ValueError) as e:
    raise ValueError("top must be an integer 1–10.") from e
  from extract_youtube_frame import parse_timestamp

  # Sample interval: prefer minutes from UI; fall back to seconds for CLI/API compat.
  interval = None
  raw_min = payload.get("intervalMin")
  if raw_min is not None and str(raw_min).strip() != "":
    try:
      interval = float(raw_min) * 60.0
    except (TypeError, ValueError) as e:
      raise ValueError("intervalMin must be minutes (e.g. 1).") from e
  elif payload.get("interval") is not None and str(payload.get("interval")).strip() != "":
    try:
      interval = float(payload.get("interval"))
    except (TypeError, ValueError) as e:
      raise ValueError("interval must be a number of seconds.") from e
  else:
    interval = 60.0  # default: every 1 minute
  if interval <= 0 or interval > 30 * 60:
    raise ValueError("Sample interval must be between 0 and 30 minutes.")

  def _parse_clock(raw, *, default: float | None, label: str) -> float | None:
    if raw is None or str(raw).strip() == "":
      return default
    text = str(raw).strip().lower()
    if text in ("end", "inf", "none"):
      return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
      value = float(raw)
    else:
      value = parse_timestamp(str(raw).strip())
    if not (value == value) or value < 0:
      raise ValueError(f"Enter a valid {label} (e.g. 00:45:00).")
    return value

  # Window defaults: 00:45:00 → 01:15:00 (~30 min) so jobs finish quickly.
  skip_start = _parse_clock(
    payload.get("startTime") if payload.get("startTime") not in (None, "") else payload.get("skipStart"),
    default=45 * 60,
    label="start time",
  )
  assert skip_start is not None
  end_at = _parse_clock(
    payload.get("endTime"),
    default=75 * 60,
    label="end time",
  )
  if end_at is not None and end_at <= skip_start:
    raise ValueError("End time must be after start time.")

  try:
    skip_end = float(payload.get("skipEnd") if payload.get("skipEnd") is not None else 15)
  except (TypeError, ValueError) as e:
    raise ValueError("skipEnd must be a number.") from e
  try:
    max_videos = max(1, min(200, int(payload.get("maxVideos") or 80)))
  except (TypeError, ValueError) as e:
    raise ValueError("maxVideos must be an integer.") from e

  OUT.mkdir(parents=True, exist_ok=True)
  out_dir = OUT / "portrait-picks"
  out_dir.mkdir(parents=True, exist_ok=True)

  try:
    if playlist:
      result = pick_playlist_portraits(
        playlist,
        out_dir=out_dir,
        interval=interval,
        skip_start=skip_start,
        end_at=end_at,
        skip_end=skip_end,
        top=top,
        fmt=fmt,
        max_videos=max_videos,
      )
      zip_path = Path(result["zip"])
      # Ensure zip lives under OUT for /download/
      dest = OUT / zip_path.name
      if zip_path.resolve() != dest.resolve():
        dest.write_bytes(zip_path.read_bytes())
      return {
        "ok": True,
        "kind": "playlist",
        "downloadUrl": f"/download/{urllib.parse.quote(dest.name)}",
        "filename": dest.name,
        "playlistId": result.get("playlistId"),
        "frameCount": len(result.get("files") or []),
        "message": (
          f"Playlist zip ready: {dest.name} "
          f"({len(result.get('files') or [])} frames"
          f"{', ' + str(len(result['failures'])) + ' failed' if result.get('failures') else ''})"
        ),
      }

    if not video:
      raise ValueError("Provide video or playlist.")

    result = pick_best_portraits(
      video,
      out_dir=out_dir,
      interval=interval,
      skip_start=skip_start,
      end_at=end_at,
      skip_end=skip_end,
      top=top,
      fmt=fmt,
      write_report=True,
    )
    files = [Path(p) for p in (result.get("files") or [])]
    if not files:
      raise ValueError("No portrait frames were produced.")

    # Mirror winners into OUT root so /download/ works (same as extract-frame).
    mirrored: list[Path] = []
    for src in files:
      dest = OUT / src.name
      if src.resolve() != dest.resolve():
        dest.write_bytes(src.read_bytes())
      mirrored.append(dest)

    if len(mirrored) == 1:
      filename = mirrored[0].name
      return {
        "ok": True,
        "kind": "video",
        "downloadUrl": f"/download/{urllib.parse.quote(filename)}",
        "previewUrl": f"/download/{urllib.parse.quote(filename)}",
        "filename": filename,
        "title": result.get("title"),
        "picks": result.get("picks"),
        "message": f"Best portrait: {filename}",
      }

    # Multiple tops for one video → zip (same pattern as playlist).
    vid = result.get("videoId") or "video"
    zip_name = f"{vid}-portrait-picks.zip"
    zip_dest = OUT / zip_name
    zip_paths(mirrored, zip_dest)
    preview = mirrored[0].name
    return {
      "ok": True,
      "kind": "video",
      "downloadUrl": f"/download/{urllib.parse.quote(zip_name)}",
      "previewUrl": f"/download/{urllib.parse.quote(preview)}",
      "filename": zip_name,
      "title": result.get("title"),
      "picks": result.get("picks"),
      "message": f"Top {len(mirrored)} portraits zipped: {zip_name}",
    }
  except SystemExit as e:
    raise ValueError(str(e) if e.args else "Portrait pick failed.") from e


def whisper_status() -> dict:
  try:
    import faster_whisper  # noqa: F401

    installed = True
    detail = getattr(faster_whisper, "__version__", "installed")
  except Exception as e:
    installed = False
    detail = str(e)
  ffmpeg = None
  try:
    from whisper_transcribe import ensure_ffmpeg_on_path

    ffmpeg = ensure_ffmpeg_on_path()
  except Exception:
    pass
  return {
    "ok": True,
    "fasterWhisper": installed,
    "fasterWhisperDetail": detail,
    "ffmpeg": bool(ffmpeg),
    "ffmpegPath": ffmpeg,
    "defaultModel": "small",
    "maxUploadMb": MAX_UPLOAD_BYTES // (1024 * 1024),
  }


def run_whisper_upload(fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> dict:
  from whisper_transcribe import safe_out_name, transcribe_audio

  if "audio" not in files:
    raise ValueError("Upload an audio file field named “audio”.")
  filename, data = files["audio"]
  if not data:
    raise ValueError("Audio file is empty.")

  lang = (fields.get("lang") or "te").strip()
  model = (fields.get("model") or "small").strip() or "small"
  extra = (fields.get("extraPrompt") or "").strip() or None
  allowed = {"tiny", "base", "small", "medium", "large-v3"}
  if model not in allowed:
    raise ValueError(f"model must be one of: {', '.join(sorted(allowed))}")

  suffix = Path(filename).suffix.lower() or ".webm"
  if suffix not in {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".mp4", ".mpeg", ".mpga"}:
    suffix = ".webm"

  OUT.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix="qlu-whisper-") as tmp:
    audio_path = Path(tmp) / f"upload{suffix}"
    audio_path.write_bytes(data)
    result = transcribe_audio(
      audio_path,
      lang=lang,
      model_size=model,
      extra_prompt=extra,
      use_cache=True,
    )

  stem = Path(filename).stem or "recording"
  out_name = safe_out_name(stem, lang)
  dest = OUT / out_name
  dest.write_text(result["text"] + "\n", encoding="utf-8", newline="\n")
  text = (result.get("text") or "").strip()
  preview_lines = text.splitlines()[:16]
  return {
    "ok": True,
    "text": text,
    "language": result["language"],
    "duration": result["duration"],
    "segmentCount": len(result["segments"]),
    "model": result["model"],
    "downloadUrl": f"/download/{urllib.parse.quote(out_name)}" if text else "",
    "filename": out_name if text else "",
    "preview": "\n".join(preview_lines),
    "message": (
      f"Whisper done · {result['language']} · ~{result['duration']}s · "
      f"{len(result['segments'])} segments · {out_name}"
      if text
      else (
        f"Whisper finished but found no speech (~{result['duration']}s). "
        "Speak louder / longer with the level bar moving."
      )
    ),
  }


class Handler(BaseHTTPRequestHandler):
  server_version = "QLUNewsletterTools/1.0"
  # Whisper on CPU can exceed the default socket idle assumptions; keep generous.
  timeout = 60 * 30

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
      # HTTP headers are latin-1; use ASCII fallback + RFC 5987 UTF-8 filename*
      ascii_name = filename.encode("ascii", "ignore").decode("ascii").strip(" .-_") or "download"
      if not Path(ascii_name).suffix and Path(filename).suffix:
        ascii_name += Path(filename).suffix
      starred = urllib.parse.quote(filename, safe="")
      self.send_header(
        "Content-Disposition",
        f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{starred}",
      )
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

    if path == "/api/whisper/status":
      self._send_json(200, whisper_status())
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
      if path == "/api/whisper":
        fields, files = _parse_multipart(self)
        result = run_whisper_upload(fields, files)
        self._send_json(200, result)
        return

      payload = _json_body(self)
      if path == "/api/captions":
        result = run_captions(payload)
        self._send_json(200, result)
        return
      if path == "/api/extract-frame":
        result = run_extract_frame(payload)
        self._send_json(200, result)
        return
      if path == "/api/pick-portrait":
        result = run_pick_portrait(payload)
        self._send_json(200, result)
        return
      self._send_json(404, {"ok": False, "error": f"No API {path}"})
    except (ValueError, RuntimeError, OSError, FileNotFoundError) as e:
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

