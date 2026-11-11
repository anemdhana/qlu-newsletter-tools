#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export Issue section(s) from Payload CMS to static HTML under docs/
for GitHub Pages (branch → /docs).

Example (from repo root):

  python scripts/export_section_pages.py --month 2026-11 --section themes
  python scripts/export_section_pages.py --month 2026-11 --section all
  python scripts/export_print_snapshot.py --month 2026-11

--section all exports every magazine section. For a pixel-matched Astro Print
page (qlu.css + images + stories), use export_print_snapshot.py (Astro must
be running on --astro, default http://localhost:4321).

Auth (Payload admin):
  PAYLOAD_URL          default http://localhost:3000
  SEED_ADMIN_EMAIL     default admin@qlu.local
  SEED_ADMIN_PASSWORD  default qlu-admin-change-me

GitHub Pages project site base (CSS / catalog links):
  --base-url /qlu-newsletter-tools
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]

SECTION_KEYS = (
  "themes",
  "highlight-classes",
  "experiences",
  "visits",
  "vanya",
  "campus",
  "upcoming",
)

SECTION_CHOICES = (*SECTION_KEYS, "all")

SECTION_TITLES: dict[str, dict[str, str]] = {
  "themes": {
    "te": "ఈ నెల ఆధ్యాత్మిక జ్ఞానసారం",
    "en": "Monthly Wisdom & Key Teachings",
  },
  "highlight-classes": {
    "te": "ఈ నెల విశిష్ట తరగతులు – జ్ఞానాంశాలు",
    "en": "Featured Classes & Insights",
  },
  "experiences": {
    "te": "ఆత్మపరివర్తన అనుభవాలు",
    "en": "Voices of Transformation",
  },
  "visits": {
    "te": "డా. న్యూటన్ గారి ఆధ్యాత్మిక జ్ఞానప్రచారం",
    "en": "Dr. Newton’s Spiritual Outreach",
  },
  "vanya": {
    "te": "వన్య మైత్రేయ విశేషాలు",
    "en": "Vanya Maitreya Highlights",
  },
  "campus": {
    "te": "గోలోక, సహస్రార మరియు QLU విశేషాలు",
    "en": "Updates from Goloka, Sahasrara & QLU",
  },
  "upcoming": {
    "te": "రాబోయే ఆధ్యాత్మిక కార్యక్రమాలు – ప్రకటనలు",
    "en": "Upcoming Events & Announcements",
  },
}

LANGS = ("te", "en")


# ---------------------------------------------------------------------------
# HTTP / CMS
# ---------------------------------------------------------------------------


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
  except urllib.error.URLError as e:
    raise SystemExit(
      f"Cannot reach CMS at {url} ({e.reason}). Is Payload running?"
    ) from e


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
  url = (
    f"{base}/api/issues?limit=1&depth=1"
    f"&where[month][equals]={quote(month)}"
  )
  out = http_json("GET", url, token=token)
  docs = out.get("docs") or []
  if not docs:
    raise SystemExit(f"No issue found for month={month}")
  return docs[0]


# ---------------------------------------------------------------------------
# Markdown (stdlib subset)
# ---------------------------------------------------------------------------


def _inline_md(text: str) -> str:
  s = html.escape(text)
  s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
  s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
  s = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", s)
  s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
  s = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<em>\1</em>", s)
  s = re.sub(
    r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
    r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
    s,
  )
  return s


