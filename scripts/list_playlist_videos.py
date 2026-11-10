#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
List videos from a YouTube channel's playlists and save a table.

Columns:
  playlist_id, playlist_title, video_id, date_happened, jnanodayam, video_title

date_happened is the YouTube publish date in India time (UTC+5:30).
jnanodayam is yes when the title contains జ్ఞానోదయం or "jnanodayam".

Default channel is QLU Global Telugu. Default months are September and October
of the current year. Scanning stops once playlists are older than that window.

Examples (from repo root):
  python scripts/list_playlist_videos.py
  python scripts/list_playlist_videos.py --months 9,10 --year 2026 -o out/sep-oct.csv
  python scripts/list_playlist_videos.py --playlist PLY8cw6DnA5GI -o out/one.csv
  python scripts/list_playlist_videos.py --all -o out/all-playlists.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from download_youtube_captions import (  # noqa: E402
  WEB_UA,
  browse_playlist,
  continuation_token,
  fetch_player,
  fetch_playlist_videos,
  parse_playlist_id,
  walk,
  web_context,
)

DEFAULT_CHANNEL = "https://www.youtube.com/@qluglobaltelugu/playlists"
IST = timezone(timedelta(hours=5, minutes=30))
REPO = Path(__file__).resolve().parent.parent

COLUMNS = (
  "playlist_id",
  "playlist_title",
  "video_id",
  "date_happened",
  "jnanodayam",
  "video_title",
)


def _console() -> None:
  for stream in (sys.stdout, sys.stderr):
    try:
      stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
      pass


def text_of(node: Any) -> str | None:
  if isinstance(node, str):
    text = node.strip()
    return text or None
  if not isinstance(node, dict):
    return None
  for key in ("content", "simpleText"):
    if isinstance(node.get(key), str) and node[key].strip():
      return node[key].strip()
  runs = node.get("runs")
  if isinstance(runs, list):
    parts = [r.get("text", "") for r in runs if isinstance(r, dict) and isinstance(r.get("text"), str)]
    text = "".join(parts).strip()
    if text:
      return text
  return None


def is_jnanodayam(title: str) -> bool:
  folded = title.casefold()
  return (
    "జ్ఞానోదయం" in title
    or "jnanodayam" in folded
    or "jnanaodayam" in folded
    or "gnanaodayam" in folded
  )


def playlists_url(raw: str) -> str:
  text = raw.strip()
  if "://" not in text:
    text = "https://www.youtube.com/" + text.lstrip("/")
  parsed = urllib.parse.urlparse(text)
  path = parsed.path.rstrip("/")
  if not path.endswith("/playlists"):
    path = path + "/playlists"
  return urllib.parse.urlunparse((parsed.scheme or "https", parsed.netloc, path, "", "", ""))


def fetch_html(url: str) -> str:
  req = urllib.request.Request(
    url,
    headers={
      "User-Agent": WEB_UA,
      "Accept-Language": "en,te;q=0.8",
      "Cookie": "CONSENT=YES+; SOCS=CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjQwMTI0LjA3X3AxGgJlbiACGgYIgJS8rgY",
    },
  )
  with urllib.request.urlopen(req, timeout=60) as resp:
    return resp.read().decode("utf-8", errors="replace")


def extract_initial_data(html: str) -> Any | None:
  marker = html.find("ytInitialData")
  if marker < 0:
    return None
  brace = html.find("{", marker)
  if brace < 0:
    return None
  depth = 0
  in_str = False
  esc = False
  for i in range(brace, len(html)):
    ch = html[i]
    if in_str:
      if esc:
        esc = False
      elif ch == "\\":
        esc = True
      elif ch == '"':
        in_str = False
      continue
    if ch == '"':
      in_str = True
    elif ch == "{":
      depth += 1
    elif ch == "}":
      depth -= 1
      if depth == 0:
        try:
          return json.loads(html[brace : i + 1])
        except json.JSONDecodeError:
          return None
  return None


