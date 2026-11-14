#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Attach still / frame images to Issue → Themes → themeItems.

Matches each image to a theme entry by (in order):
  1. YouTube video id in filename  …[VIDEOID]_00h…
  2. Jnanodayam day number         …Day-536… / day_536…
  3. Fuzzy title slug overlap

When several frames match the same theme item, **all** are attached to
`themeItems.images` (gallery). The primary `themeItems.image` is set from
`--pick` (first / last / largest among that item's matches).

Filenames follow extract_youtube_frame.py:
  {title-slug}[{videoId}]_00h59m51s.jpg

Example:

  python scripts/import_theme_images.py --folder out/frames --month 2026-11 --dry-run
  python scripts/import_theme_images.py --folder out/frames --month 2026-11 --heading-needle "నవరాత్ర"

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
# Filenames often include both Navratri episode (Day-19…Day-99) and Jnanodayam (Day-561…)
FILE_DAY_ALL_RE = re.compile(r"[Dd]ay[-_ ]?(\d{1,4})")
NAV_EPISODE_RE = re.compile(r"Day[-_]?([1-9])9(?:\D|$)", re.I)
VIJAYA_RE = re.compile(r"vijaya|dashami|dasami|విజయదశమి", re.I)
DEFAULT_HEADING_NEEDLE = "నవరాత్ర"


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


def theme_item_days(item: dict) -> set[int]:
  """Collect day numbers mentioned on the theme row (titles + body)."""
  blob = " ".join(
    str(item.get(k) or "")
    for k in (
      "titleTe",
      "titleEn",
      "blurbTe",
      "blurbEn",
      "fullStoryTe",
      "fullStoryEn",
    )
  )
  found: set[int] = set()
  d = day_from_title(blob)
  if d is not None:
    found.add(d)
  for m in FILE_DAY_ALL_RE.finditer(blob):
    found.add(int(m.group(1)))
  for m in re.finditer(r"(\d{3,4})\s*వ\s*రోజు", blob):
    found.add(int(m.group(1)))
  return found


def theme_item_jnanodayam_day(item: dict) -> int | None:
  days = [d for d in theme_item_days(item) if d >= 100]
  return max(days) if days else None


def theme_item_navratri_day(item: dict) -> int | None:
  title = theme_item_title(item)
  if VIJAYA_RE.search(title) or VIJAYA_RE.search(item.get("titleEn") or ""):
    return 10
  d = day_from_title(title) or day_from_title(item.get("titleEn") or "")
  if d is not None and d < 100:
    return d
  return None


def theme_item_title(item: dict) -> str:
  return (item.get("titleTe") or item.get("titleEn") or "").strip()


def jnanodayam_day_from_filename(name: str) -> int | None:
  """Prefer Day-561-style Jnanodayam numbers over Day-19 Navratri episode codes."""
  days = [int(x) for x in FILE_DAY_ALL_RE.findall(name)]
  big = [d for d in days if d >= 100]
  if big:
    return max(big)
  return None


def navratri_day_from_filename(name: str) -> int | None:
  """Map Day-19…Day-99 episode codes → Navratri days 1–9; Vijaya → 10."""
  if VIJAYA_RE.search(name):
    return 10
  m = NAV_EPISODE_RE.search(name)
  if m:
    return int(m.group(1))
  return None


def collect_image_files(folder: Path) -> list[Path]:
  if folder.is_file():
    return [folder] if folder.suffix.lower() in IMAGE_EXTS else []
  files: list[Path] = []
  for path in sorted(folder.rglob("*")):
    if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
      files.append(path)
  return files


def sort_paths(paths: list[Path], *, pick: str) -> list[Path]:
  """Order frames for an item; first entry becomes the primary card image."""
  if pick == "last":
    return sorted(paths, key=lambda p: (hms_seconds(p.name), p.stat().st_size, p.name), reverse=True)
  if pick == "largest":
    return sorted(paths, key=lambda p: (p.stat().st_size, hms_seconds(p.name), p.name), reverse=True)
  return sorted(paths, key=lambda p: (hms_seconds(p.name), -p.stat().st_size, p.name))


def match_item_index(
  items: list[dict],
  *,
  video_id: str | None,
  filename: str,
) -> tuple[int | None, str]:
  """Map one file → one theme item (does not consume the item; many files may share it)."""
  if video_id:
    for i, item in enumerate(items):
      if theme_item_video_id(item) == video_id:
        return i, f"videoId={video_id}"

  # Prefer Navratri episode codes (Day-19→1 … Day-99→9) before Jnanodayam day,
  # so Day-49[…564] lands on “Day 4” instead of sharing Day-564 with Day-39.
  nday = navratri_day_from_filename(filename)
  if nday is not None:
    for i, item in enumerate(items):
      if theme_item_navratri_day(item) == nday:
        return i, f"navratri-day={nday}"
    idx = nday - 1
    if 0 <= idx < len(items):
      return idx, f"navratri-day={nday}~index"

  jday = jnanodayam_day_from_filename(filename)
  if jday is not None:
    for i, item in enumerate(items):
      if theme_item_jnanodayam_day(item) == jday or jday in theme_item_days(item):
        return i, f"jnanodayam-day={jday}"

  file_tokens = title_tokens(Path(filename).stem)
  if file_tokens:
    best_i = None
    best_score = 0
    for i, item in enumerate(items):
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

  gallery = []
  for row in item.get("images") or []:
    if not isinstance(row, dict):
      continue
    gid = media_id(row.get("image"))
    if gid is None:
      continue
    entry = {"image": gid}
    if row.get("id"):
      entry["id"] = row["id"]
    gallery.append(entry)
  out["images"] = gallery
  return out


def existing_gallery_ids(item: dict) -> set[str]:
  ids: set[str] = set()
  mid = media_id(item.get("image"))
  if mid is not None:
    ids.add(str(mid))
  for row in item.get("images") or []:
    if isinstance(row, dict):
      gid = media_id(row.get("image"))
      if gid is not None:
        ids.add(str(gid))
  return ids


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

  print(f"Image files found: {len(files)}")

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

  # item index → list of (path, how)
  matched: dict[int, list[tuple[Path, str]]] = {}
  skipped: list[str] = []

  for path in files:
    vid = video_id_from_filename(path.name)
    match_i, how = match_item_index(
      items,
      video_id=vid,
      filename=path.name,
    )
    if match_i is None:
      skipped.append(f"{path.name} ({how})")
      continue
    matched.setdefault(match_i, []).append((path, how))

  planned: list[tuple[int, list[Path], str]] = []
  for match_i, pairs in sorted(matched.items()):
    paths = sort_paths([p for p, _ in pairs], pick=pick)
    hows = sorted({h for _, h in pairs})
    how = ", ".join(hows)
    title = theme_item_title(items[match_i])[:72]
    already = existing_gallery_ids(items[match_i])
    if already and not replace_existing:
      # Still allow adding newly matched files that aren't already attached
      new_names = [p.name for p in paths]
      print(
        f"  merge [{match_i}] {title} — {len(paths)} frame(s)"
        f" (existing media ids={len(already)}; will skip duplicate filenames on upload)\n"
        f"      ← {', '.join(new_names[:4])}{'…' if len(new_names) > 4 else ''}\n"
        f"      match: {how}"
      )
    else:
      action = "replace" if already else "set"
      print(
        f"  {action} [{match_i}] {title} — {len(paths)} frame(s)\n"
        f"      ← {', '.join(p.name for p in paths[:4])}{'…' if len(paths) > 4 else ''}\n"
        f"      match: {how}"
      )
    planned.append((match_i, paths, how))

  for s in skipped:
    print(f"  skip {s}")

  if not planned:
    print("Nothing to import.")
    return 0

  total_frames = sum(len(paths) for _, paths, _ in planned)
  if dry_run:
    print(f"Dry run — would upload/attach {total_frames} image(s) across {len(planned)} theme item(s).")
    return 0

  changed_items = 0
  uploaded = 0
  for match_i, paths, how in planned:
    alt = theme_item_title(items[match_i]) or paths[0].stem
    media_ids: list[int | str] = []
    seen_ids: set[str] = set()

    if not replace_existing:
      # Keep existing gallery / primary, then append newly matched frames
      primary = media_id(items[match_i].get("image"))
      if primary is not None:
        seen_ids.add(str(primary))
        media_ids.append(primary)
      for row in items[match_i].get("images") or []:
        gid = media_id(row.get("image") if isinstance(row, dict) else None)
        if gid is not None and str(gid) not in seen_ids:
          seen_ids.add(str(gid))
          media_ids.append(gid)

    new_ids: list[int | str] = []
    for path in paths:
      existing_media = find_existing_media_id(base, token, path.name)
      if existing_media is not None:
        mid = existing_media
        print(f"Reusing media id={mid} for {path.name}")
      else:
        print(f"Uploading {path.name} …")
        mid = upload_media(base, token, path, alt=alt)
        uploaded += 1
      if str(mid) in seen_ids:
        print(f"  (already on item) media id={mid}")
        continue
      seen_ids.add(str(mid))
      new_ids.append(mid)
      print(f"  → media id={mid}")

    if replace_existing:
      # paths already sorted by --pick; primary = first
      media_ids = new_ids
    else:
      # Prefer newly matched primary (--pick order) as card image when item had none
      if media_ids:
        media_ids = media_ids + new_ids
      else:
        media_ids = new_ids

    if not media_ids:
      continue

    items[match_i] = {
      **items[match_i],
      "image": media_ids[0],
      "images": [{"image": mid} for mid in media_ids],
    }
    changed_items += 1
    print(f"  item [{match_i}] gallery={len(media_ids)} primary={media_ids[0]} ({how})")

  themes = {**themes, "themeItems": items}
  sections[idx] = themes
  http_json(
    "PATCH",
    f"{base}/api/issues/{issue_id}",
    token=token,
    body={"sections": sections},
  )
  print(
    f"Patched issue {issue_id}: updated {changed_items} theme item(s), "
    f"uploaded {uploaded} new media file(s)."
  )
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
    help="Replace theme item galleries instead of merging",
  )
  ap.add_argument(
    "--pick",
    choices=("first", "last", "largest"),
    default="first",
    help="Which matched frame becomes the primary card image (default: earliest timestamp)",
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
