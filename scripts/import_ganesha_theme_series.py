#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collapse Ganesha Themes → one series card.

- Title + blurb from ganesha-10-days-*-blurb.json
- Thumbnail from provided PNG (uploaded to media)
- Read more (fullStory) = daySummaries + source YouTube per day

  python scripts/import_ganesha_theme_series.py --month 2026-11
  python scripts/import_ganesha_theme_series.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from import_devi_theme_series import (  # noqa: E402
  build_full_story,
  collect_day_videos,
)
from import_featured_classes import insight_from_blurb, load_json  # noqa: E402
from import_jnanodayam_reading import login  # noqa: E402
from import_theme_images import find_existing_media_id, upload_media  # noqa: E402
from import_theme_readmore import find_issue, http_json  # noqa: E402

DEFAULT_FOLDER = (
  r"C:\Users\dhana\Downloads\drive-download-20261115T052214Z-1-001"
)
DEFAULT_THUMB = "Radiant Ganesha of Wisdom and Blessings.png"
DEFAULT_DAY_RANGE = "529–538"


def find_ganesha_themes(sections: list[dict]) -> tuple[int, dict]:
  hits: list[tuple[int, dict]] = []
  for i, s in enumerate(sections):
    if s.get("key") != "themes":
      continue
    heading = f"{s.get('headingTe') or ''} {s.get('headingEn') or ''}"
    low = heading.lower()
    if "గణేశ" in heading or "ganesha" in low or "ganapati" in low:
      hits.append((i, s))
  if not hits:
    raise SystemExit("No Ganesha themes section found")
  if len(hits) > 1:
    raise SystemExit(
      f"Multiple Ganesha themes sections: {[h[1].get('headingTe') for h in hits]}"
    )
  return hits[0]


def prefer_blurb_paths(folder: Path, lang: str) -> Path | None:
  for name in (
    f"ganesha-10-days-{lang}-blurb-v1.json",
    f"ganesha-10-days-{lang}-blurb.json",
  ):
    path = folder / name
    if path.is_file():
      return path
  return None


def resolve_thumb(folder: Path, thumb_arg: str) -> Path:
  path = Path(thumb_arg)
  if not path.is_file():
    path = folder / thumb_arg
  if not path.is_file():
    matches = sorted(folder.glob("*Ganesha*.png")) + sorted(
      folder.glob("*ganesha*.png")
    )
    if matches:
      path = matches[0]
  if not path.is_file():
    raise SystemExit(f"Thumbnail not found: {thumb_arg}")
  return path


def ensure_thumb_media(base: str, token: str, path: Path) -> int | str:
  existing = find_existing_media_id(base, token, path.name)
  if existing is not None:
    print(f"Reusing media id={existing} for {path.name}")
    return existing
  mid = upload_media(
    base, token, path, alt="Radiant Ganesha of Wisdom and Blessings"
  )
  print(f"Uploaded media id={mid} for {path.name}")
  return mid


def main() -> None:
  ap = argparse.ArgumentParser(
    description="Collapse Ganesha Themes to one series card"
  )
  ap.add_argument("--folder", default=DEFAULT_FOLDER)
  ap.add_argument("--thumb", default=DEFAULT_THUMB)
  ap.add_argument("--month", default="2026-11")
  ap.add_argument("--base", default=os.environ.get("PAYLOAD_URL", "http://localhost:3000"))
  ap.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL", "admin@qlu.local"))
  ap.add_argument(
    "--password",
    default=os.environ.get("SEED_ADMIN_PASSWORD", "qlu-admin-change-me"),
  )
  ap.add_argument("--dry-run", action="store_true")
  args = ap.parse_args()

  folder = Path(args.folder)
  te_path = prefer_blurb_paths(folder, "te")
  en_path = prefer_blurb_paths(folder, "en")
  if not te_path and not en_path:
    raise SystemExit(f"Missing Ganesha blurb JSON in {folder}")

  te_blurb = load_json(te_path) if te_path else None
  en_blurb = load_json(en_path) if en_path else None
  print(f"blurb TE: {te_path.name if te_path else '-'}")
  print(f"blurb EN: {en_path.name if en_path else '-'}")

  title_te = str((te_blurb or {}).get("title") or "").strip()
  title_en = str((en_blurb or {}).get("title") or "").strip()
  blurb_te = insight_from_blurb(te_blurb)
  blurb_en = insight_from_blurb(en_blurb)
  summaries_te = list((te_blurb or {}).get("daySummaries") or [])
  summaries_en = list((en_blurb or {}).get("daySummaries") or [])

  thumb_path = resolve_thumb(folder, args.thumb)
  print(f"thumb: {thumb_path}")

  base = args.base.rstrip("/")
  token = login(base, args.email, args.password)
  issue = find_issue(base, args.month, token)
  issue_id = issue.get("id")
  sections = list(issue.get("sections") or [])

  t_idx, themes = find_ganesha_themes(sections)
  old_items = list(themes.get("themeItems") or [])
  videos = collect_day_videos(base, token, old_items)
  print(f"Existing Ganesha themeItems: {len(old_items)}")
  for i, vid in enumerate(videos):
    print(f"  day {i + 1:02d} video={vid}")

  if args.dry_run:
    cover_id = "(upload skipped)"
  else:
    cover_id = ensure_thumb_media(base, token, thumb_path)

  full_en = build_full_story(summaries_en, videos, lang="en") if summaries_en else ""
  full_te = build_full_story(summaries_te, videos, lang="te") if summaries_te else ""

  heading_te = (
    f"జ్ఞానోదయం ({DEFAULT_DAY_RANGE} రోజులు) | {title_te}"
    if title_te
    else (themes.get("headingTe") or "")
  )
  heading_en = (
    f"Jnanodayam (Days {DEFAULT_DAY_RANGE}) | {title_en}"
    if title_en
    else (themes.get("headingEn") or "")
  )

  theme_row: dict = {
    "titleTe": title_te or "గణేశ తత్త్వం",
    "titleEn": title_en or "Ganesha Tattva",
    "blurbTe": blurb_te,
    "blurbEn": blurb_en,
    "fullStoryTe": full_te,
    "fullStoryEn": full_en,
    "images": [],
  }
  theme_row.pop("storyUrl", None)
  if not args.dry_run and cover_id is not None:
    theme_row["image"] = cover_id
  if old_items and old_items[0].get("id"):
    theme_row["id"] = old_items[0]["id"]

  print("→ One Themes card")
  print(f"  titleEn: {theme_row['titleEn'][:70]}")
  print(f"  blurbEn chars: {len(blurb_en)}  fullStoryEn chars: {len(full_en)}")
  print(f"  blurbTe chars: {len(blurb_te)}  fullStoryTe chars: {len(full_te)}")
  print(f"  image: {cover_id}")
  print(f"  headingEn: {heading_en[:90]}")

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

  http_json(
    "PATCH",
    f"{base}/api/issues/{issue_id}",
    token=token,
    body={"sections": sections},
  )
  print(f"Done. Issue {args.month} id={issue_id}; Ganesha themeItems → 1.")


if __name__ == "__main__":
  main()
