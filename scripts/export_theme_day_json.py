#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export Issue → Themes → themeItems as daywise JSON (same shape as day-592-te.json).

One file per theme class per language:

  {
    "dayNumber": 538,
    "title": "…",
    "language": "te",
    "sections": [
      { "title": "…", "content": ["para…"], "minutes": 2, "startSec": null }
    ]
  }

Filenames: `{theme-title}-day-{NNN}-te.json` (title prefix + day + lang).

Examples:

  python scripts/export_theme_day_json.py --month 2026-11
  python scripts/export_theme_day_json.py --month 2026-11 -o out\\theme-json --lang both
  python scripts/export_theme_day_json.py --month 2026-11 --heading-needle "గణేశ" --dry-run

Auth (Payload admin):
  PAYLOAD_URL          default http://localhost:3000
  SEED_ADMIN_EMAIL     default admin@qlu.local
  SEED_ADMIN_PASSWORD  default qlu-admin-change-me
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

from import_theme_readmore import (  # noqa: E402
  _jnanodayam_day_from_text,
  day_from_title,
  find_issue,
  login,
  strip_editorial_notes,
  strip_md,
)

META_LINE_RE = re.compile(
  r"^\*\*(?:ప్రసంగకర్త|అంశం|మూల వీడియో|Speaker|Topic|Original Video|Video)\s*:\*\*",
  re.I,
)
H_SECTION_RE = re.compile(r"(?m)^(#{2,3})\s+(.+?)\s*$")
BOLD_SECTION_RE = re.compile(r"(?m)^\*\*([^*:\n][^*\n]{0,120}?)\*\*\s*:?\s*")
UNSAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def keep_markdown(md_chunk: str) -> str:
  """Normalize newlines only — keep **, links, lists, quotes, symbols as in source."""
  text = strip_md(md_chunk)
  text = re.sub(r"\n{3,}", "\n\n", text)
  return text.strip()


def heading_title(raw: str) -> str:
  """Section title from a ## / ### line — trim only, keep inline markdown/symbols."""
  return keep_markdown(raw)


def paragraphs(text: str) -> list[str]:
  parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
  out: list[str] = []
  for p in parts:
    # Soft-wrap join, but preserve markdown list / quote line structure
    if re.search(r"(?m)^(?:[-*+] |\d+\. |> )", p):
      line = p.strip()
    else:
      line = re.sub(r"[ \t]*\n[ \t]*", " ", p).strip()
    if not line:
      continue
    if META_LINE_RE.match(line) or re.match(
      r"^(?:ప్రసంగకర్త|అంశం|మూల వీడియో|Speaker|Topic)\s*:",
      line,
      flags=re.I,
    ):
      continue
    out.append(line)
  return out


def estimate_minutes(paras: list[str]) -> int:
  words = len(re.findall(r"\S+", " ".join(paras)))
  return max(1, round(words / 200) or 1)


def drop_meta_preamble(md: str) -> str:
  """Remove leading speaker/topic/video meta lines and a lone ## Read more banner."""
  text = strip_editorial_notes(strip_md(md))
  lines = text.split("\n")
  i = 0
  while i < len(lines):
    raw = lines[i].strip()
    if not raw:
      i += 1
      continue
    if META_LINE_RE.match(raw):
      i += 1
      continue
    if re.match(r"^#{1,2}\s+.*(Read more|విస్తృత సారాంశం)", raw, flags=re.I):
      i += 1
      continue
    break
  return "\n".join(lines[i:]).strip()


def sections_from_headings(md: str) -> list[dict] | None:
  matches = list(H_SECTION_RE.finditer(md))
  # Prefer ### if present; else ## (but skip a solitary Read-more banner)
  hashes = {m.group(1) for m in matches}
  level = "###" if "###" in hashes else ("##" if "##" in hashes else None)
  if not level:
    return None
  chosen = [m for m in matches if m.group(1) == level]
  if level == "##":
    chosen = [
      m
      for m in chosen
      if not re.search(r"Read more|విస్తృత సారాంశం", m.group(2), flags=re.I)
    ]
  if len(chosen) < 1:
    return None

  sections: list[dict] = []
  for i, m in enumerate(chosen):
    title = heading_title(m.group(2))
    start = m.end()
    end = chosen[i + 1].start() if i + 1 < len(chosen) else len(md)
    body = keep_markdown(md[start:end])
    content = paragraphs(body)
    if not title and not content:
      continue
    sections.append(
      {
        "title": title or f"Section {len(sections) + 1}",
        "content": content or ([body] if body else []),
        "minutes": estimate_minutes(content),
        "startSec": None,
      }
    )
  return sections or None


def sections_from_bold_leads(md: str) -> list[dict] | None:
  """Short card blurbs shaped as **Lead:** paragraph blocks."""
  matches = list(BOLD_SECTION_RE.finditer(md))
  if len(matches) < 2:
    return None
  sections: list[dict] = []
  for i, m in enumerate(matches):
    title = heading_title(m.group(1)).rstrip(":")
    if META_LINE_RE.match(m.group(0)):
      continue
    start = m.end()
    end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
    body = keep_markdown(md[start:end])
    content = paragraphs(body)
    if not content and body:
      content = [body]
    if not title or not content:
      continue
    sections.append(
      {
        "title": title,
        "content": content,
        "minutes": estimate_minutes(content),
        "startSec": None,
      }
    )
  return sections if len(sections) >= 2 else None


def sections_from_markdown(md: str, fallback_title: str) -> list[dict]:
  body = drop_meta_preamble(md)
  if not body:
    return []
  for builder in (sections_from_headings, sections_from_bold_leads):
    got = builder(body)
    if got:
      return got
  content = paragraphs(keep_markdown(body))
  if not content:
    return []
  return [
    {
      "title": fallback_title or "Reading",
      "content": content,
      "minutes": estimate_minutes(content),
      "startSec": None,
    }
  ]


