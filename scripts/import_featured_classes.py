#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import Featured Classes pack → Jnanodayam readings + Issue Section 2 (highlight-classes).

Folder layout (Drive unpack):

  day-574-te.json / day-574-en.json
  day-574-te-blurb.json / day-574-en-blurb.json
  …Day-574[VIDEO]_thumb.jpg

For each day:
  1. Upsert jnanodayam-readings (series=daily) with cover thumb
  2. Upsert Issue classItems (image, jnanodayamDay, insight blurb, fullStory markdown)
     — storyUrl left empty so newsletter Read more uses the existing side drawer

Examples:

  python scripts/import_featured_classes.py ^
    --folder "C:\\Users\\dhana\\Downloads\\drive-download-20261115T052214Z-1-001" ^
    --month 2026-11

  python scripts/import_featured_classes.py --folder … --dry-run

Auth: PAYLOAD_URL / SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from import_jnanodayam_reading import (  # noqa: E402
  ascii_filename,
  build_payload,
  find_existing_media_id,
  find_reading,
  load_day_json as load_reading_json,
  login,
  upload_media,
  upsert_reading,
)

SECTION_TITLES = {
  "highlight-classes": {
    "te": "ఈ నెల విశిష్ట తరగతులు – జ్ఞానాంశాలు",
    "en": "Featured Classes & Insights",
  },
}
from import_theme_day_json import day_json_to_markdown  # noqa: E402
from import_theme_images import media_id, serialize_theme_item  # noqa: E402
from import_theme_readmore import find_issue, http_json  # noqa: E402

DEFAULT_FOLDER = (
  r"C:\Users\dhana\Downloads\drive-download-20261115T052214Z-1-001"
)
DAY_FILE_RE = re.compile(r"^day-(\d+)-(te|en)(?:-blurb)?\.json$", re.I)
THUMB_DAY_RE = re.compile(r"Day[-_ ]?(\d+)", re.I)
VIDEO_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]")
NEWTON_RE = re.compile(r"Newton|న్యూటన్", re.I)


def load_json(path: Path) -> dict:
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except json.JSONDecodeError as e:
    raise SystemExit(f"Invalid JSON {path}: {e}") from e
  if not isinstance(data, dict):
    raise SystemExit(f"Expected object in {path}")
  return data


def discover_days(folder: Path) -> dict[int, dict]:
  """day → {te, en, te_blurb, en_blurb, thumb} Paths."""
  days: dict[int, dict] = {}
  for path in sorted(folder.iterdir()):
    if not path.is_file():
      continue
    m = DAY_FILE_RE.match(path.name)
    if m:
      day = int(m.group(1))
      lang = m.group(2).lower()
      row = days.setdefault(day, {})
      if "-blurb" in path.name.lower():
        row[f"{lang}_blurb"] = path
      else:
        row[lang] = path
      continue
    if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
      dm = THUMB_DAY_RE.search(path.name)
      if dm:
        day = int(dm.group(1))
        row = days.setdefault(day, {})
        # Prefer *_thumb.*
        prev = row.get("thumb")
        if prev is None or "_thumb" in path.name.lower():
          row["thumb"] = path
  return days


def insight_from_blurb(blurb_doc: dict | None) -> str:
  if not blurb_doc:
    return ""
  parts: list[str] = []
  blurb = str(blurb_doc.get("blurb") or "").strip()
  if blurb:
    parts.append(blurb)
  highlights = blurb_doc.get("highlights") or []
  if isinstance(highlights, list) and highlights:
    bullets = [f"- {str(h).strip()}" for h in highlights if str(h).strip()]
    if bullets:
      parts.append("\n".join(bullets))
  return "\n\n".join(parts).strip()


def speaker_guess(*texts: str) -> str:
  blob = " ".join(t for t in texts if t)
  if NEWTON_RE.search(blob):
    return "Dr. Newton Kondaveti"
  return ""


