#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import illustrated Ganesha Puranic stories into QLU News → ganesha-stories.

Parses the publication Markdown + images folder, uploads covers to Payload Media,
and upserts each story by slug.

Example:

  python scripts/import_ganesha_stories.py

  python scripts/import_ganesha_stories.py ^
    --folder "C:\\Users\\dhana\\Downloads\\QLU_Ganesha_Publication_Illustrated_Telugu" ^
    --dry-run

Auth (Payload admin):
  PAYLOAD_URL          default http://localhost:3000
  SEED_ADMIN_EMAIL     default admin@qlu.local
  SEED_ADMIN_PASSWORD  default qlu-admin-change-me
  Or pass --email / --password / --base.
"""

from __future__ import annotations

import argparse
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

DEFAULT_FOLDER_CANDIDATES = [
  Path(r"C:\Users\dhana\GitHub\quantum-life-university-news\content\ganesha-stories"),
  Path(r"C:\Users\dhana\Downloads\QLU_Ganesha_Publication_Illustrated_Telugu"),
]

DEFAULT_LABEL = "Sri Ganesha Tattva"

STORY_META = {
  "vakratunda-matsarasura": {
    "sortOrder": 1,
    "titleEn": "Vakratunda — Matsarasura",
    "taglineEn": "Recognizing jealousy and widening the heart",
    "day": 531,
    "image": "vakratunda-matsarasura.png",
  },
  "dhumravarna-ahankasura": {
    "sortOrder": 2,
    "titleEn": "Dhumravarna — Ahankasura",
    "taglineEn": "From ‘I am great’ toward humility",
    "day": 536,
    "image": "dhumravarna-ahankasura.png",
  },
  "lambodara-krodhasura": {
    "sortOrder": 3,
    "titleEn": "Lambodara — Krodhasura",
    "taglineEn": "What happens in us when anger rises?",
    "day": 537,
    "image": "lambodara-krodhasura.png",
  },
  "vikata-kamasura": {
    "sortOrder": 4,
    "titleEn": "Vikata — Kamasura",
    "taglineEn": "Desire is not wrong; do not become its slave",
    "day": 538,
    "image": "vikata-kamasura.png",
  },
}

SLUG_FROM_IMAGE = {
  "vakratunda-matsarasura.png": "vakratunda-matsarasura",
  "dhumravarna-ahankasura.png": "dhumravarna-ahankasura",
  "lambodara-krodhasura.png": "lambodara-krodhasura",
  "vikata-kamasura.png": "vikata-kamasura",
}

H2_STORY_RE = re.compile(r"^##\s+(\d+)\.\s+(.+)$", re.M)
META_DAY_RE = re.compile(
  r"\*\*జ్ఞానోదయం\s+(\d+)వ\s+రోజు\s*\|\s*([^*]+)\*\*",
)
VIDEO_RE = re.compile(r"\*\*వీడియో:\*\*\s*(https://\S+)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\((images/[^)]+)\)")


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

  parts: list[bytes] = []
  parts.append(
    (
      f"--{boundary}\r\n"
      f'Content-Disposition: form-data; name="alt"\r\n\r\n'
      f"{alt}\r\n"
    ).encode("utf-8")
  )
  parts.append(
    (
      f"--{boundary}\r\n"
      f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
      f"Content-Type: {ctype}\r\n\r\n"
    ).encode("utf-8")
    + file_bytes
    + b"\r\n"
  )
  parts.append(f"--{boundary}--\r\n".encode("utf-8"))
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


def find_md(folder: Path) -> Path:
  matches = sorted(folder.glob("*.md"))
  if not matches:
    raise SystemExit(f"No .md found in {folder}")
  preferred = [
    p
    for p in matches
    if "Ganesha" in p.name or "ganesha" in p.name or "Puranic" in p.name
  ]
  return preferred[0] if preferred else matches[0]


def resolve_folder(explicit: str | None) -> Path:
  if explicit:
    path = Path(explicit)
    if not path.is_dir():
      raise SystemExit(f"Folder not found: {path}")
    return path
  for cand in DEFAULT_FOLDER_CANDIDATES:
    if cand.is_dir() and list(cand.glob("*.md")):
      return cand
  raise SystemExit(
    "No default folder found. Pass --folder pointing at the illustrated pack."
  )


def slug_for_block(title: str, image_rel: str | None) -> str | None:
  if image_rel:
    name = Path(image_rel).name
    if name in SLUG_FROM_IMAGE:
      return SLUG_FROM_IMAGE[name]
  # Fallback from Telugu title number already handled by order + STORY_META keys.
  return None


def parse_stories(md_text: str) -> list[dict]:
  text = md_text.replace("\r\n", "\n").replace("\r", "\n")
  matches = list(H2_STORY_RE.finditer(text))
  stories: list[dict] = []

  for i, m in enumerate(matches):
    start = m.start()
    end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
    # Stop before closing editorial sections that are also ## headings without numbers.
    block = text[start:end]
    # Trim trailing non-story ## sections if present inside the slice.
    stop = re.search(r"\n##\s+(?!\\d)", block[len(m.group(0)) :])
    if stop:
      # Only cut if the next ## is not another numbered story (already handled by matches).
      pass

    title_te = m.group(2).strip()
    body = block[len(m.group(0)) :].strip()

    # Drop pack-level closing ## essays (not ### subsections).
    cut = re.search(r"\n## (?!#)", body)
    if cut:
      body = body[: cut.start()].strip()

    img_m = IMAGE_RE.search(body)
    image_rel = img_m.group(1) if img_m else None
    if img_m:
      body = (body[: img_m.start()] + body[img_m.end() :]).strip()

    tagline_te = ""
    lines = body.split("\n")
    if lines and lines[0].startswith("**") and lines[0].endswith("**"):
      tagline_te = lines[0].strip("*").strip()
      body = "\n".join(lines[1:]).strip()

    day = None
    speaker = None
    day_m = META_DAY_RE.search(body)
    if day_m:
      day = int(day_m.group(1))
      speaker = day_m.group(2).strip()
      body = (body[: day_m.start()] + body[day_m.end() :]).strip()

    video = None
    vid_m = VIDEO_RE.search(body)
    if vid_m:
      video = vid_m.group(1).strip().rstrip(")")
      body = (body[: vid_m.start()] + body[vid_m.end() :]).strip()

    # Normalize blank lines
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    slug = slug_for_block(title_te, image_rel)
    if not slug:
      # Map by story number 1..4
      n = int(m.group(1))
      by_order = {v["sortOrder"]: k for k, v in STORY_META.items()}
      slug = by_order.get(n)
    if not slug:
      print(f"Skip untitled/unmapped story: {title_te!r}", file=sys.stderr)
      continue

    meta = STORY_META[slug]
    stories.append(
      {
        "slug": slug,
        "sortOrder": meta["sortOrder"],
        "titleTe": title_te,
        "titleEn": meta["titleEn"],
        "taglineTe": tagline_te,
        "taglineEn": meta["taglineEn"],
        "jnanodayamDay": day or meta["day"],
        "speaker": speaker,
        "videoUrl": video,
        "bodyMarkdownTe": body,
        "bodyMarkdownEn": "",
        "image_rel": image_rel or f"images/{meta['image']}",
      }
    )

  return stories


def find_story(base: str, token: str, slug: str) -> dict | None:
  url = (
    f"{base}/api/ganesha-stories?limit=1"
    f"&where[slug][equals]={quote(slug)}"
  )
  out = http_json("GET", url, token=token)
  docs = out.get("docs") or []
  return docs[0] if docs else None


def upsert_story(base: str, token: str, payload: dict, *, dry_run: bool) -> None:
  slug = payload["slug"]
  existing = find_story(base, token, slug)
  if dry_run:
    action = "update" if existing else "create"
    print(
      f"[dry-run] would {action} {slug} "
      f"(day={payload.get('jnanodayamDay')}, cover={payload.get('cover')})"
    )
    return

  if existing:
    http_json(
      "PATCH",
      f"{base}/api/ganesha-stories/{existing['id']}",
      token=token,
      body=payload,
    )
    print(f"Updated {slug} (id={existing['id']})")
  else:
    out = http_json(
      "POST",
      f"{base}/api/ganesha-stories",
      token=token,
      body=payload,
    )
    doc = out.get("doc") or out
    print(f"Created {slug} (id={doc.get('id')})")


def main() -> None:
  ap = argparse.ArgumentParser(description="Import Ganesha illustrated stories into Payload")
  ap.add_argument("--folder", help="Pack folder containing .md + images/")
  ap.add_argument("--base", default=os.environ.get("PAYLOAD_URL", "http://localhost:3000"))
  ap.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL", "admin@qlu.local"))
  ap.add_argument(
    "--password",
    default=os.environ.get("SEED_ADMIN_PASSWORD", "qlu-admin-change-me"),
  )
  ap.add_argument(
    "--label",
    default=DEFAULT_LABEL,
    help=f'Theme label stored on each story (default: "{DEFAULT_LABEL}")',
  )
  ap.add_argument("--dry-run", action="store_true")
  args = ap.parse_args()

  folder = resolve_folder(args.folder)
  md_path = find_md(folder)
  md_text = md_path.read_text(encoding="utf-8")
  stories = parse_stories(md_text)
  if not stories:
    raise SystemExit(f"No stories parsed from {md_path}")

  print(f"Folder: {folder}")
  print(f"Source: {md_path.name} · {len(stories)} stories")

  base = args.base.rstrip("/")
  token = None if args.dry_run else login(base, args.email, args.password)

  for story in stories:
    image_path = folder / story["image_rel"]
    if not image_path.is_file():
      # Also try images/<name> from meta
      alt = folder / "images" / Path(story["image_rel"]).name
      image_path = alt if alt.is_file() else image_path
    if not image_path.is_file():
      raise SystemExit(f"Missing image for {story['slug']}: {story['image_rel']}")

    cover_id = None
    if args.dry_run:
      print(f"  cover → {image_path.name}")
    else:
      assert token
      existing_media = find_existing_media_id(base, token, image_path.name)
      if existing_media is not None:
        cover_id = existing_media
        print(f"Reusing media id={cover_id} for {image_path.name}")
      else:
        cover_id = upload_media(
          base,
          token,
          image_path,
          alt=story["titleTe"],
        )
        print(f"Uploaded media id={cover_id} for {image_path.name}")

    payload = {
      "editLang": "te",
      "label": args.label,
      "slug": story["slug"],
      "sortOrder": story["sortOrder"],
      "published": True,
      "titleTe": story["titleTe"],
      "titleEn": story["titleEn"],
      "taglineTe": story["taglineTe"],
      "taglineEn": story["taglineEn"],
      "jnanodayamDay": story["jnanodayamDay"],
      "speaker": story["speaker"],
      "videoUrl": story["videoUrl"],
      "bodyMarkdownTe": story["bodyMarkdownTe"],
      "bodyMarkdownEn": story["bodyMarkdownEn"],
    }
    if cover_id is not None:
      payload["cover"] = cover_id

    upsert_story(base, token or "", payload, dry_run=args.dry_run)

  print("Done.")


if __name__ == "__main__":
  main()
