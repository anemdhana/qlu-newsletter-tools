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
TE_ORDINAL_DAY = {
  "మొదటి": 1,
  "రెండవ": 2,
  "రెండో": 2,
  "మూడవ": 3,
  "మూడో": 3,
  "నాల్గవ": 4,
  "నాలుగవ": 4,
  "ఐదవ": 5,
  "ఆరవ": 6,
  "ఏడవ": 7,
  "ఎనిమిదవ": 8,
  "తొమ్మిదవ": 9,
}
TE_ORDINAL_DAY_RE = re.compile(
  r"(" + "|".join(TE_ORDINAL_DAY.keys()) + r")\s*రోజు"
)
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


def strip_editorial_notes(text: str) -> str:
  """Drop source/editorial scope blocks from newsletter body (not for readers)."""
  out = text or ""
  # ### మూలాధార–సంపాదకీయ పరిధి (+ following paras until next heading)
  out = re.sub(
    r"\n+#{2,3}\s*మూలాధార\s*[–—\-]\s*సంపాదకీయ పరిధి\s*\n+"
    r".*?(?=\n#{1,3}\s|\Z)",
    "\n",
    out,
    flags=re.S,
  )
  # Standalone bold source notes (TE)
  out = re.sub(
    r"\n+\*\*మూలాధార(?:\s*[–—\-]\s*సంపాదకీయ)?\s*గమనిక:\*\*[^\n]*(?:\n(?!\n|#|\*\*)[^\n]*)*",
    "",
    out,
  )
  out = re.sub(
    r"\n+\*\*మూలాధార గమనిక:\*\*[^\n]*(?:\n(?!\n|#|\*\*)[^\n]*)*",
    "",
    out,
  )
  # EN source / editorial notes
  out = re.sub(
    r"\n+\*\*Source and editorial note:\*\*[^\n]*(?:\n(?!\n|#|\*\*)[^\n]*)*",
    "",
    out,
    flags=re.I,
  )
  out = re.sub(
    r"\n+\*\*Editorial note:\*\*[^\n]*(?:\n(?!\n|#|\*\*)[^\n]*)*",
    "",
    out,
    flags=re.I,
  )
  # Opening editorial status callouts (Part 1 incomplete, etc.)
  out = re.sub(
    r"(?m)^>\s*\*\*సంపాదకీయ స్థితి:\*\*.*(?:\n>.*)*\n*",
    "",
    out,
  )
  out = re.sub(
    r"(?m)^>\s*\*\*Editorial status:\*\*.*(?:\n>.*)*\n*",
    "",
    out,
  )
  # Safety notice blocks (TE/EN) — not for newsletter readers
  out = re.sub(
    r"\n+#{2,3}\s*(?:ముఖ్యమైన\s+)?భద్రతా?\s*గమనిక\s*\n+"
    r".*?(?=\n#{1,3}\s|\Z)",
    "\n",
    out,
    flags=re.S,
  )
  out = re.sub(
    r"\n+\*\*(?:ముఖ్యమైన\s+)?భద్రతా?\s*గమనిక:\*\*[^\n]*(?:\n(?!\n|#|\*\*)[^\n]*)*",
    "",
    out,
  )
  out = re.sub(
    r"(?m)^>\s*\*\*(?:ముఖ్యమైన\s+)?భద్రతా?\s*గమనిక:\*\*.*(?:\n>.*)*\n*",
    "",
    out,
  )
  out = re.sub(
    r"\n+#{2,3}\s*(?:Safety|Practice)\s+not(?:e|ice)\s*\n+"
    r".*?(?=\n#{1,3}\s|\Z)",
    "\n",
    out,
    flags=re.S | re.I,
  )
  out = re.sub(
    r"\n+\*\*(?:Safety|Practice)\s+not(?:e|ice):\*\*[^\n]*(?:\n(?!\n|#|\*\*)[^\n]*)*",
    "",
    out,
    flags=re.I,
  )
  out = re.sub(
    r"\n+\*(?:Safety|Practice)\s+not(?:e|ice):\*[^\n]*(?:\n(?!\n|#|\*)[^\n]*)*",
    "",
    out,
    flags=re.I,
  )
  out = re.sub(
    r"(?m)^>\s*\*\*(?:Safety|Practice)\s+not(?:e|ice):\*\*.*(?:\n>.*)*\n*",
    "",
    out,
    flags=re.I,
  )
  return out.strip()


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
  if m:
    return int(m.group(1))
  m = TE_ORDINAL_DAY_RE.search(title)
  if m:
    return TE_ORDINAL_DAY.get(m.group(1))
  return None