def md_to_html(raw: str | None) -> str:
  src = (raw or "").replace("\r\n", "\n").replace("\r", "\n").strip()
  if not src:
    return ""

  lines = src.split("\n")
  out: list[str] = []
  i = 0
  while i < len(lines):
    line = lines[i]
    if not line.strip():
      i += 1
      continue

    hm = re.match(r"^(#{1,6})\s+(.+)$", line)
    if hm:
      level = len(hm.group(1))
      out.append(f"<h{level}>{_inline_md(hm.group(2).strip())}</h{level}>")
      i += 1
      continue

    if re.match(r"^[-*+]\s+", line):
      items: list[str] = []
      while i < len(lines) and re.match(r"^[-*+]\s+", lines[i]):
        items.append(f"<li>{_inline_md(re.sub(r'^[-*+]\\s+', '', lines[i]))}</li>")
        i += 1
      out.append("<ul>" + "".join(items) + "</ul>")
      continue

    if re.match(r"^\d+\.\s+", line):
      items = []
      while i < len(lines) and re.match(r"^\d+\.\s+", lines[i]):
        items.append(f"<li>{_inline_md(re.sub(r'^\\d+\\.\\s+', '', lines[i]))}</li>")
        i += 1
      out.append("<ol>" + "".join(items) + "</ol>")
      continue

    if line.startswith(">"):
      quotes: list[str] = []
      while i < len(lines) and lines[i].startswith(">"):
        quotes.append(_inline_md(lines[i].lstrip("> ").rstrip()))
        i += 1
      out.append("<blockquote><p>" + "<br>\n".join(quotes) + "</p></blockquote>")
      continue

    para: list[str] = []
    while i < len(lines) and lines[i].strip() and not re.match(
      r"^(#{1,6}\s+|[-*+]\s+|\d+\.\s+|>)", lines[i]
    ):
      para.append(lines[i])
      i += 1
    out.append("<p>" + "<br>\n".join(_inline_md(p) for p in para) + "</p>")

  return "\n".join(out)


def pick_lang(lang: str, te: str | None, en: str | None) -> str:
  if lang == "te":
    return (te or en or "").strip()
  return (en or te or "").strip()


# ---------------------------------------------------------------------------
# Normalize section → items
# ---------------------------------------------------------------------------


@dataclass
class CardItem:
  slug: str
  title: str
  body: str = ""
  meta: str = ""
  full_story: str = ""
  story_url: str = ""


@dataclass
class SectionView:
  key: str
  heading: str
  lead: str = ""
  items: list[CardItem] = field(default_factory=list)


def find_section(issue: dict, key: str) -> dict:
  for s in issue.get("sections") or []:
    if s.get("key") == key:
      return s
  raise SystemExit(f"Issue has no section key={key!r}")


def section_or_stub(issue: dict, key: str) -> dict:
  for s in issue.get("sections") or []:
    if s.get("key") == key:
      return s
  # Match Astro print: ensure every contents section exists
  titles = SECTION_TITLES.get(key, {"te": key, "en": key})
  return {
    "key": key,
    "headingTe": titles["te"],
    "headingEn": titles["en"],
  }


def resolve_export_keys(issue: dict, section_arg: str) -> list[str]:
  if section_arg == "all":
    return list(SECTION_KEYS)
  find_section(issue, section_arg)  # validate present
  return [section_arg]


EMPTY_SECTION = {
  "te": "ఈ నెలలో ఈ విభాగానికి ప్రత్యేక అప్‌డేట్ లేదు.",
  "en": "No updates for this section this month.",
}