def video_url_from_thumb(thumb: Path | None) -> str:
  if not thumb:
    return ""
  m = VIDEO_ID_RE.search(thumb.name)
  if not m:
    return ""
  return f"https://www.youtube.com/watch?v={m.group(1)}"


def ensure_classes_section(sections: list) -> tuple[int, dict]:
  for i, s in enumerate(sections):
    if s.get("key") == "highlight-classes":
      return i, s
  titles = SECTION_TITLES.get(
    "highlight-classes",
    {"te": "హైలైట్ క్లాసులు", "en": "Featured Classes & Insights"},
  )
  new_sec = {
    "key": "highlight-classes",
    "headingTe": titles["te"],
    "headingEn": titles["en"],
    "classItems": [],
  }
  sections.append(new_sec)
  return len(sections) - 1, new_sec


def serialize_class_item(item: dict) -> dict:
  out = serialize_theme_item(item)
  # Drop nested ids that confuse Payload array replaces when reusing rows
  return out


def find_class_index(items: list[dict], day: int) -> int | None:
  for i, it in enumerate(items):
    try:
      if int(it.get("jnanodayamDay") or 0) == day:
        return i
    except (TypeError, ValueError):
      continue
  return None


def ensure_cover(
  base: str,
  token: str,
  thumb: Path | None,
  day: int,
  alt: str,
  *,
  dry_run: bool,
) -> int | str | None:
  if not thumb or not thumb.is_file():
    return None
  upload_name = ascii_filename(thumb.name, f"jnanodayam-day-{day}-cover")
  if dry_run:
    print(f"    [dry-run] cover → {upload_name}")
    return None
  existing = find_existing_media_id(base, token, upload_name)
  if existing is not None:
    print(f"    reuse media id={existing} ({upload_name})")
    return existing
  src = thumb
  if upload_name != thumb.name:
    tmp = thumb.with_name(upload_name)
    if not tmp.exists():
      tmp.write_bytes(thumb.read_bytes())
    src = tmp
  mid = upload_media(base, token, src, alt)
  print(f"    uploaded media id={mid} ({src.name})")
  return mid


