#!/usr/bin/env python3
"""
Extract one still frame from a YouTube video at a timestamp.

Same idea as quantum-life-university lib/tools/youtubeFrame.ts
(and Tools → Extract frame at time).

Requires: yt-dlp (auto-pip if missing) + ffmpeg on PATH
  (or YT_DLP_PATH / FFMPEG_PATH env vars).

Examples:
  python scripts/extract_youtube_frame.py VIDEO_ID --time 00:01:30
  python scripts/extract_youtube_frame.py https://youtu.be/VIDEO_ID -t 90 -o out/frame.jpg
  python scripts/extract_youtube_frame.py VIDEO_ID -t 1:05 --format png
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VIDEO_ID_RE = re.compile(
  r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)?([a-zA-Z0-9_-]{11})"
)


def extract_youtube_id(value: str) -> str | None:
  trimmed = value.strip()
  if re.fullmatch(r"[a-zA-Z0-9_-]{11}", trimmed):
    return trimmed
  m = VIDEO_ID_RE.search(trimmed)
  return m.group(1) if m else None


def parse_timestamp(ts: str) -> float:
  raw = ts.strip().replace(",", ".")
  if not raw:
    return float("nan")
  parts = raw.split(":")
  try:
    if len(parts) == 3:
      return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
      return float(parts[0]) * 60 + float(parts[1])
    return float(parts[0])
  except ValueError:
    return float("nan")


def format_hms_label(seconds: float) -> str:
  total = max(0, int(round(seconds)))
  h, rem = divmod(total, 3600)
  m, s = divmod(rem, 60)
  return f"{h:02d}h{m:02d}m{s:02d}s"


def safe_title_slug(title: str, max_len: int = 100) -> str:
  """Filesystem-safe slug; keep trailing Day-NNN when truncating (same as captions)."""
  try:
    from download_youtube_captions import safe_title_slug as _slug

    return _slug(title, max_len)
  except Exception:
    pass
  slug = (title or "").strip()
  slug = re.sub(r'[\\/:*?"<>|]+', "", slug)
  slug = re.sub(r"\s+", "-", slug)
  slug = re.sub(r"-{2,}", "-", slug).strip(".- ")
  if len(slug) > max_len:
    day_m = re.search(r"(?i)(-Day-\d+)$", slug)
    if day_m:
      suffix = day_m.group(1)
      head_len = max_len - len(suffix)
      if head_len >= 12:
        slug = slug[:head_len].rstrip("-.") + suffix
      else:
        slug = slug[:max_len].rstrip("-.")
    else:
      slug = slug[:max_len].rstrip("-.")
  return slug or "video"


def safe_frame_filename(video_id: str, title: str, seconds: float, fmt: str) -> str:
  """{actual-title}[{videoId}]_00h59m51s.jpg — same idea as caption naming."""
  label = safe_title_slug(title)
  ext = "png" if fmt == "png" else "jpg"
  return f"{label}[{video_id}]_{format_hms_label(seconds)}.{ext}"


def fetch_video_title(video_id: str, yt_dlp_cmd: list[str] | None = None) -> str:
  """Prefer Innertube (same as captions); fall back to yt-dlp --print title."""
  try:
    from download_youtube_captions import fetch_video_title as innertube_title

    title = innertube_title(video_id)
    if title and title != video_id:
      return title
  except Exception:
    pass

  cmd = yt_dlp_cmd or ensure_yt_dlp_cmd()
  result = run(
    [
      *cmd,
      "--skip-download",
      "--no-warnings",
      "--print",
      "%(title)s",
      f"https://www.youtube.com/watch?v={video_id}",
    ],
    timeout=60,
  )
  if result.returncode == 0:
    lines = [ln.strip() for ln in (result.stdout or "").splitlines() if ln.strip()]
    if lines:
      return lines[0]
  return video_id


def _can_run(cmd: list[str], probe_args: list[str]) -> bool:
  try:
    r = subprocess.run(cmd + probe_args, capture_output=True, timeout=15)
    return r.returncode == 0
  except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
    # OSError includes WinError 193 (not a valid Win32 application)
    return False


def resolve_ffmpeg() -> str:
  """Return a working ffmpeg executable path."""
  from_env = (os.environ.get("FFMPEG_PATH") or "").strip()
  candidates: list[str] = []
  if from_env:
    candidates.append(from_env)
  for name in ("ffmpeg.exe", "ffmpeg"):
    found = shutil.which(name)
    if found:
      candidates.append(found)
  for path in candidates:
    if _can_run([path], ["-version"]):
      return path
  raise RuntimeError(
    "ffmpeg not found (or not a valid Windows binary). "
    "Install it and ensure it is on PATH, or set FFMPEG_PATH to ffmpeg.exe. "
    "Example: winget install Gyan.FFmpeg"
  )


def ensure_yt_dlp_cmd() -> list[str]:
  """
  Return argv prefix to run yt-dlp.
  Prefer `python -m yt_dlp` on Windows to avoid WinError 193 from a bad/non-exe
  file named yt-dlp (e.g. a Downloads copy or a Unix script without .exe).
  """
  from_env = (os.environ.get("YT_DLP_PATH") or "").strip()
  if from_env:
    if _can_run([from_env], ["--version"]):
      return [from_env]
    raise RuntimeError(
      f"YT_DLP_PATH is set but not runnable on Windows: {from_env}\n"
      "Point it at yt-dlp.exe, or unset it to use `python -m yt_dlp`."
    )

  module_cmd = [sys.executable, "-m", "yt_dlp"]
  if _can_run(module_cmd, ["--version"]):
    return module_cmd

  print("yt-dlp module not found — installing with pip…", file=sys.stderr)
  subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"])
  if _can_run(module_cmd, ["--version"]):
    return module_cmd

  # Last resort: PATH yt-dlp.exe only (skip extensionless names that break on Win)
  for name in ("yt-dlp.exe", "yt-dlp"):
    found = shutil.which(name)
    if found and _can_run([found], ["--version"]):
      return [found]

  raise RuntimeError("Could not run yt-dlp after install. Try: python -m pip install -U yt-dlp")


def run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
  try:
    # UTF-8: yt-dlp titles/errors often include Telugu; default cp1252 crashes on Windows.
    return subprocess.run(
      cmd,
      capture_output=True,
      text=True,
      encoding="utf-8",
      errors="replace",
      timeout=timeout,
    )
  except OSError as e:
    raise RuntimeError(
      f"Failed to start command ({e}). "
      "On Windows this is often a bad yt-dlp/ffmpeg binary — use python -m yt_dlp and a real ffmpeg.exe."
    ) from e


def youtube_stream_url(watch_url: str, yt_dlp_cmd: list[str]) -> str:
  result = run(
    [
      *yt_dlp_cmd,
      "--no-playlist",
      "--no-warnings",
      "-f",
      "bestvideo[height<=1080]/best[height<=1080]/best",
      "-g",
      watch_url,
    ],
    timeout=90,
  )
  if result.returncode != 0:
    raise RuntimeError((result.stderr or result.stdout or "yt-dlp failed to resolve the stream.").strip())
  lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
  if not lines:
    raise RuntimeError("yt-dlp returned no stream URL.")
  return lines[0]


def extract_frame(video_input: str, time: str, fmt: str, out: Path | None) -> Path:
  video_id = extract_youtube_id(video_input)
  if not video_id:
    raise SystemExit("Enter a YouTube video ID or URL.")
  seconds = parse_timestamp(time)
  if not (seconds == seconds) or seconds < 0:  # NaN check
    raise SystemExit("Enter a valid time (e.g. 00:01:30 or 90).")

  fmt = "png" if fmt == "png" else "jpg"
  yt_dlp_cmd = ensure_yt_dlp_cmd()
  try:
    ffmpeg = resolve_ffmpeg()
  except RuntimeError as e:
    raise SystemExit(str(e)) from e

  watch_url = f"https://www.youtube.com/watch?v={video_id}"
  stream_url = youtube_stream_url(watch_url, yt_dlp_cmd)

  if out is None:
    title = fetch_video_title(video_id, yt_dlp_cmd)
    dest = Path(safe_frame_filename(video_id, title, seconds, fmt))
  else:
    dest = out
  dest.parent.mkdir(parents=True, exist_ok=True)

  with tempfile.TemporaryDirectory(prefix="qlu-yt-frame-") as work:
    tmp = Path(work) / f"frame.{fmt}"
    ff_args = [
      ffmpeg,
      "-hide_banner",
      "-loglevel",
      "error",
      "-y",
      "-ss",
      f"{seconds:.3f}",
      "-i",
      stream_url,
      "-frames:v",
      "1",
    ]
    if fmt == "jpg":
      ff_args += ["-q:v", "2"]
    ff_args.append(str(tmp))
    ff = run(ff_args, timeout=120)
    if ff.returncode != 0:
      raise RuntimeError((ff.stderr or "ffmpeg failed to extract the frame.").strip())
    if not tmp.is_file() or tmp.stat().st_size == 0:
      raise RuntimeError("Extracted frame was empty.")
    dest.write_bytes(tmp.read_bytes())

  print(f"Wrote {dest} ({video_id} @ {seconds:.3f}s)")
  return dest


def main() -> None:
  parser = argparse.ArgumentParser(description="Extract one YouTube frame at a timestamp (yt-dlp + ffmpeg).")
  parser.add_argument("video", help="YouTube video ID or URL")
  parser.add_argument("-t", "--time", required=True, help="Timestamp: HH:MM:SS, MM:SS, or seconds")
  parser.add_argument("--format", choices=("jpg", "png"), default="jpg")
  parser.add_argument("-o", "--out", type=Path, help="Output image path")
  args = parser.parse_args()
  try:
    extract_frame(args.video, args.time, args.format, args.out)
  except RuntimeError as e:
    raise SystemExit(str(e)) from e


if __name__ == "__main__":
  main()