def resolve_day(item: dict, md: str, index: int) -> int:
  for candidate in (
    day_from_title(str(item.get("titleTe") or "")),
    day_from_title(str(item.get("titleEn") or "")),
    _jnanodayam_day_from_text(md),
    _jnanodayam_day_from_text(str(item.get("blurbTe") or "")),
    _jnanodayam_day_from_text(str(item.get("blurbEn") or "")),
  ):
    if candidate is not None:
      return int(candidate)
  return index + 1


def safe_title_prefix(title: str, max_len: int = 72) -> str:
  s = UNSAFE_NAME_RE.sub("", title or "")
  s = re.sub(r"\s+", "-", s.strip())
  s = re.sub(r"-{2,}", "-", s).strip(".-")
  if not s:
    s = "theme"
  return s[:max_len]


def safe_series_folder(heading: str) -> str:
  """
  Folder name from Themes section heading.
  Keeps Telugu / dashes; maps '|' → fullwidth '｜' (Windows forbids '|').
  """
  s = (heading or "").strip()
  s = s.replace("|", "｜")
  s = re.sub(r'[<>:"/\\?*\x00-\x1f]+', "", s)
  s = re.sub(r"\s+", " ", s).strip(" .")
  return s or "themes"


def theme_to_day_json(
  item: dict,
  *,
  lang: str,
  index: int,
) -> dict | None:
  lang = lang.lower()
  title = str(item.get("titleTe") if lang == "te" else item.get("titleEn") or "").strip()
  if not title:
    title = str(item.get("titleTe") or item.get("titleEn") or f"Theme {index + 1}").strip()
  md = str(
    item.get("fullStoryTe") if lang == "te" else item.get("fullStoryEn") or ""
  ).strip()
  if not md:
    # Fall back to blurb if full story empty
    md = str(item.get("blurbTe") if lang == "te" else item.get("blurbEn") or "").strip()
  if not md:
    return None

  sections = sections_from_markdown(md, title)
  if not sections:
    return None

  day = resolve_day(item, md, index)
  return {
    "dayNumber": day,
    "title": title,
    "language": lang,
    "sections": sections,
  }


def find_themes_section(issue: dict, heading_needle: str | None) -> dict:
  sections = list(issue.get("sections") or [])
  themes = [s for s in sections if s.get("key") == "themes"]
  if not themes:
    raise SystemExit("No Themes section on that issue.")
  if heading_needle:
    needle = heading_needle.strip().lower()
    for s in themes:
      blob = " ".join(
        str(s.get(k) or "") for k in ("headingTe", "headingEn", "leadTe", "leadEn")
      ).lower()
      if needle in blob:
        return s
    raise SystemExit(f'No Themes section matching heading-needle="{heading_needle}"')
  return themes[0]


def main() -> None:
  ap = argparse.ArgumentParser(
    description="Export Issue themeItems as daywise JSON (day-592 shape)",
  )
  ap.add_argument("--month", default="2026-11", help="Issue month YYYY-MM")
  ap.add_argument(
    "-o",
    "--out",
    default="out/theme-day-json",
    help="Output folder (default: out/theme-day-json)",
  )
  ap.add_argument(
    "--lang",
    choices=("te", "en", "both"),
    default="both",
    help="Which language files to write (default: both)",
  )
  ap.add_argument(
    "--heading-needle",
    help="Pick Themes section whose heading/lead contains this text",
  )
  ap.add_argument("--base", default=os.environ.get("PAYLOAD_URL", "http://localhost:3000"))
  ap.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL", "admin@qlu.local"))
  ap.add_argument(
    "--password",
    default=os.environ.get("SEED_ADMIN_PASSWORD", "qlu-admin-change-me"),
  )
  ap.add_argument("--dry-run", action="store_true")
  args = ap.parse_args()

  base = args.base.rstrip("/")
  token = login(base, args.email, args.password)
  issue = find_issue(base, args.month, token)
  themes = find_themes_section(issue, args.heading_needle)
  items = list(themes.get("themeItems") or [])
  if not items:
    raise SystemExit("Themes section has no themeItems.")

  series_heading = (
    str(themes.get("headingTe") or "").strip()
    or str(themes.get("headingEn") or "").strip()
    or f"themes-{args.month}"
  )
  series_folder = safe_series_folder(series_heading)
  out_dir = Path(args.out) / series_folder
  if not args.dry_run:
    out_dir.mkdir(parents=True, exist_ok=True)

  langs = ["te", "en"] if args.lang == "both" else [args.lang]
  written = 0
  skipped = 0

  print(f"Issue {args.month} · {len(items)} theme(s)")
  print(f"Series folder: {series_folder}")
  print(f"Output: {out_dir}")
  for i, item in enumerate(items):
    for lang in langs:
      doc = theme_to_day_json(item, lang=lang, index=i)
      if not doc:
        skipped += 1
        continue
      prefix = safe_title_prefix(doc["title"])
      day = doc["dayNumber"]
      name = f"{prefix}-day-{day}-{lang}.json"
      path = out_dir / name
      print(
        f"  {'would write' if args.dry_run else 'write'} {name} "
        f"({len(doc['sections'])} sections)"
      )
      if not args.dry_run:
        path.write_text(
          json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
          encoding="utf-8",
        )
      written += 1

  print(f"Done. {'Would write' if args.dry_run else 'Wrote'} {written} file(s)"
        f"{f', skipped {skipped} empty lang(s)' if skipped else ''}.")


if __name__ == "__main__":
  main()
