#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collapse Devi Navaratri Themes → one series card.

- Title + blurb from v4 blurb JSON (EN + TE)
- Thumbnail from Featured Classes Devi card (fallback: first reading cover)
- Read more (fullStory) = daySummaries, each with source YouTube link
  (video ids taken from existing per-day theme frames / fullStory meta)

Also syncs Featured Classes insight/title/image to the same v4 blurb.

  python scripts/import_devi_theme_series.py --month 2026-11
  python scripts/import_devi_theme_series.py --folder "C:\\…\\drive-download-…" --dry-run
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

from import_devi_featured_class import (  # noqa: E402
  STORY_URL,
  SERIES_BADGE,
  find_devi_item,
  first_devi_cover,
)
from import_featured_classes import (  # noqa: E402
  ensure_classes_section,
  insight_from_blurb,
  load_json,
  serialize_class_item,
)
from import_jnanodayam_reading import login  # noqa: E402
from import_theme_images import media_id, serialize_theme_item  # noqa: E402
from import_theme_readmore import find_issue, http_json  # noqa: E402

DEFAULT_FOLDER = (
  r"C:\Users\dhana\Downloads\drive-download-20261115T052214Z-1-001"
)
YT_RE = re.compile(
  r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w\-]+)"
)
VID_IN_NAME = re.compile(r"\[([A-Za-z0-9_-]{11})\]")
VID_META_RE = re.compile(
  r"\*\*(?:Original Video|Video|మూల వీడియో):\*\*\s*(.+)",
  re.I,
)


def find_devi_themes(sections: list[dict]) -> tuple[int, dict]:
  hits: list[tuple[int, dict]] = []
  for i, s in enumerate(sections):
    if s.get("key") != "themes":
      continue
    heading = f"{s.get('headingTe') or ''} {s.get('headingEn') or ''}"
    if (
      "నవరాత్ర" in heading
      or "navratri" in heading.lower()
      or "navaratri" in heading.lower()
    ):
      hits.append((i, s))
  if not hits:
    raise SystemExit("No Devi Navaratri themes section found")
  if len(hits) > 1:
    raise SystemExit(f"Multiple Devi themes sections: {[h[1].get('headingTe') for h in hits]}")
  return hits[0]


def video_id_from_text(text: str) -> str | None:
  m = VID_META_RE.search(text or "")
  if m:
    m2 = YT_RE.search(m.group(1))
    if m2:
      return m2.group(1)
  m3 = YT_RE.search(text or "")
  return m3.group(1) if m3 else None


def video_id_from_media(base: str, token: str, mid) -> str | None:
  if mid is None:
    return None
  try:
    doc = http_json("GET", f"{base}/api/media/{mid}", token=token)
  except SystemExit:
    return None
  name = str(doc.get("filename") or doc.get("alt") or "")
  m = VID_IN_NAME.search(name)
  return m.group(1) if m else None


def collect_day_videos(base: str, token: str, items: list[dict]) -> list[str | None]:
  """One YouTube id per existing day row (index order)."""
  out: list[str | None] = []
  for it in items:
    blob = "\n".join(
      str(it.get(k) or "")
      for k in ("fullStoryEn", "fullStoryTe", "blurbEn", "blurbTe", "storyUrl")
    )
    vid = video_id_from_text(blob)
    if not vid:
      vid = video_id_from_media(base, token, media_id(it.get("image")))
    out.append(vid)
  return out


def build_full_story(
  summaries: list,
  videos: list[str | None],
  *,
  lang: str,
) -> str:
  lines: list[str] = []
  video_label = "**Original Video:**" if lang == "en" else "**మూల వీడియో:**"
  for i, raw in enumerate(summaries):
    text = str(raw or "").strip()
    if not text:
      continue
    lines.append(text)
    lines.append("")
    vid = videos[i] if i < len(videos) else None
    if vid:
      lines.append(f"{video_label} https://www.youtube.com/watch?v={vid}")
      lines.append("")
  return "\n".join(lines).rstrip() + "\n"


def prefer_blurb_paths(folder: Path, lang: str) -> Path | None:
  """Prefer *-blurb-v4.json, else *-blurb.json."""
  v4 = folder / f"devi-navaratri-10-days-{lang}-blurb-v4.json"
  v1 = folder / f"devi-navaratri-10-days-{lang}-blurb.json"
  if v4.is_file():
    return v4
  if v1.is_file():
    return v1
  return None


