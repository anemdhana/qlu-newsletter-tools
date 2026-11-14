#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import daywise JSON (day-592 shape) into Issue → Themes → themeItems.

Converts sections → Markdown matching the Telugu lecture style:

  **Speaker:** …
  **Topic:** …
  **Original Video:** …

  ### Section title

  paragraph…

Matches an existing theme row (by series day index / title), then fills
titleEn + fullStoryEn (or TE fields when language is te).

Examples:

  python scripts/import_theme_day_json.py ^
    --json "out\\theme-day-json\\…\\day-07-en.json" ^
    --month 2026-11 --heading-needle "గణేశ"

  python scripts/import_theme_day_json.py --folder "out\\…\\ganesha" --lang en

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

from export_theme_day_json import find_themes_section  # noqa: E402
from import_theme_images import serialize_theme_item  # noqa: E402
from import_theme_readmore import (  # noqa: E402
  day_from_title,
  find_issue,
  http_json,
  login,
)

META_TE_RE = {
  "speaker": re.compile(r"\*\*ప్రసంగకర్త:\*\*\s*(.+)", re.I),
  "topic": re.compile(r"\*\*అంశం:\*\*\s*(.+)", re.I),
  "video": re.compile(r"\*\*మూల వీడియో:\*\*\s*(.+)", re.I),
}
META_EN_RE = {
  "speaker": re.compile(r"\*\*Speaker:\*\*\s*(.+)", re.I),
  "topic": re.compile(r"\*\*(?:Topic|Theme):\*\*\s*(.+)", re.I),
  "video": re.compile(
    r"\*\*(?:Original Video|Video):\*\*\s*(.+)",
    re.I,
  ),
}
YT_RE = re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+")


def load_day_json(path: Path) -> dict:
  if not path.is_file():
    raise SystemExit(f"JSON not found: {path}")
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except json.JSONDecodeError as e:
    raise SystemExit(f"Invalid JSON {path}: {e}") from e
  if not isinstance(data, dict):
    raise SystemExit(f"Expected object in {path}")
  if not data.get("sections"):
    raise SystemExit(f"No sections in {path}")
  return data


def extract_meta(md: str) -> dict[str, str]:
  out: dict[str, str] = {}
  text = md or ""
  for key, rx in {**META_TE_RE, **META_EN_RE}.items():
    if key in out:
      continue
    m = rx.search(text)
    if m:
      out[key] = m.group(1).strip().rstrip("*").strip()
  if "video" not in out:
    m = YT_RE.search(text)
    if m:
      out["video"] = m.group(0)
  return out


def day_json_to_markdown(doc: dict, *, peer_md: str = "") -> str:
  """Build TE-style Markdown from daywise JSON (### sections + optional meta)."""
  lang = str(doc.get("language") or "te").lower()
  title = str(doc.get("title") or "").strip()
  meta = extract_meta(peer_md)
  lines: list[str] = []

  if lang.startswith("en"):
    if meta.get("speaker"):
      lines.append(f"**Speaker:** {meta['speaker']}")
    if title or meta.get("topic"):
      lines.append(f"**Topic:** {title or meta['topic']}")
    if meta.get("video"):
      lines.append(f"**Original Video:** {meta['video']}")
  else:
    if meta.get("speaker"):
      lines.append(f"**ప్రసంగకర్త:** {meta['speaker']}")
    if title or meta.get("topic"):
      lines.append(f"**అంశం:** {title or meta['topic']}")
    if meta.get("video"):
      lines.append(f"**మూల వీడియో:** {meta['video']}")

  if lines:
    lines.append("")

  for sec in doc.get("sections") or []:
    if not isinstance(sec, dict):
      continue
    sec_title = str(sec.get("title") or "").strip()
    if sec_title:
      lines.append(f"### {sec_title}")
      lines.append("")
    content = sec.get("content") or []
    if isinstance(content, str):
      content = [content]
    for para in content:
      text = str(para or "").strip()
      if text:
        lines.append(text)
        lines.append("")

  return "\n".join(lines).rstrip() + "\n"