def normalize_section(section: dict, lang: str) -> SectionView:
  key = section.get("key") or ""
  titles = SECTION_TITLES.get(key, {"te": key, "en": key})
  heading = pick_lang(lang, section.get("headingTe"), section.get("headingEn")) or titles[lang]
  lead = pick_lang(lang, section.get("leadTe"), section.get("leadEn"))
  items: list[CardItem] = []

  if key == "themes":
    for i, row in enumerate(section.get("themeItems") or [], start=1):
      items.append(
        CardItem(
          slug=f"item-{i:02d}",
          title=pick_lang(lang, row.get("titleTe"), row.get("titleEn")),
          body=pick_lang(lang, row.get("blurbTe"), row.get("blurbEn")),
          full_story=pick_lang(lang, row.get("fullStoryTe"), row.get("fullStoryEn")),
          story_url=(row.get("storyUrl") or "").strip(),
        )
      )

  elif key == "highlight-classes":
    for i, row in enumerate(section.get("classItems") or [], start=1):
      meta = " · ".join(x for x in [row.get("speaker"), row.get("date")] if x)
      items.append(
        CardItem(
          slug=f"item-{i:02d}",
          title=pick_lang(lang, row.get("titleTe"), row.get("titleEn")),
          body=pick_lang(lang, row.get("insightTe"), row.get("insightEn")),
          meta=meta,
          full_story=pick_lang(lang, row.get("fullStoryTe"), row.get("fullStoryEn")),
          story_url=(row.get("storyUrl") or "").strip(),
        )
      )

  elif key == "experiences":
    for i, row in enumerate(section.get("stories") or [], start=1):
      title = " / ".join(x for x in [row.get("name"), row.get("location")] if x)
      items.append(
        CardItem(
          slug=f"item-{i:02d}",
          title=title or f"Story {i}",
          body=pick_lang(lang, row.get("bodyTe"), row.get("bodyEn")),
          full_story=pick_lang(lang, row.get("fullStoryTe"), row.get("fullStoryEn")),
          story_url=(row.get("storyUrl") or "").strip(),
        )
      )

  elif key == "visits":
    for i, row in enumerate(section.get("visitItems") or [], start=1):
      title = " / ".join(x for x in [row.get("date"), row.get("place")] if x)
      items.append(
        CardItem(
          slug=f"item-{i:02d}",
          title=title or f"Visit {i}",
          body=pick_lang(lang, row.get("noteTe"), row.get("noteEn")),
          full_story=pick_lang(lang, row.get("fullStoryTe"), row.get("fullStoryEn")),
          story_url=(row.get("storyUrl") or "").strip(),
        )
      )

  elif key == "vanya":
    for i, row in enumerate(section.get("featureItems") or [], start=1):
      items.append(
        CardItem(
          slug=f"item-{i:02d}",
          title=pick_lang(lang, row.get("titleTe"), row.get("titleEn")),
          body=pick_lang(lang, row.get("bodyTe"), row.get("bodyEn")),
          full_story=pick_lang(lang, row.get("fullStoryTe"), row.get("fullStoryEn")),
          story_url=(row.get("storyUrl") or "").strip(),
        )
      )

  elif key == "campus":
    campuses = (
      ("goloka", "Goloka", "గోలోక", "golokaUrl"),
      ("sahasrara", "Sahasrara", "సహస్రార", "sahasraraUrl"),
      ("qlu", "QLU", "QLU", "qluUrl"),
    )
    for prefix, title_en, title_te, url_field in campuses:
      title = title_te if lang == "te" else title_en
      body = pick_lang(lang, section.get(f"{prefix}Te"), section.get(f"{prefix}En"))
      full = pick_lang(
        lang,
        section.get(f"{prefix}FullStoryTe"),
        section.get(f"{prefix}FullStoryEn"),
      )
      url = (section.get(url_field) or "").strip()
      if not body and not full and not url:
        continue
      items.append(
        CardItem(
          slug=prefix,
          title=title,
          body=body,
          full_story=full,
          story_url=url,
        )
      )

  elif key == "upcoming":
    for i, row in enumerate(section.get("eventItems") or [], start=1):
      venue = pick_lang(lang, row.get("venueTe"), row.get("venueEn"))
      when = (row.get("when") or "").strip()
      meta = " · ".join(x for x in [when, venue] if x)
      items.append(
        CardItem(
          slug=f"item-{i:02d}",
          title=pick_lang(lang, row.get("titleTe"), row.get("titleEn")) or f"Event {i}",
          body=pick_lang(lang, row.get("detailsTe"), row.get("detailsEn")),
          meta=meta,
          full_story=pick_lang(lang, row.get("fullStoryTe"), row.get("fullStoryEn")),
          story_url=(row.get("storyUrl") or "").strip(),
        )
      )

  else:
    raise SystemExit(f"Unsupported section key={key!r}")

  # Drop completely empty cards
  items = [it for it in items if it.title or it.body or it.full_story or it.story_url]
  return SectionView(key=key, heading=heading, lead=lead, items=items)


def normalize_section_for_export(section: dict, lang: str, *, allow_empty: bool) -> SectionView:
  view = normalize_section(section, lang)
  if view.items or view.lead:
    return view
  if allow_empty:
    # Astro Print still shows the sheet with the empty-line copy
    return SectionView(
      key=view.key,
      heading=view.heading,
      lead="",
      items=[
        CardItem(
          slug="empty",
          title="",
          body=EMPTY_SECTION["te" if lang == "te" else "en"],
        )
      ],
    )
  return view


# ---------------------------------------------------------------------------
# HTML writers
# ---------------------------------------------------------------------------


