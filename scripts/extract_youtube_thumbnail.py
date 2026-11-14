#!/usr/bin/env python3
"""
Download the original high-quality YouTube thumbnail for a video (or playlist).

Naming matches extract-frame (title + video id), with a `_thumb` suffix:
  {title-slug}[{videoId}]_thumb.jpg

Examples:
  python scripts/extract_youtube_thumbnail.py VIDEO_ID
  python scripts/extract_youtube_thumbnail.py VIDEO_ID -o out/thumb.jpg
  python scripts/extract_youtube_thumbnail.py --playlist PLxxxx -o out/thumbs
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from extract_youtube_frame import (  # noqa: E402
  ensure_yt_dlp_cmd,
  extract_youtube_id,
  fetch_video_title,
  run,
  safe_title_slug,
)

# Prefer original max-res poster, then fall back.
THUMB_CANDIDATES = (
  "maxresdefault.jpg",
  "sddefault.jpg",
  "hqdefault.jpg",
  "mqdefault.jpg",
  "default.jpg",
)

UA = (
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def safe_thumb_filename(video_id: str, title: str, *, ext: str = "jpg") -> str:
  """{actual-title}[{videoId}]_thumb.jpg — same base as frame extract naming."""
  label = safe_title_slug(title)
  ext = (ext or "jpg").lstrip(".").lower()
  if ext not in ("jpg", "jpeg", "png", "webp"):
    ext = "jpg"
  if ext == "jpeg":
    ext = "jpg"
  return f"{label}[{video_id}]_thumb.{ext}"


def _http_get(url: str, timeout: int = 45) -> bytes | None:
  req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/*,*/*"})
  try:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
      data = resp.read()
      if not data or len(data) < 800:
        # YouTube sometimes returns a tiny placeholder for missing maxres
        return None
      ctype = (resp.headers.get("Content-Type") or "").lower()
      if "image" not in ctype and not url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        return None
      return data
  except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
    return None


def download_thumbnail_bytes(video_id: str) -> tuple[bytes, str]:
  """
  Return (image_bytes, quality_label).
  Tries i.ytimg.com maxres → sd → hq, then yt-dlp --write-thumbnail.
  """
  for name in THUMB_CANDIDATES:
    url = f"https://i.ytimg.com/vi/{video_id}/{name}"
    data = _http_get(url)
    if data:
      return data, name.replace(".jpg", "")

  # Fallback: let yt-dlp pick the best available thumbnail asset
  yt = ensure_yt_dlp_cmd()
  import tempfile

  with tempfile.TemporaryDirectory(prefix="qlu-yt-thumb-") as work:
    work_path = Path(work)
    outtmpl = str(work_path / "thumb.%(ext)s")
    result = run(
      [
        *yt,
        "--skip-download",
        "--no-playlist",
        "--no-warnings",
        "--write-thumbnail",
        "--convert-thumbnails",
        "jpg",
        "-o",
        outtmpl,
        f"https://www.youtube.com/watch?v={video_id}",
      ],
      timeout=90,
    )
    if result.returncode != 0:
      raise RuntimeError(
        (result.stderr or result.stdout or "yt-dlp thumbnail download failed.").strip()
      )
    files = sorted(work_path.glob("thumb.*"))
    if not files:
      # yt-dlp may write {id}.jpg beside outtmpl in some versions
      files = sorted(p for p in work_path.iterdir() if p.is_file())
    if not files:
      raise RuntimeError("No thumbnail file was written.")
    data = files[0].read_bytes()
    if not data:
      raise RuntimeError("Thumbnail file was empty.")
    return data, "yt-dlp"


def extract_thumbnail(video_input: str, out: Path | None = None) -> Path:
  video_id = extract_youtube_id(video_input)
  if not video_id:
    raise SystemExit("Enter a YouTube video ID or URL.")

  title = fetch_video_title(video_id)
  data, quality = download_thumbnail_bytes(video_id)

  if out is None:
    dest = Path(safe_thumb_filename(video_id, title))
  else:
    dest = out
    if dest.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
      dest = dest.with_suffix(".jpg")

  dest.parent.mkdir(parents=True, exist_ok=True)
  dest.write_bytes(data)
  print(f"Wrote {dest} ({video_id} · {quality})")
  return dest


def extract_playlist_thumbnails(
  playlist_input: str,
  out_dir: Path,
  *,
  max_videos: int = 80,
) -> dict:
  from download_youtube_captions import fetch_playlist_videos, parse_playlist_id
  from pick_best_portrait_frame import zip_paths

  playlist_id = parse_playlist_id(playlist_input)
  if not playlist_id:
    raise SystemExit("Enter a YouTube playlist ID or URL.")

  videos = fetch_playlist_videos(playlist_id, preferred="te", max_videos=max_videos)
  if not videos:
    raise SystemExit("No videos found in that playlist.")

  out_dir.mkdir(parents=True, exist_ok=True)
  files: list[Path] = []
  failures: list[str] = []

  for row in videos:
    vid = (row.get("videoId") or "").strip()
    if not vid:
      continue
    title = (row.get("title") or vid).strip()
    dest = out_dir / safe_thumb_filename(vid, title)
    try:
      data, quality = download_thumbnail_bytes(vid)
      dest.write_bytes(data)
      files.append(dest)
      print(f"  ✓ {dest.name} ({quality})")
    except Exception as e:
      failures.append(f"{vid}: {e}")
      print(f"  ✗ {vid}: {e}", file=sys.stderr)

  if not files:
    raise SystemExit("No thumbnails downloaded.")

  zip_name = f"{playlist_id}-thumbnails.zip"
  zip_path = out_dir / zip_name
  zip_paths(files, zip_path)
  return {
    "playlistId": playlist_id,
    "zip": zip_path,
    "files": files,
    "failures": failures,
  }


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Download original HQ YouTube thumbnail(s) with extract-frame naming.",
  )
  parser.add_argument("video", nargs="?", default="", help="YouTube video ID or URL")
  parser.add_argument("--playlist", default="", help="Playlist ID or URL → zip of thumbs")
  parser.add_argument("-o", "--out", type=Path, help="Output file (video) or folder (playlist)")
  parser.add_argument("--max-videos", type=int, default=80, help="Playlist cap (default 80)")
  args = parser.parse_args()

  try:
    if (args.playlist or "").strip():
      out_dir = args.out or Path("out") / "thumbnails"
      if out_dir.suffix:
        out_dir = out_dir.parent / out_dir.stem
      result = extract_playlist_thumbnails(
        args.playlist,
        out_dir,
        max_videos=max(1, min(200, args.max_videos)),
      )
      print(f"Zip: {result['zip']} ({len(result['files'])} thumbs)")
      return

    if not (args.video or "").strip():
      raise SystemExit("Provide a video ID/URL or --playlist.")
    extract_thumbnail(args.video, args.out)
  except RuntimeError as e:
    raise SystemExit(str(e)) from e


if __name__ == "__main__":
  main()