def title_overlap_score(a: str, b: str) -> int:
  def tokens(s: str) -> set[str]:
    parts = re.findall(r"[A-Za-z\u0C00-\u0C7F0-9]{3,}", (s or "").casefold())
    return set(parts)

  ta, tb = tokens(a), tokens(b)
  if not ta or not tb:
    return 0
  return len(ta & tb)


def match_theme_index(items: list[dict], doc: dict) -> tuple[int | None, str]:
  """Match by 1-based series dayNumber (export index), then title overlap."""
  day = doc.get("dayNumber")
  try:
    day_i = int(day) if day is not None else None
  except (TypeError, ValueError):
    day_i = None

  title = str(doc.get("title") or "")

  if day_i is not None and 1 <= day_i <= len(items):
    # Prefer exact slot used by export (day N → index N-1) when titles don't carry
    # a Jnanodayam calendar day.
    idx = day_i - 1
    item = items[idx]
    item_title = str(item.get("titleTe") or item.get("titleEn") or "")
    cal = day_from_title(item_title)
    if cal is None or cal == day_i or title_overlap_score(title, item_title) > 0:
      return idx, f"series-day={day_i}"

  # Calendar day in item titles (Devi / Speak Peace style)
  if day_i is not None:
    for i, item in enumerate(items):
      blob = " ".join(
        str(item.get(k) or "")
        for k in ("titleTe", "titleEn", "fullStoryTe", "fullStoryEn", "blurbTe")
      )
      if day_from_title(blob) == day_i:
        return i, f"calendar-day={day_i}"

  best_i, best_score = None, 0
  for i, item in enumerate(items):
    item_title = str(item.get("titleTe") or item.get("titleEn") or "")
    score = title_overlap_score(title, item_title)
    if score > best_score:
      best_i, best_score = i, score
  if best_i is not None and best_score >= 2:
    return best_i, f"title-overlap={best_score}"

  return None, "no-match"


def apply_day_json_to_item(item: dict, doc: dict, markdown: str) -> dict:
  lang = str(doc.get("language") or "te").lower()
  out = serialize_theme_item(item)
  title = str(doc.get("title") or "").strip()
  if lang.startswith("en"):
    if title:
      out["titleEn"] = title
    out["fullStoryEn"] = markdown
    # Light blurb from first paragraph if empty
    if not (out.get("blurbEn") or "").strip():
      secs = doc.get("sections") or []
      if secs and isinstance(secs[0], dict):
        paras = secs[0].get("content") or []
        if paras:
          out["blurbEn"] = str(paras[0]).strip()[:500]
  else:
    if title:
      out["titleTe"] = title
    out["fullStoryTe"] = markdown
    if not (out.get("blurbTe") or "").strip():
      secs = doc.get("sections") or []
      if secs and isinstance(secs[0], dict):
        paras = secs[0].get("content") or []
        if paras:
          out["blurbTe"] = str(paras[0]).strip()[:500]
  return out


def collect_json_files(args: argparse.Namespace) -> list[Path]:
  files: list[Path] = []
  if args.json:
    files.append(Path(args.json))
  if args.folder:
    folder = Path(args.folder)
    if not folder.is_dir():
      raise SystemExit(f"Folder not found: {folder}")
    if args.lang == "en":
      files.extend(sorted(folder.glob("*-en.json")))
      files.extend(sorted(folder.glob("day-*-en.json")))
    elif args.lang == "te":
      files.extend(sorted(folder.glob("*-te.json")))
      files.extend(sorted(folder.glob("day-*-te.json")))
    else:
      files.extend(sorted(folder.glob("*.json")))
  # de-dupe preserve order
  seen: set[str] = set()
  out: list[Path] = []
  for p in files:
    key = str(p.resolve()) if p.exists() else str(p)
    if key in seen:
      continue
    seen.add(key)
    out.append(p)
  if not out:
    raise SystemExit("Provide --json and/or --folder with daywise JSON files.")
  return out