def normalize_base_url(base_url: str) -> str:
  b = (base_url or "").strip().rstrip("/")
  if not b or b == "/":
    return ""
  if not b.startswith("/"):
    b = "/" + b
  return b


def page_shell(
  *,
  title: str,
  css_href: str,
  body: str,
  lang: str = "en",
) -> str:
  return f"""<!DOCTYPE html>
<html lang="{html.escape(lang)}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="{html.escape(css_href)}">
</head>
<body>
  <main>
{body}
  </main>
</body>
</html>
"""


def write_text(path: Path, text: str, dry_run: bool) -> None:
  if dry_run:
    print(f"  would write {path.as_posix()} ({len(text)} bytes)")
    return
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text, encoding="utf-8")
  print(f"  wrote {path.as_posix()}")


def render_cards_html(
  view: SectionView,
  *,
  lang: str,
  story_href_prefix: str = "",
) -> str:
  """Card grid HTML for a section. story_href_prefix e.g. 'themes/' on full view."""
  cards: list[str] = []
  for it in view.items:
    meta_html = f'<p class="meta">{html.escape(it.meta)}</p>' if it.meta else ""
    body_html = f'<div class="md-prose">{md_to_html(it.body)}</div>' if it.body else ""
    if it.full_story:
      href = f"{story_href_prefix}{it.slug}.html"
      link = (
        f'<p class="story-link"><a href="{html.escape(href)}">'
        f'{"పూర్తి కథ" if lang == "te" else "Read more"}</a></p>'
      )
    elif it.story_url:
      link = (
        f'<p class="story-link"><a href="{html.escape(it.story_url)}" '
        f'target="_blank" rel="noopener noreferrer">'
        f'{"బయటి లింక్" if lang == "te" else "External link"}</a></p>'
      )
    else:
      link = ""
    if it.slug == "empty" and not it.title:
      cards.append(
        f'<p class="empty">{html.escape(it.body)}</p>'
      )
      continue
    title = html.escape(it.title or ("అంశం" if lang == "te" else "Item"))
    cards.append(
      f'<article class="card">\n'
      f'  <h2>{title}</h2>\n'
      f"  {meta_html}\n"
      f"  {body_html}\n"
      f"  {link}\n"
      f"</article>"
    )
  if not cards:
    return (
      f'<p class="empty">{"ఈ విభాగానికి అంశాలు లేవు." if lang == "te" else "No items in this section."}</p>'
    )
  return f'<div class="cards">\n{chr(10).join(cards)}\n</div>'


def render_section_index(
  view: SectionView,
  *,
  month: str,
  lang: str,
  css_href: str,
  catalog_href: str,
  month_href: str,
  full_href: str | None = None,
) -> str:
  other = "en" if lang == "te" else "te"
  other_label = "English" if other == "en" else "తెలుగు"
  lead_html = f'<div class="lead md-prose">{md_to_html(view.lead)}</div>' if view.lead else ""
  cards = render_cards_html(view, lang=lang)
  full_label = "పూర్తి సంచిక" if lang == "te" else "Full issue"
  full_crumb = (
    f' · <a href="{html.escape(full_href)}">{full_label}</a>' if full_href else ""
  )

  body = f"""    <p class="crumb">
      <a href="{html.escape(catalog_href)}">Magazine</a> ·
      <a href="{html.escape(month_href)}">{html.escape(month)}</a>{full_crumb} ·
      <a href="../{other}/{html.escape(view.key)}/index.html">{other_label}</a>
    </p>
    <p class="brand">Quantum Life University</p>
    <h1>{html.escape(view.heading)}</h1>
    <p class="sub">{html.escape(month)} · {html.escape(view.key)}</p>
    {lead_html}
    {cards}"""
  return page_shell(title=f"{view.heading} · {month}", css_href=css_href, body=body, lang=lang)