def day_from_filename(path: Path) -> int | None:
  m = FILE_DAY_RE.search(path.name)
  return int(m.group(1)) if m else None


def _meta_speaker(md: str) -> str:
  return (
    meta_value(md, "ప్రసంగకర్త")
    or meta_value(md, "ప్రత్యేక బోధన")
    or meta_value(md, "ప్రవచనం")
    or meta_value(md, "Speaker")
    or meta_value(md, "Discourse")
  )


def _meta_video(md: str) -> str:
  video = (
    meta_value(md, "మూల వీడియో")
    or meta_value(md, "వీడియో")
    or meta_value(md, "Original Video")
  )
  if video:
    return video
  m = re.search(
    r"\[(?:మూల వీడియో|Original video)\]\((https?://[^)]+)\)",
    md,
    flags=re.I,
  )
  if m:
    return m.group(1).strip()
  m = re.search(r"https?://(?:www\.)?youtube\.com/watch\?v=[\w\-]+", md)
  return m.group(0) if m else ""


def _jnanodayam_day_from_text(text: str) -> int | None:
  m = re.search(r"జ్ఞానోదయం\s*[—–\-]\s*(\d+)\s*వ", text)
  if m:
    return int(m.group(1))
  m = re.search(r"Jnanodayam\s*[—–\-]\s*Day\s+(\d+)\b", text, flags=re.I)
  if m:
    return int(m.group(1))
  return None


def _jnanodayam_subtitle(md: str) -> str:
  """Prefer a bold metadata line that mentions Jnanodayam day."""
  for m in re.finditer(r"\*\*\s*(.+?)\s*\*\*", md):
    line = m.group(1).strip()
    if "జ్ఞానోదయం" in line or re.search(r"Jnanodayam", line, flags=re.I):
      # Normalize “… | జ్ఞానోదయం — 561వ రోజు” → CMS title style
      day = _jnanodayam_day_from_text(line)
      if day is not None:
        topic = ""
        if "|" in line:
          left, right = [p.strip() for p in line.split("|", 1)]
          if "జ్ఞానోదయం" in left or re.search(r"Jnanodayam", left, flags=re.I):
            topic = right
          else:
            topic = left
          # Keep "దేవీ నవరాత్రులు — …" topics; only trim "· మొదటి రోజు" style crumbs.
          topic = re.sub(r"^దేవీ నవరాత్రులు\s*[·•]\s*", "", topic).strip()
          topic = re.sub(r"^Devi Navratri\s*[·•]\s*", "", topic, flags=re.I).strip()
        if topic and not re.fullmatch(
          r"(మొదటి|రెండవ|మూడవ|నాల్గవ|నాలుగవ|ఐదవ|ఆరవ|ఏడవ|ఎనిమిదవ|తొమ్మిదవ)\s*రోజు",
          topic,
        ):
          return f"జ్ఞానోదయం – {day}వ రోజు | {topic}"
        return ""  # let caller fall back to H1 + day
      return normalize_title(line)
  return ""


def _build_story_header(
  *,
  speaker: str,
  topic: str,
  series: str,
  video: str,
  lang: str = "te",
) -> str:
  header_lines = []
  if lang == "en":
    if speaker:
      header_lines.append(f"**Speaker:** {speaker}  ")
    if topic:
      header_lines.append(f"**Topic:** {topic}  ")
    elif series:
      header_lines.append(f"**Series:** {series}  ")
    if video:
      header_lines.append(f"**Original Video:** {video}")
  else:
    if speaker:
      header_lines.append(f"**ప్రసంగకర్త:** {speaker}  ")
    if topic:
      header_lines.append(f"**అంశం:** {topic}  ")
    elif series:
      header_lines.append(f"**శ్రేణి:** {series}  ")
    if video:
      header_lines.append(f"**మూల వీడియో:** {video}")
  return "\n".join(header_lines).rstrip()