def main() -> None:
  ap = argparse.ArgumentParser(
    description="Collapse Devi Themes to one series card (v4 blurb + daySummaries)"
  )
  ap.add_argument("--folder", default=DEFAULT_FOLDER)
  ap.add_argument("--month", default="2026-11")
  ap.add_argument("--base", default=os.environ.get("PAYLOAD_URL", "http://localhost:3000"))
  ap.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL", "admin@qlu.local"))
  ap.add_argument(
    "--password",
    default=os.environ.get("SEED_ADMIN_PASSWORD", "qlu-admin-change-me"),
  )
  ap.add_argument("--dry-run", action="store_true")
  ap.add_argument(
    "--skip-featured",
    action="store_true",
    help="Do not sync Featured Classes Devi card",
  )
  args = ap.parse_args()

  folder = Path(args.folder)
  te_path = prefer_blurb_paths(folder, "te")
  en_path = prefer_blurb_paths(folder, "en")
  if not te_path and not en_path:
    raise SystemExit(f"Missing Devi blurb JSON in {folder}")

  te_blurb = load_json(te_path) if te_path else None
  en_blurb = load_json(en_path) if en_path else None
  title_te = str((te_blurb or {}).get("title") or "").strip()
  title_en = str((en_blurb or {}).get("title") or "").strip()
  blurb_te = insight_from_blurb(te_blurb)
  blurb_en = insight_from_blurb(en_blurb)
  summaries_te = list((te_blurb or {}).get("daySummaries") or [])
  summaries_en = list((en_blurb or {}).get("daySummaries") or [])

  base = args.base.rstrip("/")
  token = login(base, args.email, args.password)
  issue = find_issue(base, args.month, token)
  issue_id = issue.get("id")
  sections = list(issue.get("sections") or [])

  t_idx, themes = find_devi_themes(sections)
  old_items = list(themes.get("themeItems") or [])
  videos = collect_day_videos(base, token, old_items)
  print(f"Existing Devi themeItems: {len(old_items)}")
  for i, vid in enumerate(videos):
    print(f"  day {i + 1:02d} video={vid}")

  # Thumbnail: Featured Classes Devi image, else reading cover, else first old image
  cover_id = None
  c_idx, classes_sec = ensure_classes_section(sections)
  class_items = [serialize_class_item(it) for it in (classes_sec.get("classItems") or [])]
  match_i = find_devi_item(class_items)
  if match_i is not None:
    cover_id = media_id(class_items[match_i].get("image"))
  if cover_id is None:
    cover_id = first_devi_cover(base, token)
  if cover_id is None and old_items:
    cover_id = media_id(old_items[0].get("image"))

  full_en = build_full_story(summaries_en, videos, lang="en") if summaries_en else ""
  full_te = build_full_story(summaries_te, videos, lang="te") if summaries_te else ""

  heading_te = (
    f"జ్ఞానోదయం (561–570 రోజులు) | {title_te}"
    if title_te
    else (themes.get("headingTe") or "")
  )
  heading_en = (
    f"Jnanodayam (Days 561–570) | {title_en}"
    if title_en
    else (themes.get("headingEn") or "")
  )

  theme_row: dict = {
    "titleTe": title_te or "దేవీ నవరాత్రుల జ్ఞానం",
    "titleEn": title_en or "Devi Navaratrula Jnanam",
    "blurbTe": blurb_te,
    "blurbEn": blurb_en,
    "fullStoryTe": full_te,
    "fullStoryEn": full_en,
    "images": [],
  }
  # Keep drawer (daySummaries); no external storyUrl
  theme_row.pop("storyUrl", None)
  if cover_id is not None:
    theme_row["image"] = cover_id
  # Preserve array row id if collapsing onto first item
  if old_items and old_items[0].get("id"):
    theme_row["id"] = old_items[0]["id"]

  print("→ One Themes card")
  print(f"  titleEn: {theme_row['titleEn'][:70]}")
  print(f"  blurbEn chars: {len(blurb_en)}  fullStoryEn chars: {len(full_en)}")
  print(f"  blurbTe chars: {len(blurb_te)}  fullStoryTe chars: {len(full_te)}")
  print(f"  image: {cover_id}")
  print(f"  headingEn: {heading_en[:80]}")

  if not args.skip_featured:
    insight_te = blurb_te
    insight_en = blurb_en
    base_item = serialize_class_item(class_items[match_i]) if match_i is not None else {}
    class_payload = {
      **base_item,
      "titleTe": title_te or base_item.get("titleTe") or "దేవీ నవరాత్రుల జ్ఞానం",
      "titleEn": title_en or base_item.get("titleEn") or "Devi Navaratrula Jnanam",
      "date": SERIES_BADGE,
      "speaker": base_item.get("speaker") or "Dr. Newton Kondaveti",
      "storyUrl": STORY_URL,
      "fullStoryTe": "",
      "fullStoryEn": "",
      "insightTe": insight_te,
      "insightEn": insight_en,
    }
    class_payload.pop("jnanodayamDay", None)
    if cover_id is not None:
      class_payload["image"] = cover_id
    action = "update" if match_i is not None else "create"
    print(f"→ Featured Classes [{action}] synced to v4 blurb")

  if args.dry_run:
    print("[dry-run] skip PATCH")
    print("--- EN fullStory preview ---")
    print(full_en[:600])
    return

  themes = {
    **themes,
    "headingTe": heading_te,
    "headingEn": heading_en,
    "asCard": True,
    "themeItems": [theme_row],
  }
  themes.pop("themeItemsNav", None)
  sections[t_idx] = themes

  if not args.skip_featured:
    if match_i is not None:
      class_items[match_i] = class_payload
    else:
      class_items.insert(0, class_payload)
    classes_sec["classItems"] = class_items
    sections[c_idx] = classes_sec

  http_json(
    "PATCH",
    f"{base}/api/issues/{issue_id}",
    token=token,
    body={"sections": sections},
  )
  print(
    f"Done. Issue {args.month} id={issue_id}; "
    f"Devi themeItems → 1; featured synced={not args.skip_featured}."
  )


if __name__ == "__main__":
  main()