def render_full_issue(
  views: list[SectionView],
  *,
  month: str,
  lang: str,
  css_href: str,
  catalog_href: str,
  month_href: str,
) -> str:
  """Print-like single scroll: TOC + every section with cards."""
  other = "en" if lang == "te" else "te"
  other_label = "English" if other == "en" else "తెలుగు"
  toc_label = "విషయ సూచిక" if lang == "te" else "Contents"
  issue_title = "పూర్తి సంచిక" if lang == "te" else "Full issue"

  toc_items = "".join(
    f'<li><a href="#section-{html.escape(v.key)}">{html.escape(v.heading)}</a></li>'
    for v in views
  )

  sheets: list[str] = []
  for view in views:
    lead_html = (
      f'<div class="lead md-prose">{md_to_html(view.lead)}</div>' if view.lead else ""
    )
    cards = render_cards_html(view, lang=lang, story_href_prefix=f"{view.key}/")
    sheets.append(
      f'<section class="print-sheet" id="section-{html.escape(view.key)}">\n'
      f'  <h2 class="sheet-title">{html.escape(view.heading)}</h2>\n'
      f'  <p class="sheet-key">{html.escape(view.key)}</p>\n'
      f"  {lead_html}\n"
      f"  {cards}\n"
      f"</section>"
    )

  body = f"""    <p class="crumb">
      <a href="{html.escape(catalog_href)}">Magazine</a> ·
      <a href="{html.escape(month_href)}">{html.escape(month)}</a> ·
      <a href="../{other}/index.html">{other_label}</a>
    </p>
    <p class="brand">Quantum Life University</p>
    <h1>{issue_title}</h1>
    <p class="sub">{html.escape(month)}</p>
    <nav class="toc" aria-label="{toc_label}">
      <h2>{toc_label}</h2>
      <ol>{toc_items}</ol>
    </nav>
    <div class="print-desk">
{chr(10).join(sheets)}
    </div>"""
  return page_shell(title=f"{issue_title} · {month}", css_href=css_href, body=body, lang=lang)


def render_story_page(
  view: SectionView,
  item: CardItem,
  *,
  month: str,
  lang: str,
  css_href: str,
) -> str:
  back = "విభాగానికి తిరిగి" if lang == "te" else "Back to section"
  title = item.title or ("కథ" if lang == "te" else "Story")
  meta_html = f'<p class="meta">{html.escape(item.meta)}</p>' if item.meta else ""
  body = f"""    <p class="crumb">
      <a href="./index.html">{html.escape(view.heading)}</a>
    </p>
    <p class="brand">Quantum Life University</p>
    <h1>{html.escape(title)}</h1>
    <p class="sub">{html.escape(month)} · {html.escape(view.key)}</p>
    {meta_html}
    <article class="story md-prose">
{md_to_html(item.full_story)}
    </article>
    <p class="back"><a href="./index.html">{back}</a></p>"""
  return page_shell(title=f"{title} · {month}", css_href=css_href, body=body, lang=lang)


def render_month_index(
  *,
  month: str,
  sections_by_lang: dict[str, list[str]],
  css_href: str,
  catalog_href: str,
) -> str:
  blocks: list[str] = []
  for lang in LANGS:
    keys = sections_by_lang.get(lang) or []
    label = "తెలుగు" if lang == "te" else "English"
    full_label = "పూర్తి సంచిక" if lang == "te" else "Full issue"
    if not keys:
      continue
    full_link = (
      f'<p class="full-link"><a href="{lang}/index.html">{full_label}</a></p>'
    )
    links = "".join(
      f'<li><a href="{lang}/{html.escape(k)}/index.html">'
      f'{html.escape(SECTION_TITLES.get(k, {}).get(lang, k))}</a></li>'
      for k in keys
    )
    blocks.append(
      f"<h2>{label}</h2>\n{full_link}\n<ul class=\"section-list\">{links}</ul>"
    )

  body = f"""    <p class="crumb"><a href="{html.escape(catalog_href)}">Magazine</a></p>
    <p class="brand">Quantum Life University</p>
    <h1>{html.escape(month)}</h1>
    <p class="sub">Exported magazine sections</p>
    {chr(10).join(blocks) or '<p class="empty">No sections yet.</p>'}"""
  return page_shell(title=f"Issue {month}", css_href=css_href, body=body, lang="en")