def parse_newsletter_readmore_md(path: Path, md: str) -> dict | None:
  """Legacy newsletter format: Newsletter పరిచయం + Read More."""
  blurb = section_after(md, r"^##\s*Newsletter\s*కోసం\s*పరిచయం\s*$")
  if not blurb:
    blurb = section_after(md, r"^##\s*Newsletter.*$")
  if not blurb:
    return None

  title_m = re.search(r"^#\s+(.+)$", md, flags=re.M)
  if not title_m:
    raise ValueError(f"{path.name}: missing H1 title")
  title = normalize_title(title_m.group(1))
  speaker = _meta_speaker(md)
  video = _meta_video(md)
  series = meta_value(md, "శ్రేణి")
  topic_meta = meta_value(md, "అంశం")
  day_meta = meta_value(md, "Day / Session") or meta_value(md, "Day")

  blurb = re.sub(r"^---+\s*", "", blurb).strip()
  blurb = re.sub(r"\s*---+\s*$", "", blurb).strip()
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

  full_story = _build_story_header(speaker=speaker, topic=topic, series=series, video=video)
  if read_more:
    full_story = (full_story + "\n\n" + read_more).strip() if full_story else read_more

  day = day_from_title(title) or day_from_filename(path)
  if day is None and day_meta:
    m = re.search(r"(\d+)", day_meta)
    if m:
      day = int(m.group(1))
  if not full_story:
    raise ValueError(f"{path.name}: missing Read More body")

  return {
    "day": day,
    "file": path.name,
    "lang": "te",
    "titleTe": title,
    "blurbTe": strip_editorial_notes(blurb),
    "fullStoryTe": strip_editorial_notes(full_story),
    "storyUrl": None,
    "video": video or None,
  }


def detect_theme_lang(path: Path, md: str) -> str:
  if is_english_theme_file(path):
    return "en"
  if is_telugu_theme_file(path):
    return "te"
  head = md[:2500]
  if re.search(r"[\u0C00-\u0C7F]", head):
    return "te"
  return "en"


def parse_lecture_edition_md(path: Path, md: str) -> dict:
  """Lecture edition (master publication prompt): intro + numbered sections (TE or EN)."""
  title_m = re.search(r"^#\s+(.+)$", md, flags=re.M)
  if not title_m:
    raise ValueError(f"{path.name}: missing H1 title")
  h1 = title_m.group(1).strip()
  lang = detect_theme_lang(path, md)
  day_hint = _jnanodayam_day_from_text(md)

  # Card title: day prefix from metadata + H1 page title
  if day_hint is not None:
    if lang == "en":
      title = f"Jnanodayam — Day {day_hint} | {h1}"
    else:
      title = f"జ్ఞానోదయం – {day_hint}వ రోజు | {h1}"
  else:
    subtitle = _jnanodayam_subtitle(md)
    title = subtitle or normalize_title(h1)

  speaker = _meta_speaker(md)
  video = _meta_video(md)
  series = meta_value(md, "శ్రేణి") or meta_value(md, "Series")

  blurb = section_after(md, r"^##\s*పరిచయం\s*$")
  if not blurb:
    blurb = section_after(md, r"^##\s*ఈ రోజు ఆధ్యాత్మిక ప్రయాణం\s*$")
  if not blurb:
    blurb = section_after(md, r"^##\s*Introduction\s*$")
  if not blurb:
    blurb = section_after(md, r"^##\s*Today'?s Spiritual Journey\s*$")

  # Intro-like ## only (not closing "## ఈ రోజు జ్ఞానం" / "## Bringing…")
  intro_heading_re = (
    r"^##\s*(?:0?1\.|పరిచయం|ఈ రోజు ఆధ్యాత్మిక|"
    r"Introduction|Today'?s Spiritual Journey)\s*$"
  )
  body = ""
  body_m = re.search(intro_heading_re, md, flags=re.I | re.M)
  if body_m:
    after_intro = md[body_m.end() :]
    nxt = re.search(r"^##\s+", after_intro, flags=re.M)
    body = after_intro[nxt.start() :].strip() if nxt else after_intro.strip()
  else:
    first_sec = re.search(r"^##\s+.+$", md, flags=re.M)
    body = md[first_sec.start() :].strip() if first_sec else ""

  if not blurb:
    # Day-04 style: H1 + ## topic + lead paragraph before ### sections
    lead_m = re.search(
      r"^#\s+.+\n+(?:##\s+.+\n+)?(.+?)(?=\n###\s|\n##\s|\Z)",
      md,
      flags=re.S,
    )
    if lead_m:
      paras = [p.strip() for p in re.split(r"\n\s*\n", lead_m.group(1)) if p.strip()]
      if paras and not paras[0].startswith("#") and not paras[0].startswith("**"):
        blurb = paras[0]
  if not blurb and body:
    first = section_after(md, r"^##\s+.+$")
    if first:
      paras = [p.strip() for p in re.split(r"\n\s*\n", first) if p.strip()]
      blurb = paras[0] if paras else first[:400]
      if not body.startswith("##"):
        body = md[md.find("##") :].strip()

  topic = ""
  if "|" in title:
    topic = title.split("|", 1)[1].strip()
  elif h1 and h1 not in title:
    topic = h1

  header = _build_story_header(
    speaker=speaker,
    topic=topic,
    series=series,
    video=video,
    lang=lang,
  )
  full_story = (header + "\n\n" + body).strip() if header else body.strip()
  if not full_story:
    rest = re.sub(r"^#\s+.+\n+(?:\*\*.+\*\*\s*\n+)*", "", md, count=1).strip()
    full_story = (header + "\n\n" + rest).strip() if header else rest

  day = (
    day_from_title(title)
    or _jnanodayam_day_from_text(md)
    or day_from_title(h1)
    or day_from_filename(path)
  )

  blurb = strip_editorial_notes(blurb.strip())
  full_story = strip_editorial_notes(full_story)

  if not blurb:
    raise ValueError(f"{path.name}: missing intro/పరిచయం for blurb")
  if not full_story:
    raise ValueError(f"{path.name}: missing lecture body")

  if lang == "en":
    return {
      "day": day,
      "file": path.name,
      "lang": "en",
      "titleEn": title,
      "blurbEn": blurb,
      "fullStoryEn": full_story,
      "storyUrl": None,
      "video": video or None,
    }
  return {
    "day": day,
    "file": path.name,
    "lang": "te",
    "titleTe": title,
    "blurbTe": blurb,
    "fullStoryTe": full_story,
    "storyUrl": None,
    "video": video or None,
  }


