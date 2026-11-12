#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Attach still / frame images to Issue → Themes → themeItems.image.

Matches each image to a theme entry by (in order):
  1. YouTube video id in filename  …[VIDEOID]_00h…
  2. Jnanodayam day number         …Day-536… / day_536…
  3. Fuzzy title slug overlap

Filenames follow extract_youtube_frame.py:
  {title-slug}[{videoId}]_00h59m51s.jpg

Example:

  python scripts/import_theme_images.py --folder out/frames --month 2026-11 --dry-run
  python scripts/import_theme_images.py --folder out/frames --month 2026-11 --heading-needle "గణేశ"

Auth (same as import_theme_readmore.py):
  PAYLOAD_URL, SEED_ADMIN_EMAIL, SEED_ADMIN_PASSWORD
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import uuid
import urllib.error
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from import_theme_readmore import (  # noqa: E402
  day_from_filename,
  day_from_title,
  find_issue,
  find_themes_section,
  http_json,
  login,
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_ID_RE = re.compile(r"\[([a-zA-Z0-9_-]{6,})\]")
YT_ID_RE = re.compile(
  r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([a-zA-Z0-9_-]{6,})",
  re.I,
)
HMS_RE = re.compile(r"_(\d{2})h(\d{2})m(\d{2})s\.", re.I)
DEFAULT_HEADING_NEEDLE = "గణేశ"


def media_id(value) -> int | str | None:
  if value is None:
    return None
  if isinstance(value, dict):
    return value.get("id")
  if isinstance(value, (int, str)) and str(value).strip():
    return value
  return None


def video_id_from_filename(name: str) -> str | None:
  m = VIDEO_ID_RE.search(name)
  return m.group(1) if m else None


def video_id_from_text(text: str) -> str | None:
  if not text:
    return None
  m = YT_ID_RE.search(text)
  if m:
    return m.group(1)
  m = VIDEO_ID_RE.search(text)
  return m.group(1) if m else None


def hms_seconds(name: str) -> int:
  m = HMS_RE.search(name)
  if not m:
    return 0
  return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def normalize_slug(text: str) -> str:
  text = (text or "").casefold()
  text = re.sub(r"\[.*?\]", " ", text)
  text = re.sub(r"_\d{2}h\d{2}m\d{2}s$", " ", text, flags=re.I)
  text = re.sub(r"[^0-9a-z\u0c00-\u0c7f]+", " ", text)
  return re.sub(r"\s+", " ", text).strip()


def title_tokens(text: str) -> set[str]:
  return {t for t in normalize_slug(text).split() if len(t) >= 3}


def theme_item_video_id(item: dict) -> str | None:
  for key in ("fullStoryTe", "fullStoryEn", "blurbTe", "blurbEn", "storyUrl", "titleTe", "titleEn"):
    vid = video_id_from_text(item.get(key) or "")
    if vid:
      return vid
  return None


def theme_item_day(item: dict) -> int | None:
  for key in ("titleTe", "titleEn"):
    d = day_from_title(item.get(key) or "")
    if d is not None:
      return d
  return None


def theme_item_title(item: dict) -> str:
  return (item.get("titleTe") or item.get("titleEn") or "").strip()


def collect_image_files(folder: Path) -> list[Path]:
  if folder.is_file():
    return [folder] if folder.suffix.lower() in IMAGE_EXTS else []
  files: list[Path] = []
  for path in sorted(folder.rglob("*")):
    if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
      files.append(path)
  return files


def pick_best_per_key(
  files: list[Path],
  *,
  pick: str,
) -> dict[str, Path]:
  """
  Group images that share the same video id (preferred) or day key.
  Returns mapping key → chosen path. Keys are 'v:ID' or 'd:NNN'.
  """
  buckets: dict[str, list[Path]] = {}
  for path in files:
    vid = video_id_from_filename(path.name)
    day = day_from_filename(path)
    if vid:
      key = f"v:{vid}"
    elif day is not None:
      key = f"d:{day}"
    else:
      key = f"f:{path.name.casefold()}"
    buckets.setdefault(key, []).append(path)

  chosen: dict[str, Path] = {}
  for key, paths in buckets.items():
    if pick == "last":
      best = max(paths, key=lambda p: (hms_seconds(p.name), p.stat().st_size, p.name))
    elif pick == "largest":
      best = max(paths, key=lambda p: (p.stat().st_size, hms_seconds(p.name), p.name))
    else:  # first (earliest timestamp)
      best = min(paths, key=lambda p: (hms_seconds(p.name), -p.stat().st_size, p.name))
    chosen[key] = best
  return chosen


def match_item_index(
  items: list[dict],
  *,
  video_id: str | None,
  day: int | None,
  filename: str,
  used: set[int],
) -> tuple[int | None, str]:
  if video_id:
    for i, item in enumerate(items):
      if i in used:
        continue
      if theme_item_video_id(item) == video_id:
        return i, f"videoId={video_id}"

  if day is not None:
    for i, item in enumerate(items):
      if i in used:
        continue
      if theme_item_day(item) == day:
        return i, f"day={day}"

  file_tokens = title_tokens(Path(filename).stem)
  if file_tokens:
    best_i = None
    best_score = 0
    for i, item in enumerate(items):
      if i in used:
        continue
      score = len(file_tokens & title_tokens(theme_item_title(item)))
      if score > best_score:
        best_score = score
        best_i = i
    if best_i is not None and best_score >= 2:
      return best_i, f"title-overlap={best_score}"

  return None, "unmatched"


def find_existing_media_id(base: str, token: str, filename: str) -> int | str | None:
  """Reuse a Media doc that already has this filename (avoids duplicate uploads)."""
  from urllib.parse import quote

  url = f"{base}/api/media?limit=1&where[filename][equals]={quote(filename)}"
  try:
    out = http_json("GET", url, token=token)
  except SystemExit:
    return None
  docs = out.get("docs") or []
  if not docs:
    return None
  return docs[0].get("id")


def upload_media(base: str, token: str, path: Path, alt: str) -> int | str:
  boundary = f"----qlu{uuid.uuid4().hex}"
  filename = path.name
  ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
  file_bytes = path.read_bytes()

  parts: list[bytes] = []
  for name, value in (("alt", alt),):
    parts.append(
      (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
        f"{value}\r\n"
      ).encode("utf-8")
    )
  parts.append(
    (
      f"--{boundary}\r\n"
      f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
      f"Content-Type: {ctype}\r\n\r\n"
    ).encode("utf-8")
    + file_bytes
    + b"\r\n"
  )
  parts.append(f"--{boundary}--\r\n".encode("utf-8"))
  body = b"".join(parts)

  req = urllib.request.Request(
    f"{base}/api/media",
    data=body,
    method="POST",
    headers={
      "Authorization": f"JWT {token}",
      "Content-Type": f"multipart/form-data; boundary={boundary}",
      "Accept": "application/json",
    },
  )
  try:
    with urllib.request.urlopen(req, timeout=180) as resp:
      out = json.loads(resp.read().decode("utf-8"))
  except urllib.error.HTTPError as e:
    detail = e.read().decode("utf-8", errors="replace")
    raise SystemExit(f"POST /api/media → HTTP {e.code}: {detail[:800]}") from e

  doc = out.get("doc") or out
  mid = doc.get("id")
  if mid is None:
    raise SystemExit(f"Media upload returned no id: {out!r}"[:500])
  return mid


def serialize_theme_item(item: dict) -> dict:
  """Keep array row writable for PATCH (resolve nested media to id)."""
  out = dict(item)
  mid = media_id(item.get("image"))
  if mid is not None:
    out["image"] = mid
  elif "image" in out:
    out.pop("image", None)
  return out


def import_theme_images(
  files: list[Path],
  *,
  month: str,
  heading_needle: str,
  base_url: str = "http://localhost:3000",
  email: str = "admin@qlu.local",
  password: str = "qlu-admin-change-me",
  dry_run: bool = False,
  replace_existing: bool = False,
  pick: str = "first",
) -> int:
  if not files:
    raise SystemExit("No image files to import")

  chosen = pick_best_per_key(files, pick=pick)
  print(f"Image files found: {len(files)} → unique keys: {len(chosen)} (pick={pick})")

  base = base_url.rstrip("/")
  print(f"Logging in to {base} as {email} …")
  token = login(base, email, password)

  issue = find_issue(base, month, token)
  issue_id = issue["id"]
  sections = list(issue.get("sections") or [])
  idx, themes, _created = find_themes_section(
    sections,
    heading_needle,
    create_section=False,
  )
  items = [serialize_theme_item(it) for it in (themes.get("themeItems") or [])]

  print(f"Issue id={issue_id} month={month}")
  print(f"Themes heading: {themes.get('headingTe')}")
  print(f"Theme items: {len(items)}")

  used: set[int] = set()
  planned: list[tuple[int, Path, str]] = []
  skipped: list[str] = []

  # Prefer video-key matches before day-key matches for stable assignment
  ordered_keys = sorted(chosen.keys(), key=lambda k: (0 if k.startswith("v:") else 1, k))
  for key in ordered_keys:
    path = chosen[key]
    vid = video_id_from_filename(path.name)
    day = day_from_filename(path)
    match_i, how = match_item_index(
      items,
      video_id=vid,
      day=day,
      filename=path.name,
      used=used,
    )
    if match_i is None:
      skipped.append(f"{path.name} ({how})")
      continue

    existing = media_id(items[match_i].get("image"))
    title = theme_item_title(items[match_i])[:72]
    if existing is not None and not replace_existing:
      skipped.append(f"{path.name} → day/item already has image id={existing}")
      used.add(match_i)
      continue

    planned.append((match_i, path, how))
    used.add(match_i)
    action = "replace" if existing is not None else "set"
    print(
      f"  {action} [{match_i}] {title}\n"
      f"      ← {path.name}\n"
      f"      match: {how}"
    )

  for s in skipped:
    print(f"  skip {s}")

  if not planned:
    print("Nothing to import.")
    return 0

  if dry_run:
    print(f"Dry run — would upload/attach {len(planned)} image(s).")
    return 0

  changed = 0
  for match_i, path, how in planned:
    alt = theme_item_title(items[match_i]) or path.stem
    existing_media = find_existing_media_id(base, token, path.name)
    if existing_media is not None:
      mid = existing_media
      print(f"Reusing media id={mid} for {path.name}")
    else:
      print(f"Uploading {path.name} …")
      mid = upload_media(base, token, path, alt=alt)
    items[match_i] = {**items[match_i], "image": mid}
    changed += 1
    print(f"  → media id={mid} ({how})")

  themes = {**themes, "themeItems": items}
  sections[idx] = themes
  http_json(
    "PATCH",
    f"{base}/api/issues/{issue_id}",
    token=token,
    body={"sections": sections},
  )
  print(f"Patched issue {issue_id}: attached {changed} theme image(s).")
  return 0


def main() -> int:
  ap = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter,
  )
  ap.add_argument("--folder", required=True, help="Folder (or single file) of theme frame images")
  ap.add_argument("--month", default="2026-11", help="Issue month YYYY-MM")
  ap.add_argument(
    "--heading-needle",
    default=DEFAULT_HEADING_NEEDLE,
    help="Match themes section heading (substring)",
  )
  ap.add_argument("--base-url", default=os.environ.get("PAYLOAD_URL", "http://localhost:3000"))
  ap.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL", "admin@qlu.local"))
  ap.add_argument(
    "--password",
    default=os.environ.get("SEED_ADMIN_PASSWORD", "qlu-admin-change-me"),
  )
  ap.add_argument("--dry-run", action="store_true", help="Plan only; no upload/PATCH")
  ap.add_argument(
    "--replace-existing",
    action="store_true",
    help="Replace theme items that already have an image",
  )
  ap.add_argument(
    "--pick",
    choices=("first", "last", "largest"),
    default="first",
    help="When multiple frames share a video/day, which to keep (default: earliest timestamp)",
  )
  args = ap.parse_args()

  folder = Path(args.folder)
  if not folder.exists():
    raise SystemExit(f"Folder not found: {folder}")
  files = collect_image_files(folder)
  if not files:
    raise SystemExit(f"No image files under {folder}")

  return import_theme_images(
    files,
    month=args.month,
    heading_needle=args.heading_needle,
    base_url=args.base_url,
    email=args.email,
    password=args.password,
    dry_run=args.dry_run,
    replace_existing=args.replace_existing,
    pick=args.pick,
  )


if __name__ == "__main__":
  sys.exit(main())