def playlists_from_payload(payload: Any) -> list[dict]:
  found: list[dict] = []
  seen: set[str] = set()

  def add(playlist_id: str, title: str | None) -> None:
    if not playlist_id.startswith("PL") or playlist_id in seen:
      return
    seen.add(playlist_id)
    found.append({"playlistId": playlist_id, "title": (title or playlist_id).strip()})

  def visit(item: dict) -> None:
    lockup = item.get("lockupViewModel")
    if isinstance(lockup, dict) and isinstance(lockup.get("contentId"), str):
      meta = lockup.get("metadata") if isinstance(lockup.get("metadata"), dict) else {}
      lockup_meta = meta.get("lockupMetadataViewModel") if isinstance(meta.get("lockupMetadataViewModel"), dict) else {}
      add(lockup["contentId"], text_of(lockup_meta.get("title")) or text_of(lockup.get("metadata")))
      return
    classic = item.get("gridPlaylistRenderer") or item.get("playlistRenderer")
    if isinstance(classic, dict) and isinstance(classic.get("playlistId"), str):
      add(classic["playlistId"], text_of(classic.get("title")))

  walk(payload, visit)
  return found


def list_channel_playlists(channel: str) -> list[dict]:
  url = playlists_url(channel)
  html = fetch_html(url)
  payload = extract_initial_data(html)
  if payload is None:
    raise RuntimeError(f"Could not read playlists from {url}")
  playlists = playlists_from_payload(payload)
  seen_tokens: set[str] = set()
  context = web_context("en")
  for _ in range(12):
    token = continuation_token(payload)
    if not token or token in seen_tokens:
      break
    seen_tokens.add(token)
    payload = browse_playlist({"context": context, "continuation": token}, WEB_UA)
    playlists.extend(item for item in playlists_from_payload(payload) if item["playlistId"] not in {p["playlistId"] for p in playlists})
  if not playlists:
    raise RuntimeError(f"No public playlists found at {url}")
  # Dedupe while keeping order (extend above already filters, first page is unique).
  uniq: list[dict] = []
  seen: set[str] = set()
  for item in playlists:
    if item["playlistId"] in seen:
      continue
    seen.add(item["playlistId"])
    uniq.append(item)
  return uniq


def to_ist_date(raw: str) -> date | None:
  text = raw.strip()
  if not text:
    return None
  if len(text) == 10 and text[4] == "-" and text[7] == "-":
    try:
      return date.fromisoformat(text)
    except ValueError:
      return None
  try:
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
  except ValueError:
    return None
  if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)
  return dt.astimezone(IST).date()


def _microformat_date(player: Any) -> str | None:
  mf = (player.get("microformat") or {}).get("playerMicroformatRenderer") or {}
  raw = mf.get("publishDate") or mf.get("uploadDate")
  return raw if isinstance(raw, str) and raw.strip() else None


def publish_raw(video_id: str) -> str | None:
  try:
    raw = _microformat_date(fetch_player(video_id, "en"))
    if raw:
      return raw
  except Exception:
    pass
  from download_youtube_captions import http_json

  try:
    player = http_json(
      "https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
      method="POST",
      body={"context": web_context("en"), "videoId": video_id},
      user_agent=WEB_UA,
    )
  except Exception:
    return None
  return _microformat_date(player)


def fetch_happened_on(video_id: str) -> date | None:
  try:
    raw = publish_raw(video_id)
  except Exception:
    raw = None
  if not raw:
    return None
  return to_ist_date(raw)


def parse_months(raw: str) -> set[int]:
  months: set[int] = set()
  for part in raw.split(","):
    part = part.strip()
    if not part:
      continue
    value = int(part)
    if value < 1 or value > 12:
      raise argparse.ArgumentTypeError(f"Month out of range: {part}")
    months.add(value)
  if not months:
    raise argparse.ArgumentTypeError("Give at least one month, for example 9,10")
  return months


def in_window(happened: date | None, year: int, months: set[int] | None) -> bool:
  if months is None:
    return True
  if happened is None:
    return False
  return happened.year == year and happened.month in months


def rows_for_playlist(playlist_id: str, playlist_title: str, workers: int) -> list[dict]:
  videos = fetch_playlist_videos(playlist_id, "en", 120)
  with ThreadPoolExecutor(max_workers=workers) as pool:
    dates = list(pool.map(fetch_happened_on, [v["videoId"] for v in videos]))
  rows: list[dict] = []
  for video, happened in zip(videos, dates):
    title = (video.get("title") or video["videoId"]).strip()
    rows.append(
      {
        "playlist_id": playlist_id,
        "playlist_title": playlist_title,
        "video_id": video["videoId"],
        "date_happened": happened.isoformat() if happened else "",
        "jnanodayam": "yes" if is_jnanodayam(title) else "no",
        "video_title": title,
        "_date": happened,
      }
    )
  return rows


