#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import Jnanodayam Read More .md files into QLU News Issue → Themes → themeItems.

Matches the field shape already used for the Ganesha series (titleTe / blurbTe /
fullStoryTe) under the Themes section heading.

Example (from repo root):

  python scripts/import_theme_readmore.py ^
    --folder "C:\\Users\\dhana\\Downloads\\QLU_Ganesha_Days_535-538_Revised_ReadMore" ^
    --month 2026-11

  python scripts/import_theme_readmore.py --folder ... --month 2026-11 --dry-run

Auth (Payload admin):
  PAYLOAD_URL          default http://localhost:3000
  SEED_ADMIN_EMAIL     default admin@qlu.local
  SEED_ADMIN_PASSWORD  default qlu-admin-change-me
  Or pass --email / --password.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_FOLDER = (
  r"C:\Users\dhana\Downloads\QLU_Ganesha_Days_535-538_Revised_ReadMore"
)
DEFAULT_HEADING_NEEDLE = "శ్రీ గణేశ తత్త్వం"
DAY_RE = re.compile(r"(\d+)\s*వ\s*రోజు")
FILE_DAY_RE = re.compile(r"day[-_]?(\d+)", re.I)
EN_DAY_RE = re.compile(r"\bDay\s+(\d+)\b", re.I)
SPEAK_PEACE_RE = re.compile(
  r"Speak Peace\s*[-–—]\s*(.+?)\s+by\s+.+?\s*[-–—]?\s*Day\s+(\d+)\s*$",
  re.I,
)


def http_json(
  method: str,
  url: str,
  *,
  token: str | None = None,
  body: dict | None = None,
) -> dict:
  data = None
  headers = {"Accept": "application/json"}
  if body is not None:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers["Content-Type"] = "application/json"
  if token:
    headers["Authorization"] = f"JWT {token}"
  req = urllib.request.Request(url, data=data, headers=headers, method=method)
  try:
    with urllib.request.urlopen(req, timeout=120) as resp:
      raw = resp.read().decode("utf-8")
      return json.loads(raw) if raw.strip() else {}
  except urllib.error.HTTPError as e:
    detail = e.read().decode("utf-8", errors="replace")
    raise SystemExit(f"{method} {url} → HTTP {e.code}: {detail[:800]}") from e


def login(base: str, email: str, password: str) -> str:
  out = http_json(
    "POST",
    f"{base}/api/users/login",
    body={"email": email, "password": password},
  )
  token = out.get("token")
  if not token:
    raise SystemExit(f"Login failed for {email}: no token in response")
  return token


def find_issue(base: str, month: str, token: str) -> dict:
  from urllib.parse import quote

  url = (
    f"{base}/api/issues?limit=1&depth=1"
    f"&where[month][equals]={quote(month)}"
  )
  out = http_json("GET", url, token=token)
  docs = out.get("docs") or []
  if not docs:
    raise SystemExit(f"No issue found for month={month}")
  return docs[0]


def strip_md(text: str) -> str:
  return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def section_after(md: str, heading_re: str) -> str:
  m = re.search(heading_re, md, flags=re.I | re.M)
  if not m:
    return ""
  rest = md[m.end() :]
  nxt = re.search(r"^##\s+", rest, flags=re.M)
  if nxt:
    rest = rest[: nxt.start()]
  return rest.strip().strip("-").strip()


def meta_value(md: str, label: str) -> str:
  m = re.search(
    rf"\*\*{re.escape(label)}:\*\*\s*(.+)",
    md,
  )
  if not m:
    return ""
  return m.group(1).strip().rstrip("*").strip()