def parse_readmore_md(path: Path) -> dict:
  """Parse theme Markdown (legacy newsletter Read More or lecture edition)."""
  md = strip_md(path.read_text(encoding="utf-8"))
  legacy = parse_newsletter_readmore_md(path, md)
  if legacy is not None:
    return legacy
  return parse_lecture_edition_md(path, md)


def is_english_theme_file(path: Path) -> bool:
  name = path.name.lower()
  if "english" in name:
    return True
  if re.search(r"(^|[_\-])en([_\-.]|$)", name):
    return True
  return False


def is_telugu_theme_file(path: Path) -> bool:
  if is_english_theme_file(path):
    return False
  name = path.name.lower()
  if re.search(r"(^|[_\-])te([_\-.]|$)", name) or "telugu" in name:
    return True
  try:
    head = path.read_text(encoding="utf-8")[:2500]
  except OSError:
    return False
  return bool(re.search(r"[\u0C00-\u0C7F]", head))


def theme_file_quality(path: Path) -> int:
  """Higher = prefer when multiple files share a day."""
  name = path.name.lower()
  score = 0
  if "complete" in name:
    score += 30
  if "reviewed" in name:
    score += 20
  if re.search(r"(^|[_\-])te([_\-.]|$)", name):
    score += 10
  if "part" in name:
    score -= 15
  score += min(path.stat().st_size // 1000, 40)
  return score


def _pick_best_per_day(candidates: list[Path]) -> list[Path]:
  by_day: dict[int | None, list[Path]] = {}
  for path in candidates:
    try:
      head = path.read_text(encoding="utf-8")[:2000]
      day = _jnanodayam_day_from_text(head) or day_from_title(head) or day_from_filename(path)
    except OSError:
      day = day_from_filename(path)
    by_day.setdefault(day, []).append(path)

  chosen: list[tuple[int | None, Path]] = []
  for day, paths in by_day.items():
    best = max(paths, key=theme_file_quality)
    chosen.append((day, best))
  return [p for _, p in sorted(chosen, key=lambda t: (t[0] is None, t[0] or 0, t[1].name.lower()))]


def select_theme_md_files(folder: Path) -> list[Path]:
  """Pick best Telugu theme article per day (skip English / manifests)."""
  skip_names = {"manifest.md", "editorial_qa.md", "batch-manifest.md"}
  candidates = [
    p
    for p in folder.glob("*.md")
    if p.name.lower() not in skip_names and is_telugu_theme_file(p)
  ]
  if not candidates:
    candidates = [
      p
      for p in folder.glob("*.md")
      if p.name.lower() not in skip_names and not is_english_theme_file(p)
    ]
  return _pick_best_per_day(candidates)


def select_english_theme_md_files(folder: Path) -> list[Path]:
  """Pick best English theme article per day."""
  skip_names = {"manifest.md", "editorial_qa.md", "batch-manifest.md"}
  candidates = [
    p
    for p in folder.glob("*.md")
    if p.name.lower() not in skip_names and is_english_theme_file(p)
  ]
  return _pick_best_per_day(candidates)


def merge_theme_rows(te_rows: list[dict], en_rows: list[dict]) -> list[dict]:
  """Merge TE + EN parses by Jnanodayam day number."""
  by_day: dict[int | None, dict] = {}
  for row in te_rows:
    day = row.get("day")
    by_day[day] = {
      "day": day,
      "file": row.get("file"),
      "titleTe": row.get("titleTe"),
      "blurbTe": row.get("blurbTe"),
      "fullStoryTe": row.get("fullStoryTe"),
      "storyUrl": None,
      "video": row.get("video"),
    }
  for row in en_rows:
    day = row.get("day")
    cur = by_day.get(day)
    if cur is None:
      # EN-only day: still import with EN fields (TE left empty)
      by_day[day] = {
        "day": day,
        "file": row.get("file"),
        "titleEn": row.get("titleEn"),
        "blurbEn": row.get("blurbEn"),
        "fullStoryEn": row.get("fullStoryEn"),
        "storyUrl": None,
        "video": row.get("video"),
      }
      continue
    cur["titleEn"] = row.get("titleEn")
    cur["blurbEn"] = row.get("blurbEn")
    cur["fullStoryEn"] = row.get("fullStoryEn")
    if not cur.get("video") and row.get("video"):
      cur["video"] = row.get("video")
    cur["fileEn"] = row.get("file")
  return [by_day[k] for k in sorted(by_day.keys(), key=lambda d: (d is None, d or 0))]


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
  te_files: list[Path] = []
  en_files: list[Path] = []
  if source.is_file() and source.suffix.lower() == ".md":
    if is_english_theme_file(source):
      en_files = [source]
    else:
      te_files = [source]
  elif source.is_dir():
    preferred = sorted(source.glob("jnanodayam*.md"))
    te_files = preferred or select_theme_md_files(source)
    en_files = [] if preferred else select_english_theme_md_files(source)
  else:
    raise SystemExit(f"Not a folder or .md file: {source}")

  return import_theme_files(
    te_files,
    en_files=en_files,
    month=args.month,
    heading_needle=args.heading_needle,
    set_heading=args.set_heading,
    create_section=args.create_section,
    base_url=args.base_url,
    email=args.email,
    password=args.password,
    dry_run=args.dry_run,
    replace_existing=args.replace_existing,
  )


def _payload_from_row(row: dict, *, existing: dict | None = None) -> dict:
  base = dict(existing or {})
  if existing and existing.get("id"):
    base["id"] = existing["id"]
  for key in (
    "titleTe",
    "blurbTe",
    "fullStoryTe",
    "titleEn",
    "blurbEn",
    "fullStoryEn",
  ):
    if row.get(key):
      base[key] = row[key]
  base["storyUrl"] = None
  return base


def _row_label(row: dict) -> str:
  parts = [f"day {row.get('day')}"]
  if row.get("file"):
    parts.append(str(row["file"]))
  if row.get("fileEn"):
    parts.append(f"+ {row['fileEn']}")
  return " · ".join(parts)


def import_theme_files(
  files: list[Path],
  *,
  en_files: list[Path] | None = None,
  month: str,
  heading_needle: str,
  set_heading: str = "",
  create_section: bool = False,
  base_url: str = "http://localhost:3000",
  email: str = "admin@qlu.local",
  password: str = "qlu-admin-change-me",
  dry_run: bool = False,
  replace_existing: bool = False,
) -> int:
  te_files = list(files or [])
  en_list = list(en_files or [])
  if not te_files and not en_list:
    raise SystemExit("No .md files to import")

  te_rows: list[dict] = []
  en_rows: list[dict] = []
  for path in te_files:
    try:
      te_rows.append(parse_readmore_md(path))
    except ValueError as e:
      raise SystemExit(str(e)) from e
  for path in en_list:
    try:
      en_rows.append(parse_readmore_md(path))
    except ValueError as e:
      raise SystemExit(str(e)) from e

  parsed = merge_theme_rows(te_rows, en_rows)

  base = base_url.rstrip("/")
  print(f"Logging in to {base} as {email} …")
  token = login(base, email, password)

  issue = find_issue(base, month, token)
  issue_id = issue["id"]
  sections = list(issue.get("sections") or [])
  idx, themes, created = find_themes_section(
    sections,
    heading_needle,
    create_section=create_section,
    set_heading=set_heading or None,
  )
  if set_heading.strip():
    themes = {
      **themes,
      "headingTe": set_heading.strip(),
      "headingEn": themes.get("headingEn") or set_heading.strip(),
      "asCard": True,
    }
  items = list(themes.get("themeItems") or [])
  have = existing_days(items)

  print(f"Issue id={issue_id} month={month}")
  print(f"Themes heading: {themes.get('headingTe')}{' (new section)' if created else ''}")
  print(f"Existing theme items: {len(items)} (days {sorted(have) or '—'})")
  print(f"Parsed TE days: {sorted(r['day'] for r in te_rows if r.get('day') is not None) or '—'}")
  print(f"Parsed EN days: {sorted(r['day'] for r in en_rows if r.get('day') is not None) or '—'}")

  to_add: list[dict] = []
  skipped: list[str] = []
  replaced = 0
  for row in parsed:
    day = row["day"]
    label = _row_label(row)
    title_preview = (row.get("titleTe") or row.get("titleEn") or "")[:72]
    te_chars = len(row.get("fullStoryTe") or "")
    en_chars = len(row.get("fullStoryEn") or "")
    if day is not None and day in have:
      match_i = None
      for i, it in enumerate(items):
        title = it.get("titleTe") or it.get("titleEn") or ""
        if day_from_title(title) == day:
          match_i = i
          break
      if match_i is None:
        skipped.append(f"{label} (day present but unmatched item)")
        continue
      existing = items[match_i]
      if replace_existing:
        payload_item = _payload_from_row(row, existing=existing)
        items[match_i] = payload_item
        replaced += 1
        print(
          f"  ~ replace {label}\n"
          f"      title: {title_preview}{'…' if len(title_preview) > 72 else ''}\n"
          f"      TE story: {te_chars} · EN story: {en_chars}"
        )
        continue
      # Fill missing EN without wiping TE
      if row.get("fullStoryEn") and not (existing.get("fullStoryEn") or "").strip():
        payload_item = {
          **existing,
          "titleEn": row.get("titleEn") or existing.get("titleEn"),
          "blurbEn": row.get("blurbEn") or existing.get("blurbEn"),
          "fullStoryEn": row.get("fullStoryEn"),
        }
        items[match_i] = payload_item
        replaced += 1
        print(f"  ~ fill EN {label} · EN story: {en_chars}")
        continue
      skipped.append(f"{label} (already present)")
      continue

    payload_item = _payload_from_row(row)
    if not (payload_item.get("titleTe") or payload_item.get("titleEn")):
      skipped.append(f"{label} (no title)")
      continue
    to_add.append(payload_item)
    if day is not None:
      have.add(day)
    print(
      f"  + {label}\n"
      f"      title: {title_preview}{'…' if len(title_preview) > 72 else ''}\n"
      f"      TE story: {te_chars} · EN story: {en_chars}"
    )

  for s in skipped:
    print(f"  skip {s}")

  if not to_add and not replaced and not created and not set_heading.strip():
    print("Nothing to import.")
    return 0

  new_items = items + to_add
  themes = {**themes, "themeItems": new_items}
  themes.pop("themeItemsNav", None)
  sections[idx] = themes

  if dry_run:
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
  needles = [n for n in ((set_heading or "").strip(), (heading_needle or "").strip()) if n]
  for s in doc.get("sections") or []:
    if s.get("key") != "themes":
      continue
    heading = f"{s.get('headingTe') or ''} {s.get('headingEn') or ''}"
    if not needles or any(n in heading for n in needles):
      themes_after = s
      break
  # Fallback: last themes section (new series often appended)
  if themes_after is None:
    for s in reversed(doc.get("sections") or []):
      if s.get("key") == "themes":
        themes_after = s
        break
  count = len((themes_after or {}).get("themeItems") or [])
  print(f"Done. Themes now has {count} theme item(s). Heading: {(themes_after or {}).get('headingTe')}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