def import_day_pack(
  *,
  day: int,
  pack: dict,
  base: str,
  token: str,
  items: list[dict],
  dry_run: bool,
) -> bool:
  te_path: Path | None = pack.get("te")
  en_path: Path | None = pack.get("en")
  if not te_path and not en_path:
    print(f"  skip day {day}: no day JSON")
    return False

  te = load_reading_json(te_path) if te_path else None
  en = load_reading_json(en_path) if en_path else None
  # load_reading_json requires sections — blurb is separate
  te_blurb = load_json(pack["te_blurb"]) if pack.get("te_blurb") else None
  en_blurb = load_json(pack["en_blurb"]) if pack.get("en_blurb") else None
  thumb: Path | None = pack.get("thumb")

  title_te = str((te or {}).get("title") or (te_blurb or {}).get("title") or "").strip()
  title_en = str((en or {}).get("title") or (en_blurb or {}).get("title") or "").strip()
  alt = title_te or title_en or f"Jnanodayam Day {day}"

  print(f"  day {day}: {title_en or title_te}")
  cover_id = ensure_cover(base, token, thumb, day, alt, dry_run=dry_run)

  existing_reading = None if dry_run else find_reading(base, token, "daily", day)
  reading_payload = build_payload(
    series="daily",
    te=te,
    en=en,
    title_en=title_en or None,
    title_te=title_te or None,
    subtitle_en=None,
    subtitle_te=None,
    cover_id=cover_id,
    published=True,
    existing=existing_reading,
  )
  # EN-only create still needs both titles (build_payload handles)
  upsert_reading(base, token, reading_payload, dry_run=dry_run)

  video = video_url_from_thumb(thumb)
  peer_for_en = ""
  if video:
    peer_for_en = f"**Original Video:** {video}\n"
  peer_for_te = f"**మూల వీడియో:** {video}\n" if video else ""

  full_te = day_json_to_markdown(te, peer_md=peer_for_te) if te else ""
  full_en = day_json_to_markdown(en, peer_md=peer_for_en) if en else ""
  insight_te = insight_from_blurb(te_blurb)
  insight_en = insight_from_blurb(en_blurb)
  speaker = speaker_guess(
    title_te,
    title_en,
    str(thumb.name if thumb else ""),
    full_te,
    full_en,
  ) or "Dr. Newton Kondaveti"

  match_i = find_class_index(items, day)
  base_item = serialize_class_item(items[match_i]) if match_i is not None else {}
  payload = {
    **base_item,
    "jnanodayamDay": day,
    "speaker": speaker or base_item.get("speaker") or "",
  }
  # Keep drawer: never set storyUrl from this importer
  payload.pop("storyUrl", None)

  if title_te:
    payload["titleTe"] = title_te
  elif not payload.get("titleTe"):
    payload["titleTe"] = title_en or f"జ్ఞానోదయం · రోజు {day}"
  if title_en:
    payload["titleEn"] = title_en
  elif not payload.get("titleEn"):
    payload["titleEn"] = title_te or f"Jnanodayam · Day {day}"

  if insight_te:
    payload["insightTe"] = insight_te
  if insight_en:
    payload["insightEn"] = insight_en
  if full_te:
    payload["fullStoryTe"] = full_te
  if full_en:
    payload["fullStoryEn"] = full_en
  if cover_id is not None:
    payload["image"] = cover_id
  elif match_i is not None:
    mid = media_id(items[match_i].get("image"))
    if mid is not None:
      payload["image"] = mid

  # Ensure required-ish titles always present for PATCH create rows
  if not payload.get("titleTe"):
    payload["titleTe"] = payload.get("titleEn") or f"Day {day}"
  if not payload.get("titleEn"):
    payload["titleEn"] = payload.get("titleTe") or f"Day {day}"

  action = "update" if match_i is not None else "create"
  print(
    f"    classItem [{action}] "
    f"teStory={len(full_te)} enStory={len(full_en)} "
    f"insightTe={len(insight_te)} insightEn={len(insight_en)}"
  )
  if dry_run:
    return True

  if match_i is not None:
    items[match_i] = payload
  else:
    items.append(payload)
  return True