def write_csv(path: Path, rows: list[dict]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(COLUMNS), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
      writer.writerow(row)


def default_out(year: int, months: set[int] | None) -> Path:
  if months is None:
    name = "playlist-videos-all.csv"
  else:
    tag = "-".join(f"{month:02d}" for month in sorted(months))
    name = f"playlist-videos-{year}-{tag}.csv"
  return REPO / "out" / name


def build_rows(args: argparse.Namespace) -> list[dict]:
  months: set[int] | None = None if args.all else args.months
  year = args.year
  if args.playlist:
    targets = []
    for raw in args.playlist:
      playlist_id = parse_playlist_id(raw)
      if not playlist_id:
        raise SystemExit(f"Not a playlist id or URL: {raw}")
      targets.append({"playlistId": playlist_id, "title": playlist_id})
  else:
    print(f"Reading playlists from {playlists_url(args.channel)}", flush=True)
    targets = list_channel_playlists(args.channel)
    print(f"Found {len(targets)} playlist(s)", flush=True)

  window_start = date(year, min(months), 1) if months else None
  kept: list[dict] = []
  older_streak = 0
  for index, playlist in enumerate(targets, start=1):
    playlist_id = playlist["playlistId"]
    title = playlist["title"]
    print(f"[{index}] {title} ({playlist_id})", flush=True)
    try:
      rows = rows_for_playlist(playlist_id, title, args.workers)
    except Exception as exc:
      print(f"  skipped: {exc}", file=sys.stderr, flush=True)
      older_streak = 0
      continue
    dated = [row["_date"] for row in rows if row["_date"] is not None]
    matched = [row for row in rows if in_window(row["_date"], year, months)]
    kept.extend(matched)
    if dated:
      print(
        f"  {len(rows)} video(s), {min(dated)} .. {max(dated)}, kept {len(matched)}",
        flush=True,
      )
    else:
      print(f"  {len(rows)} video(s), no publish dates, kept {len(matched)}", flush=True)
    if window_start and dated and max(dated) < window_start:
      older_streak += 1
      if older_streak >= 2 and not args.playlist:
        print("Stopped: later playlists are older than the requested months.", flush=True)
        break
    else:
      older_streak = 0

  kept.sort(key=lambda row: (row["date_happened"], row["playlist_title"], row["video_title"], row["video_id"]))
  return kept


def main() -> None:
  _console()
  today = date.today()
  parser = argparse.ArgumentParser(description="Save channel playlist videos as a CSV table.")
  parser.add_argument(
    "--channel",
    default=DEFAULT_CHANNEL,
    help="Channel or playlists URL (default: QLU Global Telugu)",
  )
  parser.add_argument(
    "--playlist",
    action="append",
    help="One playlist id or URL. Repeat to add more. Skips the channel scan.",
  )
  parser.add_argument(
    "--months",
    type=parse_months,
    default=parse_months("9,10"),
    help="Months to keep, comma-separated (default: 9,10). Ignored with --all.",
  )
  parser.add_argument("--year", type=int, default=today.year, help=f"Year to keep (default: {today.year})")
  parser.add_argument("--all", action="store_true", help="Keep every video, no month filter")
  parser.add_argument("-o", "--out", type=Path, help="CSV path (default: out/playlist-videos-….csv)")
  parser.add_argument("--workers", type=int, default=6, help="Parallel date lookups (default: 6)")
  args = parser.parse_args()
  if args.workers < 1:
    parser.error("--workers must be at least 1")

  rows = build_rows(args)
  out = args.out or default_out(args.year, None if args.all else args.months)
  if not out.is_absolute():
    out = REPO / out
  write_csv(out, rows)
  jnana = sum(1 for row in rows if row["jnanodayam"] == "yes")
  print(f"Wrote {len(rows)} row(s) ({jnana} jnanodayam) to {out}", flush=True)


if __name__ == "__main__":
  main()