def render_catalog(
  *,
  months: dict[str, dict[str, list[str]]],
  css_href: str,
  base_url: str,
) -> str:
  if not months:
    list_html = '<p class="empty">No exported issues yet. Run export_section_pages.py.</p>'
  else:
    parts: list[str] = []
    for month in sorted(months.keys(), reverse=True):
      sec_bits: list[str] = []
      for lang in LANGS:
        keys = months[month].get(lang) or []
        if not keys:
          continue
        full_label = "full" if lang == "en" else "పూర్తి"
        sec_bits.append(
          f'<a href="issues/{html.escape(month)}/{lang}/index.html">'
          f'{html.escape(month)} · {lang} · {full_label}</a>'
        )
        for k in keys:
          label = SECTION_TITLES.get(k, {}).get(lang, k)
          href = f"issues/{html.escape(month)}/{lang}/{html.escape(k)}/index.html"
          sec_bits.append(
            f'<a href="{href}">{html.escape(month)} · {lang} · {html.escape(label)}</a>'
          )
      month_href = f"issues/{html.escape(month)}/index.html"
      parts.append(
        f'<li class="catalog-month">'
        f'<a class="month-link" href="{month_href}">{html.escape(month)}</a>'
        f'<div class="catalog-links">{"".join(f"<span>{b}</span>" for b in sec_bits)}</div>'
        f"</li>"
      )
    list_html = f'<ul class="catalog">{chr(10).join(parts)}</ul>'

  tools_href = f"{base_url}/Tools/index.html" if base_url else "../Tools/index.html"
  body = f"""    <p class="brand">Quantum Life University</p>
    <h1>Magazine exports</h1>
    <p class="sub">Static section pages for GitHub Pages. <a href="{html.escape(tools_href)}">Newsletter Tools</a></p>
    {list_html}"""
  return page_shell(title="QLU Magazine exports", css_href=css_href, body=body, lang="en")


def scan_exported(docs: Path) -> dict[str, dict[str, list[str]]]:
  """month → lang → [section keys] from existing docs/issues tree."""
  root = docs / "issues"
  out: dict[str, dict[str, list[str]]] = {}
  if not root.is_dir():
    return out
  for month_dir in sorted(p for p in root.iterdir() if p.is_dir()):
    month = month_dir.name
    if not re.fullmatch(r"\d{4}-\d{2}", month):
      continue
    out[month] = {"te": [], "en": []}
    for lang in LANGS:
      lang_dir = month_dir / lang
      if not lang_dir.is_dir():
        continue
      for sec_dir in sorted(p for p in lang_dir.iterdir() if p.is_dir()):
        if (sec_dir / "index.html").is_file():
          out[month][lang].append(sec_dir.name)
  return out


def ensure_docs_assets(docs: Path, dry_run: bool) -> None:
  nojekyll = docs / ".nojekyll"
  if not dry_run:
    docs.mkdir(parents=True, exist_ok=True)
  if not nojekyll.exists():
    write_text(nojekyll, "", dry_run)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def export_section_files(
  *,
  docs: Path,
  month: str,
  views_by_lang: dict[str, SectionView],
  dry_run: bool,
  include_full_link: bool,
) -> None:
  section_css = "../../../../magazine.css"
  for lang, view in views_by_lang.items():
    if not view.items and not view.lead:
      print(f"  skip {lang}/{view.key} (empty)")
      continue
    sec_dir = docs / "issues" / month / lang / view.key
    index_html = render_section_index(
      view,
      month=month,
      lang=lang,
      css_href=section_css,
      catalog_href="../../../../index.html",
      month_href="../../../index.html",
      full_href="../index.html" if include_full_link else None,
    )
    write_text(sec_dir / "index.html", index_html, dry_run)

    for it in view.items:
      if not it.full_story:
        continue
      story_html = render_story_page(
        view,
        it,
        month=month,
        lang=lang,
        css_href=section_css,
      )
      write_text(sec_dir / f"{it.slug}.html", story_html, dry_run)