def main() -> None:
  ap = argparse.ArgumentParser(
    description="Import Featured Classes pack into Jnanodayam + Issue Section 2",
  )
  ap.add_argument("--folder", default=DEFAULT_FOLDER, help="Drive unpack folder")
  ap.add_argument("--month", default="2026-11")
  ap.add_argument("--base", default=os.environ.get("PAYLOAD_URL", "http://localhost:3000"))
  ap.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL", "admin@qlu.local"))
  ap.add_argument(
    "--password",
    default=os.environ.get("SEED_ADMIN_PASSWORD", "qlu-admin-change-me"),
  )
  ap.add_argument("--dry-run", action="store_true")
  ap.add_argument(
    "--skip-readings",
    action="store_true",
    help="Only update Issue classItems (skip jnanodayam-readings)",
  )
  args = ap.parse_args()

  folder = Path(args.folder)
  if not folder.is_dir():
    raise SystemExit(f"Folder not found: {folder}")

  days = discover_days(folder)
  if not days:
    raise SystemExit(f"No day-*-{{te|en}}.json files in {folder}")

  base = args.base.rstrip("/")
  token = "" if args.dry_run else login(base, args.email, args.password)
  issue = find_issue(base, args.month, token) if not args.dry_run else {"sections": []}
  if args.dry_run:
    # Still need real issue for planning if possible
    try:
      token = login(base, args.email, args.password)
      issue = find_issue(base, args.month, token)
    except SystemExit as e:
      print(f"[dry-run] could not load issue: {e}")
      issue = {"id": "?", "sections": []}

  issue_id = issue.get("id")
  sections = list(issue.get("sections") or [])
  idx, classes_sec = ensure_classes_section(sections)
  items = [serialize_class_item(it) for it in (classes_sec.get("classItems") or [])]

  print(f"Issue {args.month} id={issue_id}")
  print(f"Folder: {folder}")
  print(f"Days found: {sorted(days)}")
  print(f"Existing classItems: {len(items)}")

  changed = 0
  for day in sorted(days):
    pack = days[day]
    # Temporarily stub upsert_reading when --skip-readings
    if args.skip_readings:
      # Local override: only class items
      te_path = pack.get("te")
      en_path = pack.get("en")
      if not te_path and not en_path:
        continue
      te = load_reading_json(te_path) if te_path else None
      en = load_reading_json(en_path) if en_path else None
      te_blurb = load_json(pack["te_blurb"]) if pack.get("te_blurb") else None
      en_blurb = load_json(pack["en_blurb"]) if pack.get("en_blurb") else None
      thumb = pack.get("thumb")
      title_te = str((te or {}).get("title") or (te_blurb or {}).get("title") or "").strip()
      title_en = str((en or {}).get("title") or (en_blurb or {}).get("title") or "").strip()
      alt = title_te or title_en or f"Jnanodayam Day {day}"
      print(f"  day {day}: {title_en or title_te} (skip readings)")
      cover_id = ensure_cover(base, token, thumb, day, alt, dry_run=args.dry_run)
      video = video_url_from_thumb(thumb)
      peer_en = f"**Original Video:** {video}\n" if video else ""
      peer_te = f"**మూల వీడియో:** {video}\n" if video else ""
      full_te = day_json_to_markdown(te, peer_md=peer_te) if te else ""
      full_en = day_json_to_markdown(en, peer_md=peer_en) if en else ""
      match_i = find_class_index(items, day)
      base_item = serialize_class_item(items[match_i]) if match_i is not None else {}
      payload = {
        **base_item,
        "jnanodayamDay": day,
        "speaker": speaker_guess(title_te, title_en, str(thumb.name if thumb else ""))
        or "Dr. Newton Kondaveti",
        "titleTe": title_te or title_en or f"జ్ఞానోదయం · రోజు {day}",
        "titleEn": title_en or title_te or f"Jnanodayam · Day {day}",
      }
      payload.pop("storyUrl", None)
      insight_te = insight_from_blurb(te_blurb)
      insight_en = insight_from_blurb(en_blurb)
      if insight_te:
        payload["insightTe"] = insight_te
      if insight_en:
        payload["insightEn"] = insight_en
      if full_te:
        payload["fullStoryTe"] = full_te
      if full_en:
        payload["fullStoryEn"] = full_en
      if cover_id is not None:
        payload["image"] = cover_id
      if args.dry_run:
        print(f"    [dry-run] would {'update' if match_i is not None else 'create'} classItem")
      elif match_i is not None:
        items[match_i] = payload
      else:
        items.append(payload)
      changed += 1
      continue

    if import_day_pack(
      day=day,
      pack=pack,
      base=base,
      token=token,
      items=items,
      dry_run=args.dry_run,
    ):
      changed += 1

  if not changed:
    print("Nothing to import.")
    return

  if args.dry_run:
    print(f"Dry run — would touch {changed} day(s).")
    return

  classes_sec = {**classes_sec, "classItems": items}
  sections[idx] = classes_sec
  print(f"PATCHing issue {issue_id} ({len(items)} classItems) …")
  http_json(
    "PATCH",
    f"{base}/api/issues/{issue_id}",
    token=token,
    body={"sections": sections},
  )
  print(f"Done. Updated {changed} day(s); classItems now {len(items)}.")


if __name__ == "__main__":
  main()