def normalize_title(title: str) -> str:
  # Match existing CMS style: జ్ఞానోదయం – NNNవ రోజు |
  title = title.strip().lstrip("#").strip()
  sp = SPEAK_PEACE_RE.search(title)
  if sp:
    topic = sp.group(1).strip().rstrip("-–— ").strip()
    day = sp.group(2)
    return f"జ్ఞానోదయం – {day}వ రోజు | Speak Peace — {topic}"
  title = re.sub(r"^(జ్ఞానోదయం)\s*[—–-]\s*", r"\1 – ", title, count=1)
  # English "… Day NNN" → Telugu day form when not already normalized
  if "వ రోజు" not in title:
    en = EN_DAY_RE.search(title)
    if en and title.lower().startswith("జ్ఞానోదయం"):
      day = en.group(1)
      rest = EN_DAY_RE.sub("", title).strip(" -–—|")
      rest = re.sub(r"^జ్ఞానోదయం\s*(on\s+)?", "", rest, flags=re.I).strip(" -–—")
      if rest:
        return f"జ్ఞానోదయం – {day}వ రోజు | {rest}"
      return f"జ్ఞానోదయం – {day}వ రోజు"
  return title


def day_from_title(title: str) -> int | None:
  m = DAY_RE.search(title)
  if m:
    return int(m.group(1))
  m = EN_DAY_RE.search(title)
  return int(m.group(1)) if m else None


def day_from_filename(path: Path) -> int | None:
  m = FILE_DAY_RE.search(path.name)
  return int(m.group(1)) if m else None


def parse_readmore_md(path: Path) -> dict:
  md = strip_md(path.read_text(encoding="utf-8"))
  title_m = re.search(r"^#\s+(.+)$", md, flags=re.M)
  if not title_m:
    raise ValueError(f"{path.name}: missing H1 title")
  title = normalize_title(title_m.group(1))

  speaker = (
    meta_value(md, "ప్రసంగకర్త")
    or meta_value(md, "ప్రత్యేక బోధన")
    or meta_value(md, "Speaker")
  )
  video = (
    meta_value(md, "మూల వీడియో")
    or meta_value(md, "వీడియో")
    or meta_value(md, "Original Video")
  )
  series = meta_value(md, "శ్రేణి")
  topic_meta = meta_value(md, "అంశం")
  day_meta = meta_value(md, "Day / Session") or meta_value(md, "Day")

  blurb = section_after(md, r"^##\s*Newsletter\s*కోసం\s*పరిచయం\s*$")
  if not blurb:
    blurb = section_after(md, r"^##\s*Newsletter.*$")
  # drop horizontal rules left in intro
  blurb = re.sub(r"^---+\s*", "", blurb).strip()
  blurb = re.sub(r"\s*---+\s*$", "", blurb).strip()
  # drop auto-caption editorial disclaimer from short blurb
  blurb = re.sub(
    r"\s*ఇది మూల ఆటోమేటిక్ క్యాప్షన్ల ఆధారంగా రూపొందించిన సంక్షిప్త సంపాదకీయ ముసాయిదా;?\s*"
    r"పూర్తి వీడియోతో తుది నిర్ధారణ ఇంకా అవసరం\.?\s*",
    " ",
    blurb,
  ).strip()

  read_more = ""
  rm = re.search(
    r"^##\s*Read More[^\n]*\n+(.*)\Z",
    md,
    flags=re.I | re.M | re.S,
  )
  if rm:
    read_more = rm.group(1).strip()
  # drop trailing editorial / watch-link footers
  read_more = re.sub(
    r"\n+---+\s*\n+\*\*పూర్తి బోధన.*$",
    "",
    read_more,
    flags=re.S,
  ).strip()
  read_more = re.sub(
    r"\n+---+\s*\n+\*సంపాదకీయ.*\*\s*$",
    "",
    read_more,
    flags=re.S,
  ).strip()
  read_more = re.sub(r"\n+\*సంపాదకీయ.*\*\s*$", "", read_more, flags=re.S).strip()

  topic = topic_meta
  if not topic and "|" in title:
    topic = title.split("|", 1)[1].strip()

  header_lines = []
  if speaker:
    header_lines.append(f"**ప్రసంగకర్త:** {speaker}  ")
  if topic:
    header_lines.append(f"**అంశం:** {topic}  ")
  elif series:
    header_lines.append(f"**శ్రేణి:** {series}  ")
  if video:
    header_lines.append(f"**మూల వీడియో:** {video}")

  full_story = "\n".join(header_lines).rstrip()
  if read_more:
    full_story = (full_story + "\n\n" + read_more).strip() if full_story else read_more

  day = day_from_title(title) or day_from_filename(path)
  if day is None and day_meta:
    m = re.search(r"(\d+)", day_meta)
    if m:
      day = int(m.group(1))
  if not blurb:
    raise ValueError(f"{path.name}: missing Newsletter పరిచయం section")
  if not full_story:
    raise ValueError(f"{path.name}: missing Read More body")

  return {
    "day": day,
    "file": path.name,
    "titleTe": title,
    "blurbTe": blurb,
    "fullStoryTe": full_story,
    "storyUrl": None,  # keep full story in-site; video is in the story body header
    "video": video or None,
  }