def main() -> int:
  ap = argparse.ArgumentParser(description="Export CMS Issue section(s) to static docs/ HTML")
  ap.add_argument("--month", required=True, help="Issue month YYYY-MM")
  ap.add_argument(
    "--section",
    required=True,
    choices=SECTION_CHOICES,
    help="Section key, or 'all' for every present section + full-issue page",
  )
  ap.add_argument(
    "--url",
    default=os.environ.get("PAYLOAD_URL", "http://localhost:3000"),
    help="Payload CMS base URL",
  )
  ap.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL", "admin@qlu.local"))
  ap.add_argument(
    "--password",
    default=os.environ.get("SEED_ADMIN_PASSWORD", "qlu-admin-change-me"),
  )
  ap.add_argument(
    "--out",
    default=str(REPO_ROOT / "docs"),
    help="Output root (default: docs/)",
  )
  ap.add_argument(
    "--base-url",
    default="/qlu-newsletter-tools",
    help="GitHub Pages project base path (CSS/catalog). Use '' for user site root.",
  )
  ap.add_argument("--dry-run", action="store_true", help="Plan only; do not write files")
  args = ap.parse_args()

  if not re.fullmatch(r"\d{4}-\d{2}", args.month):
    raise SystemExit("--month must be YYYY-MM")

  docs = Path(args.out).resolve()
  base_url = normalize_base_url(args.base_url)
  cms = args.url.rstrip("/")

  print(f"Logging in to {cms} as {args.email} …")
  token = login(cms, args.email, args.password)
  issue = find_issue(cms, args.month, token)
  keys = resolve_export_keys(issue, args.section)

  print(f"Issue id={issue.get('id')} month={args.month} sections={', '.join(keys)}")

  # key → lang → SectionView
  allow_empty = args.section == "all"
  normalized: dict[str, dict[str, SectionView]] = {}
  for key in keys:
    section = section_or_stub(issue, key) if allow_empty else find_section(issue, key)
    by_lang = {
      lang: normalize_section_for_export(section, lang, allow_empty=allow_empty)
      for lang in LANGS
    }
    has_real = any(
      (v.lead or any(it.slug != "empty" for it in v.items)) for v in by_lang.values()
    )
    if not has_real and not allow_empty:
      print(f"  skip {key} (no exportable content)")
      continue
    normalized[key] = by_lang
    for lang, view in by_lang.items():
      real_n = sum(1 for it in view.items if it.slug != "empty")
      print(f"  {key}/{lang}: {real_n} item(s) · {view.heading[:56]}")

  if not normalized:
    raise SystemExit(f"Nothing to export for {args.month} ({args.section})")

  ensure_docs_assets(docs, args.dry_run)

  write_full = args.section == "all"
  for key, by_lang in normalized.items():
    # Only write per-section folders for sections that have real items
    if not any(
      any(it.slug != "empty" for it in v.items) or v.lead for v in by_lang.values()
    ):
      continue
    export_section_files(
      docs=docs,
      month=args.month,
      views_by_lang=by_lang,
      dry_run=args.dry_run,
      include_full_link=write_full,
    )

  # Full-issue Print-like scroll (TOC + every section) — --section all
  if write_full:
    full_css = "../../../magazine.css"
    for lang in LANGS:
      views = [
        normalized[key][lang]
        for key in SECTION_KEYS
        if key in normalized
      ]
      if not views:
        continue
      full_html = render_full_issue(
        views,
        month=args.month,
        lang=lang,
        css_href=full_css,
        catalog_href="../../../index.html",
        month_href="../../index.html",
      )
      write_text(docs / "issues" / args.month / lang / "index.html", full_html, args.dry_run)

  exported = scan_exported(docs)
  if args.dry_run:
    exported.setdefault(args.month, {"te": [], "en": []})
    for lang in LANGS:
      exported[args.month][lang] = sorted(
        set(exported[args.month][lang]) | set(normalized.keys())
      )
  else:
    exported = scan_exported(docs)

  month_html = render_month_index(
    month=args.month,
    sections_by_lang=exported.get(args.month, {"te": [], "en": []}),
    css_href="../../magazine.css",
    catalog_href="../../index.html",
  )
  write_text(docs / "issues" / args.month / "index.html", month_html, args.dry_run)

  catalog_html = render_catalog(
    months=exported,
    css_href="magazine.css",
    base_url=base_url,
  )
  write_text(docs / "index.html", catalog_html, args.dry_run)

  if args.dry_run:
    print("Dry run complete — no files written.")
  else:
    full_te = docs / "issues" / args.month / "te" / "index.html"
    print(f"Done. Full issue: {full_te if write_full else docs / 'index.html'}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
