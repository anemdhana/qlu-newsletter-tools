#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Add / update Featured Classes card for Devi Navaratrula Jnanam.

Uses blurb JSON + first published devi-navaratri reading cover.
Read more → /jnanodayam/devi-navaratri/ (new tab via storyUrl; no drawer).

  python scripts/import_devi_featured_class.py --month 2026-11
  python scripts/import_devi_featured_class.py --folder "C:\\…\\drive-download-…" --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from import_featured_classes import (  # noqa: E402
  insight_from_blurb,
  load_json,
  serialize_class_item,
  ensure_classes_section,
)
from import_jnanodayam_reading import login  # noqa: E402
from import_theme_images import media_id  # noqa: E402
from import_theme_readmore import find_issue, http_json  # noqa: E402

DEFAULT_FOLDER = (
  r"C:\Users\dhana\Downloads\drive-download-20261115T052214Z-1-001"
)
STORY_URL = "/jnanodayam/devi-navaratri/"
SERIES_BADGE = "10 Days"  # shown as "10 రోజులు" on TE via classCardBadge


def find_devi_item(items: list[dict]) -> int | None:
  needle = STORY_URL.rstrip("/")
  for i, it in enumerate(items):
    url = str(it.get("storyUrl") or "").rstrip("/")
    if url.endswith(needle) or "devi-navaratri" in url:
      return i
    title = f"{it.get('titleEn') or ''} {it.get('titleTe') or ''}".lower()
    if "navaratri" in title or "నవరాత్ర" in title:
      return i
  return None


def first_devi_cover(base: str, token: str) -> int | None:
  q = (
    f"{base}/api/jnanodayam-readings?limit=1&depth=1&sort=day"
    f"&where[and][0][series][equals]=devi-navaratri"
    f"&where[and][1][published][equals]=true"
  )
  out = http_json("GET", q, token=token)
  docs = out.get("docs") or []
  if not docs:
    return None
  return media_id(docs[0].get("cover"))


def main() -> None:
  ap = argparse.ArgumentParser(description="Import Devi Navaratri Featured Class card")
  ap.add_argument("--folder", default=DEFAULT_FOLDER)
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
  te_blurb_path = folder / "devi-navaratri-10-days-te-blurb.json"
  en_blurb_path = folder / "devi-navaratri-10-days-en-blurb.json"
  if not te_blurb_path.is_file() and not en_blurb_path.is_file():
    raise SystemExit(f"Missing blurb JSON in {folder}")

  te_blurb = load_json(te_blurb_path) if te_blurb_path.is_file() else None
  en_blurb = load_json(en_blurb_path) if en_blurb_path.is_file() else None
  title_te = str((te_blurb or {}).get("title") or "").strip()
  title_en = str((en_blurb or {}).get("title") or "").strip()
  insight_te = insight_from_blurb(te_blurb)
  insight_en = insight_from_blurb(en_blurb)

  base = args.base.rstrip("/")
  token = login(base, args.email, args.password)
  issue = find_issue(base, args.month, token)
  issue_id = issue.get("id")
  sections = list(issue.get("sections") or [])
  idx, classes_sec = ensure_classes_section(sections)
  items = [serialize_class_item(it) for it in (classes_sec.get("classItems") or [])]

  cover_id = first_devi_cover(base, token)
  match_i = find_devi_item(items)
  base_item = serialize_class_item(items[match_i]) if match_i is not None else {}

  payload = {
    **base_item,
    "titleTe": title_te or base_item.get("titleTe") or "దేవీ నవరాత్రుల జ్ఞానం",
    "titleEn": title_en or base_item.get("titleEn") or "Devi Navaratrula Jnanam",
    "date": SERIES_BADGE,
    "speaker": base_item.get("speaker") or "Dr. Newton Kondaveti",
    "storyUrl": STORY_URL,
    # External series page — no in-newsletter drawer
    "fullStoryTe": "",
    "fullStoryEn": "",
  }
  payload.pop("jnanodayamDay", None)
  if insight_te:
    payload["insightTe"] = insight_te
  if insight_en:
    payload["insightEn"] = insight_en
  if cover_id is not None:
    payload["image"] = cover_id
  elif match_i is not None:
    mid = media_id(items[match_i].get("image"))
    if mid is not None:
      payload["image"] = mid

  action = "update" if match_i is not None else "create"
  print(f"Devi Featured Class [{action}]")
  print(f"  titleEn: {payload['titleEn'][:70]}")
  print(f"  storyUrl: {payload['storyUrl']}")
  print(f"  insightTe={len(insight_te)} insightEn={len(insight_en)} cover={cover_id}")

  if args.dry_run:
    print("[dry-run] skip PATCH")
    return

  if match_i is not None:
    items[match_i] = payload
  else:
    # Put series card first (like hub programmes before daily days)
    items.insert(0, payload)

  classes_sec["classItems"] = items
  sections[idx] = classes_sec
  http_json(
    "PATCH",
    f"{base}/api/issues/{issue_id}",
    token=token,
    body={"sections": sections},
  )
  print(f"Done. Issue {args.month} id={issue_id}; classItems now {len(items)}.")


if __name__ == "__main__":
  main()
