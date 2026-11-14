#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import one (or more) Jnanodayam day JSON packs into QLU News → jnanodayam-readings.

Same shape as Devi Navaratri seed: sections → body HTML (h2 + p), optional cover image.
Upserts by series + day.

Day JSON (from the daywise master prompt):

  {
    "dayNumber": 592,
    "title": "…",
    "language": "te",
    "sections": [
      { "title": "…", "content": ["para…"], "minutes": 3, "startSec": 3720 }
    ]
  }

Examples:

  python scripts/import_jnanodayam_reading.py ^
    --json "C:\\Users\\dhana\\Downloads\\day-592-te.json" ^
    --cover "C:\\Users\\dhana\\Downloads\\…Day-592[ir4blTXdoDE]_thumb.jpg"

  python scripts/import_jnanodayam_reading.py ^
    --json day-592-te.json --json-en day-592-en.json --cover thumb.jpg ^
    --series daily --title-en "Patriji Birthday Special"

  python scripts/import_jnanodayam_reading.py --folder out\\day-592 --dry-run

Auth (Payload admin):
  PAYLOAD_URL          default http://localhost:3000
  SEED_ADMIN_EMAIL     default admin@qlu.local
  SEED_ADMIN_PASSWORD  default qlu-admin-change-me
"""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
import sys
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

DEFAULT_SERIES = "daily"


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


def find_existing_media_id(base: str, token: str, filename: str) -> int | str | None:
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

  parts: list[bytes] = [
    (
      f"--{boundary}\r\n"
      f'Content-Disposition: form-data; name="alt"\r\n\r\n'
      f"{alt}\r\n"
    ).encode("utf-8"),
    (
      f"--{boundary}\r\n"
      f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
      f"Content-Type: {ctype}\r\n\r\n"
    ).encode("utf-8")
    + file_bytes
    + b"\r\n",
    f"--{boundary}--\r\n".encode("utf-8"),
  ]
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


def load_day_json(path: Path) -> dict:
  if not path.is_file():
    raise SystemExit(f"JSON not found: {path}")
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except json.JSONDecodeError as e:
    raise SystemExit(f"Invalid JSON {path}: {e}") from e
  if not isinstance(data, dict):
    raise SystemExit(f"Expected object in {path}")
  return data


def sections_to_html(sections: list) -> str:
  """Match CMS seed chaptersToHtml: <h2>title</h2> + <p>para</p>."""
  parts: list[str] = []
  for sec in sections or []:
    if not isinstance(sec, dict):
      continue
    title = html.escape(str(sec.get("title") or "").strip())
    if title:
      parts.append(f"<h2>{title}</h2>")
    content = sec.get("content") or []
    if isinstance(content, str):
      content = [content]
    for para in content:
      text = str(para or "").strip()
      if text:
        parts.append(f"<p>{html.escape(text)}</p>")
  return "\n".join(parts)


def ascii_filename(name: str, fallback: str) -> str:
  """Payload/media on some setups choke on non-ASCII filenames; keep a safe copy name."""
  stem = Path(name).stem
  ext = Path(name).suffix.lower() or ".jpg"
  if re.search(r"[^\x00-\x7F]", stem):
    return f"{fallback}{ext}"
  safe = re.sub(r"[^\w.\-\[\]]+", "-", stem).strip("-")
  return f"{safe or fallback}{ext}"


def resolve_from_folder(folder: Path) -> tuple[Path | None, Path | None, Path | None]:
  """Find day-*-te.json, optional day-*-en.json, and a *_thumb / cover image."""
  te = next(iter(sorted(folder.glob("day-*-te.json"))), None)
  if not te:
    te = next(iter(sorted(folder.glob("*-te.json"))), None)
  en = None
  if te:
    cand = te.with_name(te.name.replace("-te.json", "-en.json"))
    if cand.is_file():
      en = cand
  cover = next(iter(sorted(folder.glob("*_thumb.*"))), None)
  if not cover:
    for pat in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
      imgs = sorted(folder.glob(pat))
      if imgs:
        cover = imgs[0]
        break
  return te, en, cover


def find_reading(base: str, token: str, series: str, day: int) -> dict | None:
  url = (
    f"{base}/api/jnanodayam-readings?limit=1"
    f"&where[and][0][series][equals]={quote(series)}"
    f"&where[and][1][day][equals]={day}"
  )
  out = http_json("GET", url, token=token)
  docs = out.get("docs") or []
  return docs[0] if docs else None


def upsert_reading(
  base: str,
  token: str,
  payload: dict,
  *,
  dry_run: bool,
) -> None:
  series = payload["series"]
  day = payload["day"]
  existing = None if dry_run else find_reading(base, token, series, day)
  if dry_run:
    action = "create/update"
    print(
      f"[dry-run] would {action} {series} day {day} "
      f"(te={bool(payload.get('bodyHtmlTe'))}, en={bool(payload.get('bodyHtmlEn'))}, "
      f"cover={payload.get('cover')})"
    )
    return

  if existing:
    http_json(
      "PATCH",
      f"{base}/api/jnanodayam-readings/{existing['id']}",
      token=token,
      body=payload,
    )
    print(f"Updated {series} day {day} (id={existing['id']})")
  else:
    out = http_json(
      "POST",
      f"{base}/api/jnanodayam-readings",
      token=token,
      body=payload,
    )
    doc = out.get("doc") or out
    print(f"Created {series} day {day} (id={doc.get('id')})")


def build_payload(
  *,
  series: str,
  te: dict | None,
  en: dict | None,
  title_en: str | None,
  title_te: str | None,
  subtitle_en: str | None,
  subtitle_te: str | None,
  cover_id: int | str | None,
  published: bool,
  existing: dict | None = None,
) -> dict:
  day = None
  for src in (te, en):
    if src and src.get("dayNumber") is not None:
      day = int(src["dayNumber"])
      break
  if day is None:
    raise SystemExit("dayNumber missing in JSON")

  te_title = (title_te or (te or {}).get("title") or "").strip()
  en_title = (title_en or (en or {}).get("title") or "").strip()
  if not en_title and en is not None:
    en_title = f"Jnanodayam · Day {day}"
  if not te_title and te is not None:
    te_title = en_title or f"జ్ఞానోదయం · రోజు {day}"

  body_te = sections_to_html((te or {}).get("sections") or []) if te else ""
  body_en = sections_to_html((en or {}).get("sections") or []) if en else ""

  payload: dict = {
    "editLang": "te" if te else "en",
    "series": series,
    "day": day,
    "published": published,
  }

  # Only touch language fields we were given — EN-only must not wipe Telugu titles.
  if te is not None:
    payload["titleTe"] = te_title
    payload["subtitleTe"] = (
      subtitle_te if subtitle_te is not None else te_title
    ).strip()
    if body_te:
      payload["bodyHtmlTe"] = body_te
  if en is not None:
    payload["titleEn"] = en_title
    payload["subtitleEn"] = (
      subtitle_en if subtitle_en is not None else en_title
    ).strip()
    if body_en:
      payload["bodyHtmlEn"] = body_en

  # Create requires both title fields; fill missing side from the other / existing.
  if not existing:
    if "titleTe" not in payload:
      payload["titleTe"] = (
        (existing or {}).get("titleTe")
        or en_title
        or f"జ్ఞానోదయం · రోజు {day}"
      )
    if "titleEn" not in payload:
      payload["titleEn"] = (
        te_title or f"Jnanodayam · Day {day}"
      )

  if cover_id is not None:
    payload["cover"] = cover_id
  return payload


def main() -> None:
  ap = argparse.ArgumentParser(
    description="Import Jnanodayam day JSON (+ optional cover) into Payload readings",
  )
  ap.add_argument("--json", "--json-te", dest="json_te", help="Telugu day-NNN-te.json")
  ap.add_argument("--json-en", help="English day-NNN-en.json (optional)")
  ap.add_argument("--cover", help="Cover / thumbnail image path")
  ap.add_argument(
    "--folder",
    help="Folder with day-*-te.json (+ optional -en.json and *_thumb image)",
  )
  ap.add_argument(
    "--series",
    default=DEFAULT_SERIES,
    choices=("daily", "devi-navaratri"),
    help=f'Series slug (default: "{DEFAULT_SERIES}")',
  )
  ap.add_argument("--title-en", help="English title override (required field if no EN JSON)")
  ap.add_argument("--title-te", help="Telugu title override")
  ap.add_argument("--subtitle-en", help="English day subtitle (defaults to title)")
  ap.add_argument("--subtitle-te", help="Telugu day subtitle (defaults to title)")
  ap.add_argument("--unpublished", action="store_true", help="Create as draft")
  ap.add_argument("--base", default=os.environ.get("PAYLOAD_URL", "http://localhost:3000"))
  ap.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL", "admin@qlu.local"))
  ap.add_argument(
    "--password",
    default=os.environ.get("SEED_ADMIN_PASSWORD", "qlu-admin-change-me"),
  )
  ap.add_argument("--dry-run", action="store_true")
  args = ap.parse_args()

  te_path: Path | None = Path(args.json_te) if args.json_te else None
  en_path: Path | None = Path(args.json_en) if args.json_en else None
  cover_path: Path | None = Path(args.cover) if args.cover else None

  if args.folder:
    folder = Path(args.folder)
    if not folder.is_dir():
      raise SystemExit(f"Folder not found: {folder}")
    f_te, f_en, f_cover = resolve_from_folder(folder)
    te_path = te_path or f_te
    en_path = en_path or f_en
    cover_path = cover_path or f_cover

  if not te_path and not en_path:
    raise SystemExit("Provide --json / --json-en, or --folder with day JSON.")

  te = load_day_json(te_path) if te_path else None
  en = load_day_json(en_path) if en_path else None

  if te and te.get("language") and str(te["language"]).lower() not in ("te", "telugu"):
    print(f"Warning: {te_path} language={te.get('language')!r} (expected te)", file=sys.stderr)
  if en and en.get("language") and str(en["language"]).lower() not in ("en", "english"):
    print(f"Warning: {en_path} language={en.get('language')!r} (expected en)", file=sys.stderr)

  day_hint = int((te or en or {}).get("dayNumber") or 0)
  print(f"Series: {args.series} · day {day_hint or '?'}")
  if te_path:
    print(f"  TE: {te_path}")
  if en_path:
    print(f"  EN: {en_path}")
  if cover_path:
    print(f"  Cover: {cover_path}")

  base = args.base.rstrip("/")
  token = "" if args.dry_run else login(base, args.email, args.password)

  cover_id = None
  if cover_path:
    if not cover_path.is_file():
      raise SystemExit(f"Cover not found: {cover_path}")
    if args.dry_run:
      print(f"  [dry-run] would upload {cover_path.name}")
    else:
      upload_name = ascii_filename(cover_path.name, f"jnanodayam-day-{day_hint or 'x'}-cover")
      # Reuse by safe filename if we rewrite; also try original name.
      existing_media = find_existing_media_id(base, token, upload_name)
      if existing_media is None and upload_name != cover_path.name:
        existing_media = find_existing_media_id(base, token, cover_path.name)
      if existing_media is not None:
        cover_id = existing_media
        print(f"Reusing media id={cover_id}")
      else:
        # Write a temp ASCII-named copy when needed so multipart filename is safe.
        src = cover_path
        if upload_name != cover_path.name:
          tmp = cover_path.with_name(upload_name)
          if not tmp.exists():
            tmp.write_bytes(cover_path.read_bytes())
          src = tmp
        alt = (te or en or {}).get("title") or f"Jnanodayam Day {day_hint}"
        cover_id = upload_media(base, token, src, str(alt))
        print(f"Uploaded media id={cover_id} ({src.name})")

  existing_doc = (
    None
    if args.dry_run
    else find_reading(base, token, args.series, day_hint)
  )

  payload = build_payload(
    series=args.series,
    te=te,
    en=en,
    title_en=args.title_en,
    title_te=args.title_te,
    subtitle_en=args.subtitle_en,
    subtitle_te=args.subtitle_te,
    cover_id=cover_id,
    published=not args.unpublished,
    existing=existing_doc,
  )

  n_te = payload.get("bodyHtmlTe", "").count("<h2>")
  n_en = payload.get("bodyHtmlEn", "").count("<h2>")
  print(f"  Sections: te={n_te} en={n_en}")

  upsert_reading(base, token, payload, dry_run=args.dry_run)
  if not args.dry_run:
    print(
      f"View: {base.replace(':3000', ':4321')}/jnanodayam/{args.series}/{payload['day']}/te/"
      if ":3000" in base
      else f"Reading: {args.series} day {payload['day']}"
    )
  print("Done.")


if __name__ == "__main__":
  main()