def main() -> None:
  ap = argparse.ArgumentParser(
    description="Import daywise JSON into Issue Themes (TE-style Markdown)",
  )
  ap.add_argument("--json", help="One day-NN-te.json / day-NN-en.json")
  ap.add_argument("--folder", help="Folder of daywise JSON files")
  ap.add_argument(
    "--lang",
    choices=("te", "en", "both"),
    default="both",
    help="When using --folder, which files to pick (default: both)",
  )
  ap.add_argument("--month", default="2026-11")
  ap.add_argument(
    "--heading-needle",
    default="గణేశ",
    help='Themes section filter (default: "గణేశ")',
  )
  ap.add_argument("--base", default=os.environ.get("PAYLOAD_URL", "http://localhost:3000"))
  ap.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL", "admin@qlu.local"))
  ap.add_argument(
    "--password",
    default=os.environ.get("SEED_ADMIN_PASSWORD", "qlu-admin-change-me"),
  )
  ap.add_argument("--dry-run", action="store_true")
  args = ap.parse_args()

  paths = collect_json_files(args)
  base = args.base.rstrip("/")
  token = login(base, args.email, args.password)
  issue = find_issue(base, args.month, token)
  issue_id = issue["id"]
  sections = list(issue.get("sections") or [])
  themes = find_themes_section(issue, args.heading_needle)
  # find index in sections list
  idx = None
  for i, s in enumerate(sections):
    if s is themes or (
      s.get("key") == "themes"
      and (s.get("id") and s.get("id") == themes.get("id"))
    ):
      idx = i
      break
  if idx is None:
    for i, s in enumerate(sections):
      if s.get("key") != "themes":
        continue
      blob = f"{s.get('headingTe') or ''} {s.get('headingEn') or ''}"
      if args.heading_needle.lower() in blob.lower():
        idx = i
        themes = s
        break
  if idx is None:
    raise SystemExit("Could not locate Themes section index for PATCH.")

  items = [serialize_theme_item(it) for it in (themes.get("themeItems") or [])]
  print(f"Issue {args.month} id={issue_id}")
  print(f"Themes: {themes.get('headingTe')}")
  print(f"Items: {len(items)} · files: {len(paths)}")

  changed = 0
  for path in paths:
    doc = load_day_json(path)
    match_i, how = match_theme_index(items, doc)
    if match_i is None:
      print(f"  skip {path.name} ({how})")
      continue
    peer_md = ""
    lang = str(doc.get("language") or "").lower()
    if lang.startswith("en"):
      peer_md = str(items[match_i].get("fullStoryTe") or "")
    else:
      peer_md = str(items[match_i].get("fullStoryEn") or "")
    md = day_json_to_markdown(doc, peer_md=peer_md)
    title = str(doc.get("title") or "")[:72]
    print(
      f"  {'would update' if args.dry_run else 'update'} [{match_i}] {path.name}\n"
      f"      → {title} · {len(doc.get('sections') or [])} sections · match={how}\n"
      f"      markdown: {len(md)} chars"
    )
    if not args.dry_run:
      items[match_i] = apply_day_json_to_item(items[match_i], doc, md)
    changed += 1

  if not changed:
    print("Nothing to import.")
    return

  if args.dry_run:
    print(f"Dry run — would update {changed} theme item(s).")
    return

  themes = {**themes, "themeItems": items}
  themes.pop("themeItemsNav", None)
  sections[idx] = themes
  print(f"PATCHing issue {issue_id} …")
  http_json(
    "PATCH",
    f"{base}/api/issues/{issue_id}",
    token=token,
    body={"sections": sections},
  )
  print(f"Done. Updated {changed} theme item(s).")


if __name__ == "__main__":
  main()
