#!/usr/bin/env python3
"""
Pick the best portrait / smile stills from a YouTube video.

Clone of extract_youtube_frame.py workflow, with three steps:

  1) Sample frames across the talk (yt-dlp download + ffmpeg fps sampling)
  2) Score each still (face + smile via OpenCV Haar; sharpness fallback)
  3) Keep the top candidates (default 3) with timestamps

Examples:
  python scripts/pick_best_portrait_frame.py VIDEO_ID
  python scripts/pick_best_portrait_frame.py https://youtu.be/VIDEO_ID -o out\\portraits --top 5
  python scripts/pick_best_portrait_frame.py --playlist PLxxxx -o out\\portraits --top 1

Requires: yt-dlp + ffmpeg (same as extract_youtube_frame.py).
Optional but recommended: pip install opencv-python-headless

Image names match extract-frame: {title}[{videoId}]_00h01m30s.jpg
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

# Reuse helpers from the single-frame extract script (same folder).
from extract_youtube_frame import (  # noqa: E402
  ensure_yt_dlp_cmd,
  extract_youtube_id,
  fetch_video_title,
  resolve_ffmpeg,
  run,
  safe_frame_filename,
  youtube_stream_url,
)


@dataclass
class ScoredFrame:
  path: str
  seconds: float
  score: float
  faces: int
  smiles: int
  sharpness: float
  reason: str


YUNET_URL = (
  "https://github.com/opencv/opencv_zoo/raw/main/models/"
  "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
YUNET_NAME = "face_detection_yunet_2023mar.onnx"
_yunet_detector = None


def ensure_opencv():
  try:
    import cv2  # noqa: F401

    return
  except ImportError:
    pass
  print("opencv not found — installing opencv-python-headless…", file=sys.stderr)
  import subprocess

  subprocess.check_call(
    [sys.executable, "-m", "pip", "install", "--upgrade", "opencv-python-headless"]
  )


def yunet_model_path() -> Path:
  """Cached YuNet ONNX (OpenCV 5 removed Haar CascadeClassifier)."""
  cache = Path(__file__).resolve().parent.parent / ".cache" / "yunet"
  cache.mkdir(parents=True, exist_ok=True)
  dest = cache / YUNET_NAME
  if dest.is_file() and dest.stat().st_size > 100_000:
    return dest
  print(f"Downloading YuNet face model → {dest}…", file=sys.stderr)
  import urllib.request

  tmp = dest.with_suffix(".onnx.part")
  try:
    urllib.request.urlretrieve(YUNET_URL, tmp)
    tmp.replace(dest)
  finally:
    if tmp.exists():
      try:
        tmp.unlink()
      except OSError:
        pass
  if not dest.is_file() or dest.stat().st_size < 100_000:
    raise RuntimeError("Failed to download YuNet face model.")
  return dest


def get_yunet_detector(input_size: tuple[int, int]):
  """Reuse one FaceDetectorYN; resize input_size per frame as needed."""
  global _yunet_detector
  import cv2

  if not hasattr(cv2, "FaceDetectorYN_create"):
    raise RuntimeError("This OpenCV build has no FaceDetectorYN (need opencv-python-headless).")
  model = str(yunet_model_path())
  w, h = input_size
  if _yunet_detector is None:
    _yunet_detector = cv2.FaceDetectorYN_create(model, "", (w, h), 0.6, 0.3, 5000)
  else:
    _yunet_detector.setInputSize((w, h))
  return _yunet_detector


def video_duration_seconds(watch_url: str, yt_dlp_cmd: list[str]) -> float:
  result = run(
    [
      *yt_dlp_cmd,
      "--skip-download",
      "--no-warnings",
      "--print",
      "%(duration)s",
      watch_url,
    ],
    timeout=90,
  )
  if result.returncode != 0:
    raise RuntimeError((result.stderr or result.stdout or "yt-dlp duration failed.").strip())
  lines = [ln.strip() for ln in (result.stdout or "").splitlines() if ln.strip()]
  if not lines:
    raise RuntimeError("yt-dlp returned no duration.")
  try:
    return float(lines[0])
  except ValueError as e:
    raise RuntimeError(f"Bad duration from yt-dlp: {lines[0]!r}") from e


DEFAULT_START_SECONDS = 50 * 60  # 00:50:00 — Jnanodayam talk window start
DEFAULT_END_SECONDS = 65 * 60  # 01:05:00 — ~15 min window
DEFAULT_INTERVAL_SECONDS = 120.0  # sample every 2 minutes
DEFAULT_TOP = 7


def _hms(seconds: float) -> str:
  total = max(0, int(seconds))
  h, rem = divmod(total, 3600)
  m, s = divmod(rem, 60)
  return f"{h}:{m:02d}:{s:02d}"


def resolve_sample_window(
  skip_start: float,
  end_at: float | None,
  duration: float,
  skip_end: float,
  interval: float,
) -> tuple[float, float]:
  """
  Return (start, end) in original video seconds.

  end_at is an absolute timestamp when set; otherwise sample to near the end.
  Short videos clamp start toward 0 and end to duration.
  """
  tail = max(0.0, skip_end)
  hard_end = max(0.0, duration - tail)
  start = max(0.0, skip_start)
  if end_at is None or not (end_at == end_at):
    end = hard_end
  else:
    end = min(hard_end, max(0.0, float(end_at)))

  if start + interval > end:
    # Requested window past / beyond short video — sample what remains from 0
    print(
      f"  window {_hms(skip_start)}–{_hms(end_at if end_at is not None else hard_end)} "
      f"not usable (duration {_hms(duration)}); sampling from 0:00 instead",
      file=sys.stderr,
    )
    start = 0.0
    end = hard_end if end_at is None else min(hard_end, max(interval, float(end_at)))

  if end <= start:
    raise RuntimeError(
      f"Nothing to sample: duration={_hms(duration)} window "
      f"{_hms(start)}–{_hms(end)}."
    )
  return start, end


_STREAM_FORMATS = (
  "bestvideo[height<=720]/best[height<=720]/bestvideo/best",
  "bestvideo/best",
)


def resolve_video_stream_url(watch_url: str, yt_dlp_cmd: list[str]) -> str:
  """Direct media URL for ffmpeg seeks (same idea as extract-frame; no download)."""
  last_err = ""
  for fmt in _STREAM_FORMATS:
    result = run(
      [
        *yt_dlp_cmd,
        "--no-playlist",
        "--no-warnings",
        "-f",
        fmt,
        "-g",
        watch_url,
      ],
      timeout=90,
    )
    if result.returncode == 0:
      lines = [ln.strip() for ln in (result.stdout or "").splitlines() if ln.strip()]
      if lines:
        # -g may print video then audio; first line is enough for stills
        return lines[0]
    last_err = (result.stderr or result.stdout or "yt-dlp -g failed.").strip()
    if "Requested format is not available" not in last_err:
      # Try next format anyway; fall through
      pass
  # Last resort: helper used by extract-frame
  try:
    return youtube_stream_url(watch_url, yt_dlp_cmd)
  except RuntimeError as e:
    raise RuntimeError(last_err or str(e)) from e


def sample_times(start: float, end: float, interval: float) -> list[float]:
  start = max(0.0, start)
  end = max(start, end)
  if interval <= 0:
    raise RuntimeError("interval must be > 0")
  times: list[float] = []
  t = start
  # Inclusive start; stop at/just before end
  while t <= end + 1e-6:
    times.append(t)
    t += interval
  if not times:
    times = [start]
  return times


def sample_frames_from_stream(
  stream_url: str,
  work_dir: Path,
  *,
  interval: float,
  start: float,
  end: float,
  ffmpeg: str,
) -> list[tuple[Path, float]]:
  """
  Step 1 (fast) — seek the YouTube stream at each sample time (no full download).
  For a 5‑minute window @ 1/min this is ~5 ffmpeg stills, like extract-frame.
  """
  work_dir.mkdir(parents=True, exist_ok=True)
  times = sample_times(start, end, interval)
  out: list[tuple[Path, float]] = []
  for i, seconds in enumerate(times):
    dest = work_dir / f"frame_{i:05d}.jpg"
    print(f"  frame {i + 1}/{len(times)} @ {_hms(seconds)}…", file=sys.stderr)
    ff = run(
      [
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
        "-q:v",
        "3",
        str(dest),
      ],
      timeout=120,
    )
    if ff.returncode != 0 or not dest.is_file() or dest.stat().st_size == 0:
      err = (ff.stderr or "").strip()
      print(f"    skip @{_hms(seconds)}: {err or 'empty frame'}", file=sys.stderr)
      continue
    out.append((dest, seconds))
  if not out:
    raise RuntimeError(
      "No frames could be extracted from the stream — try a different start/end window."
    )
  return out


def _laplacian_var(gray) -> float:
  import cv2
  import numpy as np

  return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _smile_from_yunet_landmarks(face_row, face_w: float) -> tuple[int, float]:
  """
  YuNet landmarks: right eye, left eye, nose, right mouth corner, left mouth corner.
  Wider mouth relative to face ≈ more smile-like (Haar smile cascade gone in OpenCV 5).
  """
  # face_row: x,y,w,h, re_x,re_y, le_x,le_y, nose_x,nose_y, rm_x,rm_y, lm_x,lm_y, score
  if face_row is None or len(face_row) < 15 or face_w <= 1:
    return 0, 0.0
  rm_x, lm_x = float(face_row[10]), float(face_row[12])
  mouth_w = abs(lm_x - rm_x)
  ratio = mouth_w / face_w
  # Neutral ~0.28–0.38; open smile often higher
  if ratio >= 0.42:
    return 1, min(3.0, 1.2 + (ratio - 0.42) * 8.0)
  if ratio >= 0.36:
    return 1, min(2.0, 0.6 + (ratio - 0.36) * 6.0)
  return 0, max(0.0, (ratio - 0.28) * 2.0)


def score_frame_opencv(path: Path) -> ScoredFrame:
  import cv2

  img = cv2.imread(str(path))
  if img is None:
    return ScoredFrame(str(path), 0.0, -1.0, 0, 0, 0.0, "unreadable")

  gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
  sharp = _laplacian_var(gray)
  h, w = gray.shape[:2]

  # OpenCV 5: use YuNet FaceDetectorYN (CascadeClassifier removed).
  try:
    detector = get_yunet_detector((w, h))
    _retval, faces = detector.detect(img)
  except Exception as e:
    return ScoredFrame(
      str(path),
      0.0,
      min(2.0, sharp / 400.0),
      0,
      0,
      sharp,
      f"face-detect-error: {e}",
    )

  if faces is None or len(faces) == 0:
    return ScoredFrame(
      str(path),
      0.0,
      min(2.0, sharp / 400.0),
      0,
      0,
      sharp,
      "no-face",
    )

  # Largest face by box area
  faces_sorted = sorted(faces, key=lambda f: float(f[2]) * float(f[3]), reverse=True)
  face = faces_sorted[0]
  x, y, fw, fh = [float(v) for v in face[:4]]
  x_i, y_i = max(0, int(x)), max(0, int(y))
  fw_i, fh_i = max(1, int(fw)), max(1, int(fh))
  face_area = (fw * fh) / float(w * h)
  cx = (x + fw / 2) / w
  cy = (y + fh / 2) / h
  center_bonus = 1.0 - min(1.0, math.hypot(cx - 0.5, cy - 0.42) * 1.6)
  conf = float(face[14]) if len(face) > 14 else 0.0

  smiles, smile_score = _smile_from_yunet_landmarks(face, fw)

  face_roi = gray[y_i : y_i + fh_i, x_i : x_i + fw_i]
  face_sharp = _laplacian_var(face_roi) if face_roi.size else 0.0

  score = (
    2.5 * min(1.0, face_area * 8.0)
    + 1.8 * center_bonus
    + smile_score
    + min(2.0, face_sharp / 250.0)
    + min(1.0, sharp / 500.0)
    + min(1.0, conf)  # detector confidence
  )
  if len(faces) > 1:
    score -= 0.6 * (len(faces) - 1)

  reason = "smile" if smiles else "face"
  return ScoredFrame(str(path), 0.0, float(score), len(faces), smiles, face_sharp, reason)


def score_frame_fallback(path: Path) -> ScoredFrame:
  """No OpenCV: rank by JPEG size as a rough detail heuristic."""
  try:
    size_score = min(2.0, path.stat().st_size / 80_000)
    return ScoredFrame(
      str(path),
      0.0,
      size_score,
      0,
      0,
      float(path.stat().st_size),
      "filesize-fallback (install opencv-python-headless for face/smile)",
    )
  except Exception:
    return ScoredFrame(str(path), 0.0, 0.0, 0, 0, 0.0, "unscored")


def score_frames(frames: list[tuple[Path, float]], *, use_cv: bool) -> list[ScoredFrame]:
  """Step 2 — score each still."""
  scored: list[ScoredFrame] = []
  for path, seconds in frames:
    if use_cv:
      item = score_frame_opencv(path)
    else:
      item = score_frame_fallback(path)
    item.seconds = seconds
    scored.append(item)
  scored.sort(key=lambda s: s.score, reverse=True)
  return scored


def _unique_path(out_dir: Path, name: str) -> Path:
  dest = out_dir / name
  if not dest.exists():
    return dest
  stem = dest.stem
  suffix = dest.suffix
  n = 2
  while True:
    cand = out_dir / f"{stem}_r{n}{suffix}"
    if not cand.exists():
      return cand
    n += 1


def _copy_frame(src: Path, dest: Path, *, fmt: str, ffmpeg: str | None) -> Path:
  """Write still using extract-frame naming; convert to PNG when requested."""
  dest.parent.mkdir(parents=True, exist_ok=True)
  want_png = fmt == "png"
  if want_png and src.suffix.lower() != ".png":
    if not ffmpeg:
      dest = dest.with_suffix(".jpg")
      shutil.copy2(src, dest)
      return dest
    ff = run(
      [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        str(dest),
      ],
      timeout=60,
    )
    if ff.returncode != 0 or not dest.is_file():
      dest = dest.with_suffix(".jpg")
      shutil.copy2(src, dest)
    return dest
  shutil.copy2(src, dest)
  return dest


def write_winners(
  scored: list[ScoredFrame],
  *,
  out_dir: Path,
  video_id: str,
  title: str,
  top: int,
  fmt: str,
  ffmpeg: str | None = None,
  write_report: bool = True,
) -> list[Path]:
  """Step 3 — copy top candidates using extract-frame filenames."""
  out_dir.mkdir(parents=True, exist_ok=True)
  written: list[Path] = []
  winners = scored[: max(1, top)]
  for rank, item in enumerate(winners, start=1):
    src = Path(item.path)
    name = safe_frame_filename(video_id, title, item.seconds, fmt)
    dest = _unique_path(out_dir, name)
    dest = _copy_frame(src, dest, fmt=fmt, ffmpeg=ffmpeg)
    written.append(dest)
    print(
      f"  #{rank}  {dest.name}  "
      f"@{item.seconds:.1f}s  score={item.score:.2f}  "
      f"faces={item.faces} smiles={item.smiles}  ({item.reason})"
    )

  if write_report:
    report = {
      "videoId": video_id,
      "title": title,
      "top": [
        {
          **{k: v for k, v in asdict(s).items() if k != "path"},
          "file": Path(w).name,
        }
        for s, w in zip(winners, written)
      ],
    }
    report_name = safe_frame_filename(video_id, title, winners[0].seconds, "jpg").rsplit(".", 1)[0]
    report_path = out_dir / f"{report_name}_portrait-picks.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote report {report_path}")
  return written


def _prepare_cv() -> bool:
  try:
    ensure_opencv()
    import cv2

    if not hasattr(cv2, "FaceDetectorYN_create"):
      raise RuntimeError("OpenCV build lacks FaceDetectorYN")
    # Warm model download + construct once
    get_yunet_detector((320, 320))
    return True
  except Exception as e:
    print(f"OpenCV face model unavailable ({e}); using sharpness/filesize fallback.", file=sys.stderr)
    return False


def pick_best_portraits(
  video_input: str,
  *,
  out_dir: Path,
  interval: float = DEFAULT_INTERVAL_SECONDS,
  skip_start: float = DEFAULT_START_SECONDS,
  end_at: float | None = DEFAULT_END_SECONDS,
  skip_end: float = 15.0,
  top: int = DEFAULT_TOP,
  fmt: str = "jpg",
  keep_work: bool = False,
  write_report: bool = True,
  yt_dlp_cmd: list[str] | None = None,
  ffmpeg: str | None = None,
  use_cv: bool | None = None,
) -> dict:
  """
  Run the 3-step picker for one video.

  Returns dict with videoId, title, files (list[Path]), best (Path|None), picks (metadata).
  """
  video_id = extract_youtube_id(video_input)
  if not video_id:
    raise SystemExit("Enter a YouTube video ID or URL.")
  if interval <= 0:
    raise SystemExit("--interval / --every-min must be > 0")
  if top < 1:
    raise SystemExit("--top must be >= 1")

  yt_dlp_cmd = yt_dlp_cmd or ensure_yt_dlp_cmd()
  if ffmpeg is None:
    try:
      ffmpeg = resolve_ffmpeg()
    except RuntimeError as e:
      raise SystemExit(str(e)) from e
  if use_cv is None:
    use_cv = _prepare_cv()

  fmt = "png" if fmt == "png" else "jpg"
  watch_url = f"https://www.youtube.com/watch?v={video_id}"
  title = fetch_video_title(video_id, yt_dlp_cmd)
  duration = video_duration_seconds(watch_url, yt_dlp_cmd)
  start, end = resolve_sample_window(skip_start, end_at, duration, skip_end, interval)
  print(f"Video: {title} [{video_id}] · {_hms(duration)} · window {_hms(start)}–{_hms(end)}")

  work_root = Path(tempfile.mkdtemp(prefix="qlu-portrait-"))
  try:
    n_expect = len(sample_times(start, end, interval))
    print(
      f"Step 1/3 — resolving stream & sampling {n_expect} stills "
      f"({_hms(start)}–{_hms(end)}, every {interval:g}s)…"
    )
    stream_url = resolve_video_stream_url(watch_url, yt_dlp_cmd)
    frames_dir = work_root / "frames"
    frames = sample_frames_from_stream(
      stream_url,
      frames_dir,
      interval=interval,
      start=start,
      end=end,
      ffmpeg=ffmpeg,
    )
    print(f"  extracted {len(frames)} stills")

    print("Step 2/3 — scoring faces / smiles…")
    scored = score_frames(frames, use_cv=bool(use_cv))
    smiling = sum(1 for s in scored if s.smiles > 0)
    faced = sum(1 for s in scored if s.faces > 0)
    print(f"  faces in {faced}/{len(scored)} · smiles in {smiling}/{len(scored)}")

    print(f"Step 3/3 — writing top {top} to {out_dir}…")
    written = write_winners(
      scored,
      out_dir=out_dir,
      video_id=video_id,
      title=title,
      top=top,
      fmt=fmt,
      ffmpeg=ffmpeg,
      write_report=write_report,
    )
    winners = scored[: max(1, top)]
    return {
      "videoId": video_id,
      "title": title,
      "files": written,
      "best": written[0] if written else None,
      "picks": [
        {
          "file": w.name,
          "seconds": s.seconds,
          "score": s.score,
          "faces": s.faces,
          "smiles": s.smiles,
          "reason": s.reason,
        }
        for s, w in zip(winners, written)
      ],
    }
  finally:
    if keep_work:
      print(f"Kept work dir: {work_root}")
    else:
      shutil.rmtree(work_root, ignore_errors=True)


def pick_playlist_portraits(
  playlist_input: str,
  *,
  out_dir: Path,
  interval: float = DEFAULT_INTERVAL_SECONDS,
  skip_start: float = DEFAULT_START_SECONDS,
  end_at: float | None = DEFAULT_END_SECONDS,
  skip_end: float = 15.0,
  top: int = DEFAULT_TOP,
  fmt: str = "jpg",
  max_videos: int = 80,
) -> dict:
  """Pick portraits for each playlist video; return a zip path + metadata."""
  from download_youtube_captions import fetch_playlist_videos, parse_playlist_id

  playlist_id = parse_playlist_id(playlist_input)
  if not playlist_id:
    raise SystemExit("Enter a YouTube playlist ID or URL (list=…).")

  videos = fetch_playlist_videos(playlist_id, "auto", max_videos)
  print(f"Playlist {playlist_id}: {len(videos)} video(s)")

  yt_dlp_cmd = ensure_yt_dlp_cmd()
  try:
    ffmpeg = resolve_ffmpeg()
  except RuntimeError as e:
    raise SystemExit(str(e)) from e
  use_cv = _prepare_cv()

  out_dir.mkdir(parents=True, exist_ok=True)
  folder = out_dir / f"{playlist_id}-portrait-picks"
  folder.mkdir(parents=True, exist_ok=True)

  all_files: list[Path] = []
  results: list[dict] = []
  failures: list[str] = []

  for video in videos:
    vid = video["videoId"]
    title = video["title"]
    idx = video["index"]
    print(f"\n[{idx}/{len(videos)}] {vid} — {title[:60]}")
    try:
      result = pick_best_portraits(
        vid,
        out_dir=folder,
        interval=interval,
        skip_start=skip_start,
        end_at=end_at,
        skip_end=skip_end,
        top=top,
        fmt=fmt,
        write_report=False,
        yt_dlp_cmd=yt_dlp_cmd,
        ffmpeg=ffmpeg,
        use_cv=use_cv,
      )
      all_files.extend(result["files"])
      results.append(
        {
          "index": idx,
          "videoId": vid,
          "title": title,
          "picks": result["picks"],
        }
      )
    except Exception as e:
      msg = f"{vid} — {title}\n   {e}"
      failures.append(msg)
      print(f"  FAIL: {e}", file=sys.stderr)

  if not all_files:
    raise SystemExit(f"Playlist portrait pick failed. {failures[0] if failures else 'No files.'}")

  manifest_lines = [
    f"Playlist: {playlist_id}",
    f"Videos: {len(videos)}",
    f"Frames: {len(all_files)}",
    f"Failures: {len(failures)}",
    f"Top per video: {top}",
    "",
    *[f.name for f in all_files],
    "",
  ]
  manifest = "\n".join(manifest_lines)
  (folder / "_manifest.txt").write_text(manifest, encoding="utf-8")
  if failures:
    (folder / "_failures.txt").write_text(
      f"Playlist {playlist_id}\nSucceeded: {len(results)}\nFailed: {len(failures)}\n\n"
      + "\n\n".join(f"{i + 1}. {f}" for i, f in enumerate(failures))
      + "\n",
      encoding="utf-8",
    )

  zip_name = f"{playlist_id}-portrait-picks.zip"
  zip_path = out_dir / zip_name
  with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("_manifest.txt", manifest)
    for path in all_files:
      zf.write(path, arcname=path.name)
    if failures:
      zf.write(folder / "_failures.txt", arcname="_failures.txt")
  print(f"\nZip: {zip_path} ({len(all_files)} frames, {len(failures)} failed)")
  return {
    "playlistId": playlist_id,
    "zip": zip_path,
    "files": all_files,
    "results": results,
    "failures": failures,
  }


def zip_paths(paths: list[Path], zip_path: Path) -> Path:
  zip_path.parent.mkdir(parents=True, exist_ok=True)
  with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in paths:
      if path.is_file():
        zf.write(path, arcname=path.name)
  return zip_path


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Sample a YouTube talk and pick the best smiling / portrait frames.",
  )
  parser.add_argument("video", nargs="?", help="YouTube video ID or URL")
  parser.add_argument("-p", "--playlist", help="YouTube playlist ID or URL")
  parser.add_argument(
    "-o",
    "--out",
    type=Path,
    default=Path("out") / "portrait-picks",
    help="Output directory for top frames / zip",
  )
  parser.add_argument(
    "--every-min",
    type=float,
    default=2.0,
    help="Minutes between sampled frames (default: 2)",
  )
  parser.add_argument(
    "--interval",
    type=float,
    default=None,
    help="Seconds between frames (overrides --every-min if set)",
  )
  parser.add_argument(
    "--start",
    "--skip-start",
    dest="start",
    default="00:50:00",
    help="Start sampling at this time (default: 00:50:00, Jnanodayam tip). Accepts HH:MM:SS or MM:SS.",
  )
  parser.add_argument(
    "--end",
    dest="end",
    default="01:05:00",
    help="Stop sampling at this time (default: 01:05:00, Jnanodayam tip). Use empty / 'end' for full remainder.",
  )
  parser.add_argument(
    "--skip-end",
    type=float,
    default=15.0,
    help="Extra seconds to trim from the video end when --end is omitted (default: 15)",
  )
  parser.add_argument("--top", type=int, default=DEFAULT_TOP, help="How many winners to keep per video (default: 7)")
  parser.add_argument("--format", choices=("jpg", "png"), default="jpg")
  parser.add_argument("--max-videos", type=int, default=80, help="Playlist cap (default: 80)")
  parser.add_argument(
    "--keep-work",
    action="store_true",
    help="Keep temp download + all sampled frames for debugging",
  )
  args = parser.parse_args()
  from extract_youtube_frame import parse_timestamp

  start_seconds = parse_timestamp(str(args.start).strip())
  if not (start_seconds == start_seconds) or start_seconds < 0:
    raise SystemExit("Enter a valid --start time (e.g. 00:50:00).")
  end_raw = str(args.end).strip().lower() if args.end is not None else ""
  if end_raw in ("", "end", "inf", "none"):
    end_seconds: float | None = None
  else:
    end_seconds = parse_timestamp(str(args.end).strip())
    if not (end_seconds == end_seconds) or end_seconds < 0:
      raise SystemExit("Enter a valid --end time (e.g. 01:05:00).")
    if end_seconds <= start_seconds:
      raise SystemExit("--end must be after --start.")
  if args.interval is not None:
    interval_seconds = float(args.interval)
  else:
    interval_seconds = float(args.every_min) * 60.0
  if interval_seconds <= 0:
    raise SystemExit("--every-min / --interval must be > 0")
  try:
    if args.playlist:
      pick_playlist_portraits(
        args.playlist,
        out_dir=args.out,
        interval=interval_seconds,
        skip_start=start_seconds,
        end_at=end_seconds,
        skip_end=args.skip_end,
        top=args.top,
        fmt=args.format,
        max_videos=args.max_videos,
      )
    elif args.video:
      pick_best_portraits(
        args.video,
        out_dir=args.out,
        interval=interval_seconds,
        skip_start=start_seconds,
        end_at=end_seconds,
        skip_end=args.skip_end,
        top=args.top,
        fmt=args.format,
        keep_work=args.keep_work,
      )
    else:
      raise SystemExit("Provide a video ID/URL or --playlist.")
  except RuntimeError as e:
    raise SystemExit(str(e)) from e


if __name__ == "__main__":
  main()