def existing_days(theme_items: list) -> set[int]:
  found: set[int] = set()
  for item in theme_items:
    title = item.get("titleTe") or item.get("titleEn") or ""
    d = day_from_title(title)
    if d is not None:
      found.add(d)
  return found


def find_themes_section(
  sections: list,
  heading_needle: str,
  *,
  create_section: bool = False,
  set_heading: str | None = None,
) -> tuple[int, dict, bool]:
  """Return (index, section, created)."""
  themes = [(i, s) for i, s in enumerate(sections) if s.get("key") == "themes"]
  needle = (heading_needle or "").strip()
  if needle:
    for i, s in themes:
      heading = f"{s.get('headingTe') or ''} {s.get('headingEn') or ''}"
      if needle in heading:
        return i, s, False
    if create_section:
      heading = (set_heading or needle).strip()
      new_sec = {
        "key": "themes",
        "headingTe": heading,
        "headingEn": heading,
        "asCard": True,
        "themeItems": [],
      }
      sections.append(new_sec)
      return len(sections) - 1, new_sec, True
    raise SystemExit(
      f"No themes section heading contains {needle!r}. "
      f"Found: {[s.get('headingTe') for _, s in themes]!r}. "
      f"Pass --create-section to add one."
    )
  if not themes:
    if create_section:
      heading = (set_heading or "Themes").strip()
      new_sec = {
        "key": "themes",
        "headingTe": heading,
        "headingEn": heading,
        "asCard": True,
        "themeItems": [],
      }
      sections.append(new_sec)
      return len(sections) - 1, new_sec, True
    raise SystemExit("Issue has no themes section")
  if len(themes) > 1:
    raise SystemExit("Multiple themes sections — pass --heading-needle")
  return themes[0][0], themes[0][1], False


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument(
    "--folder",
    default=DEFAULT_FOLDER,
    help="Folder of *.md files, or a single .md path",
  )
  ap.add_argument("--month", default="2026-11", help="Issue month YYYY-MM")
  ap.add_argument(
    "--heading-needle",
    default=DEFAULT_HEADING_NEEDLE,
    help="Match themes section heading (substring)",
  )
  ap.add_argument(
    "--set-heading",
    default="",
    help="Set/create themes headingTe (e.g. series title)",
  )
  ap.add_argument(
    "--create-section",
    action="store_true",
    help="Create a new themes section when heading-needle is not found",
  )
  ap.add_argument("--base-url", default=os.environ.get("PAYLOAD_URL", "http://localhost:3000"))
  ap.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL", "admin@qlu.local"))
  ap.add_argument(
    "--password",
    default=os.environ.get("SEED_ADMIN_PASSWORD", "qlu-admin-change-me"),
  )
  ap.add_argument("--dry-run", action="store_true", help="Parse + plan only; no PATCH")
  ap.add_argument("--replace-existing", action="store_true", help="Replace same day numbers instead of skipping")
  args = ap.parse_args()

  source = Path(args.folder)
  if source.is_file() and source.suffix.lower() == ".md":
    files = [source]
  elif source.is_dir():
    # Prefer article files; skip manifests / editorial notes
    files = sorted(source.glob("jnanodayam*.md")) or sorted(
      p for p in source.glob("*.md") if p.name.upper() not in {"MANIFEST.MD", "EDITORIAL_QA.MD"}
    )
  else:
    raise SystemExit(f"Not a folder or .md file: {source}")

  if not files:
    raise SystemExit(f"No .md files in {source}")

  parsed = []
  for path in files:
    try:
      parsed.append(parse_readmore_md(path))
    except ValueError as e:
      raise SystemExit(str(e)) from e

  base = args.base_url.rstrip("/")
  print(f"Logging in to {base} as {args.email} …")
  token = login(base, args.email, args.password)

  issue = find_issue(base, args.month, token)
  issue_id = issue["id"]
  sections = list(issue.get("sections") or [])
  idx, themes, created = find_themes_section(
    sections,
    args.heading_needle,
    create_section=args.create_section,
    set_heading=args.set_heading or None,
  )
  if args.set_heading.strip():
    themes = {**themes, "headingTe": args.set_heading.strip(), "asCard": True}
  items = list(themes.get("themeItems") or [])
  have = existing_days(items)

  print(f"Issue id={issue_id} month={args.month}")
  print(f"Themes heading: {themes.get('headingTe')}{' (new section)' if created else ''}")
  print(f"Existing theme items: {len(items)} (days {sorted(have) or '—'})")

  to_add: list[dict] = []
  skipped: list[str] = []
  replaced = 0
  for row in parsed:
    day = row["day"]
    label = f"day {day} · {row['file']}"
    # Put speaker + video into full story header (parser already did); keep storyUrl empty
    payload_item = {
      "titleTe": row["titleTe"],
      "blurbTe": row["blurbTe"],
      "fullStoryTe": row["fullStoryTe"],
      "storyUrl": None,
    }
    if day is not None and day in have:
      if args.replace_existing:
        for i, it in enumerate(items):
          if day_from_title(it.get("titleTe") or "") == day:
            if it.get("id"):
              payload_item = {**payload_item, "id": it["id"]}
            items[i] = payload_item
            replaced += 1
            break
        have.discard(day)
        print(
          f"  ~ replace {label}\n"
          f"      title: {row['titleTe'][:72]}{'…' if len(row['titleTe']) > 72 else ''}\n"
          f"      blurb: {len(row['blurbTe'])} chars · fullStory: {len(row['fullStoryTe'])} chars"
        )
        continue
      skipped.append(f"{label} (already present)")
      continue
    to_add.append(payload_item)
    print(
      f"  + {label}\n"
      f"      title: {row['titleTe'][:72]}{'…' if len(row['titleTe']) > 72 else ''}\n"
      f"      blurb: {len(row['blurbTe'])} chars · fullStory: {len(row['fullStoryTe'])} chars"
    )

  for s in skipped:
    print(f"  skip {s}")

  if not to_add and not replaced and not created and not args.set_heading.strip():
    print("Nothing to import.")
    return 0

  new_items = items + to_add
  themes = {**themes, "themeItems": new_items}
  themes.pop("themeItemsNav", None)
  sections[idx] = themes

  if args.dry_run:
    print(
      f"Dry run — would add {len(to_add)}, replace {replaced}"
      f"{', create section' if created else ''}; "
      f"total themeItems → {len(new_items)}"
    )
    return 0

  print(f"PATCHing issue {issue_id} …")
  updated = http_json(
    "PATCH",
    f"{base}/api/issues/{issue_id}",
    token=token,
    body={"sections": sections},
  )
  doc = updated.get("doc") or updated
  themes_after = None
  needle = (args.heading_needle or args.set_heading or "").strip()
  for s in doc.get("sections") or []:
    if s.get("key") != "themes":
      continue
    if not needle or needle in (s.get("headingTe") or "") or needle in (s.get("headingEn") or ""):
      themes_after = s
      break
  count = len((themes_after or {}).get("themeItems") or [])
  print(f"Done. Themes now has {count} theme item(s). Heading: {(themes_after or {}).get('headingTe')}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
