#!/usr/bin/env python3
"""
Download YouTube captions the same way the QLU admin Prepare UI does
(quantum-life-university: lib/youtube/captions.ts + playlist.ts).

Default engine: YouTube Innertube ANDROID player API (stdlib only — no yt-dlp).
Optional: --engine yt-dlp  (auto-pip installs yt-dlp if missing).

Examples (from repo root):
  python scripts/download_youtube_captions.py VIDEO_ID --lang te
  python scripts/download_youtube_captions.py https://youtu.be/VIDEO_ID --lang en -o out/video.txt
  python scripts/download_youtube_captions.py --playlist PLxxxx --lang te -o out/playlist
  python scripts/download_youtube_captions.py -p "https://www.youtube.com/playlist?list=PLxxxx" --lang te
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Literal

Lang = Literal["te", "en", "auto"]

ANDROID_UA = "com.google.android.youtube/20.10.38 (Linux; U; Android 14) gzip"
WEB_UA = (
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")
PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,80}$")


# —— IDs ——

def parse_youtube_id(raw: str) -> str | None:
  trimmed = raw.strip()
  if VIDEO_ID_RE.match(trimmed):
    return trimmed
  try:
    url = urllib.parse.urlparse(trimmed if "://" in trimmed else f"https://{trimmed}")
    host = (url.hostname or "").lower()
    if "youtu.be" in host:
      part = next((p for p in url.path.split("/") if p), "")
      vid = part[:11]
      return vid if VIDEO_ID_RE.match(vid) else None
    qs = urllib.parse.parse_qs(url.query)
    if "v" in qs and VIDEO_ID_RE.match(qs["v"][0]):
      return qs["v"][0]
  except Exception:
    pass
  m = re.search(r"(?:v=|/embed/|/shorts/|youtu\.be/)([a-zA-Z0-9_-]{11})", trimmed)
  return m.group(1) if m else None


def parse_playlist_id(raw: str) -> str | None:
  trimmed = raw.strip()
  if PLAYLIST_ID_RE.match(trimmed) and re.match(r"^(PL|UU|LL|FL|OL|RD|TL)", trimmed):
    return trimmed
  try:
    url = urllib.parse.urlparse(trimmed if "://" in trimmed else f"https://{trimmed}")
    qs = urllib.parse.parse_qs(url.query)
    lst = (qs.get("list") or [None])[0]
    if lst and PLAYLIST_ID_RE.match(lst):
      return lst
  except Exception:
    pass
  m = re.search(r"[?&]list=([A-Za-z0-9_-]{10,80})", trimmed)
  return m.group(1) if m else None


# —— HTTP ——

def http_json(url: str, *, method: str = "GET", body: dict | None = None, user_agent: str = ANDROID_UA) -> Any:
  data = None if body is None else json.dumps(body).encode("utf-8")
  req = urllib.request.Request(
    url,
    data=data,
    method=method,
    headers={
      "Content-Type": "application/json",
      "User-Agent": user_agent,
      "Accept-Language": "en,te;q=0.8",
    },
  )
  try:
    with urllib.request.urlopen(req, timeout=60) as resp:
      return json.loads(resp.read().decode("utf-8", errors="replace"))
  except urllib.error.HTTPError as e:
    raise RuntimeError(f"HTTP {e.code} for {url}") from e


def http_text(url: str, *, user_agent: str = ANDROID_UA) -> str:
  req = urllib.request.Request(
    url,
    headers={"User-Agent": user_agent, "Accept-Language": "en,te;q=0.8"},
  )
  with urllib.request.urlopen(req, timeout=60) as resp:
    return resp.read().decode("utf-8", errors="replace")


# —— Caption parse (mirrors captions.ts) ——

def decode_entities(value: str) -> str:
  return html_lib.unescape(value).replace("\xa0", " ")


def clean_caption_text(value: str) -> str:
  text = decode_entities(value)
  text = re.sub(r"<[^>]+>", " ", text)
  return re.sub(r"\s+", " ", text).strip()


def parse_xml_captions(xml: str) -> list[dict]:
  cues: list[dict] = []
  for m in re.finditer(r"<text\b([^>]*)>([\s\S]*?)</text>", xml, re.I):
    sm = re.search(r'\bstart="([0-9.]+)"', m.group(1), re.I)
    if not sm:
      continue
    text = clean_caption_text(m.group(2))
    if text:
      cues.append({"startSec": float(sm.group(1)), "text": text})
  if cues:
    return cues
  for m in re.finditer(r"<p\b([^>]*)>([\s\S]*?)</p>", xml, re.I):
    sm = re.search(r'\bt="(\d+)"', m.group(1), re.I)
    if not sm:
      continue
    text = clean_caption_text(m.group(2))
    if text:
      cues.append({"startSec": int(sm.group(1)) / 1000.0, "text": text})
  return cues


def parse_json3_captions(payload: Any) -> list[dict]:
  if not isinstance(payload, dict):
    return []
  events = payload.get("events")
  if not isinstance(events, list):
    return []
  cues: list[dict] = []
  for event in events:
    if not isinstance(event, dict):
      continue
    t = event.get("tStartMs")
    segs = event.get("segs")
    if not isinstance(t, (int, float)) or not isinstance(segs, list):
      continue
    text = clean_caption_text("".join(str(s.get("utf8", "")) for s in segs if isinstance(s, dict)))
    if text and text != "\n":
      cues.append({"startSec": t / 1000.0, "text": text})
  return cues


def tracks_from_player(player: Any) -> list[dict]:
  if not isinstance(player, dict):
    return []
  captions = player.get("captions")
  if not isinstance(captions, dict):
    return []
  renderer = captions.get("playerCaptionsTracklistRenderer") or {}
  listing = renderer.get("captionTracks") if isinstance(renderer, dict) else None
  if not isinstance(listing, list):
    return []
  tracks: list[dict] = []
  for item in listing:
    if not isinstance(item, dict):
      continue
    base = item.get("baseUrl")
    lang = item.get("languageCode")
    if not isinstance(base, str) or not isinstance(lang, str):
      continue
    name_obj = item.get("name")
    name = None
    if isinstance(name_obj, str):
      name = name_obj
    elif isinstance(name_obj, dict) and isinstance(name_obj.get("simpleText"), str):
      name = name_obj["simpleText"]
    tracks.append(
      {
        "baseUrl": base.replace("\\u0026", "&").replace("&amp;", "&"),
        "languageCode": lang.lower(),
        "kind": item.get("kind") if isinstance(item.get("kind"), str) else None,
        "name": name,
      }
    )
  return tracks


def short_lang(code: str) -> str:
  primary = (code or "und").split("-")[0].lower()
  return primary[:8] or "und"


def lang_family(code: str) -> int:
  """Lower is better for QLU: Telugu, then English, then anything else."""
  c = code.lower()
  if c in ("te", "tel") or c.startswith("te-") or c.startswith("tel-"):
    return 0
  if c == "en" or c.startswith("en-"):
    return 1
  return 2


def pick_track(tracks: list[dict], preferred: Lang) -> dict | None:
  if preferred == "te":
    aliases = ["te", "tel", "te-in"]
  elif preferred == "en":
    aliases = ["en", "en-us", "en-gb", "en-in"]
  else:
    aliases = []

  def rank(t: dict) -> tuple[int, ...]:
    code = t["languageCode"]
    asr = 1 if t.get("kind") == "asr" else 0
    if preferred == "auto":
      return (lang_family(code), asr)
    pref = 0 if any(code == a or code.startswith(f"{a}-") for a in aliases) else 1
    # Prefer requested language; if missing, still take best available (te → en → other).
    return (pref, lang_family(code), asr)

  ranked = sorted(tracks, key=rank)
  return ranked[0] if ranked else None


def fetch_player(video_id: str, preferred: Lang) -> Any:
  hl = "te" if preferred == "te" else "en"
  gl = "IN" if preferred in ("te", "auto") else "US"
  return http_json(
    "https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
    method="POST",
    body={
      "context": {
        "client": {
          "clientName": "ANDROID",
          "clientVersion": "20.10.38",
          "hl": hl,
          "gl": gl,
        }
      },
      "videoId": video_id,
    },
    user_agent=ANDROID_UA,
  )


def download_track(base_url: str) -> list[dict]:
  for fmt in ("fmt=json3", "fmt=srv3", ""):
    url = f"{base_url}{'&' if '?' in base_url else '?'}{fmt}" if fmt else base_url
    try:
      body = http_text(url, user_agent=ANDROID_UA)
    except Exception:
      continue
    if not body.strip():
      continue
    if body.strip().startswith("{"):
      try:
        cues = parse_json3_captions(json.loads(body))
        if cues:
          return cues
      except json.JSONDecodeError:
        pass
    cues = parse_xml_captions(body)
    if cues:
      return cues
  return []


def fetch_youtube_captions(video_id: str, preferred: Lang) -> tuple[list[dict], str]:
  player = fetch_player(video_id, preferred)
  playability = player.get("playabilityStatus") if isinstance(player, dict) else None
  if isinstance(playability, dict):
    status = playability.get("status")
    if status and status != "OK":
      raise RuntimeError(playability.get("reason") or f"YouTube will not play that video ({status}).")

  tracks = tracks_from_player(player)
  if not tracks:
    raise RuntimeError("No captions were found on that video. Turn on subtitles on YouTube, then try again.")

  track = pick_track(tracks, preferred)
  if not track:
    raise RuntimeError("No matching caption track was found.")

  cues = download_track(track["baseUrl"])
  if not cues:
    raise RuntimeError(
      "The caption track downloaded empty. Auto-captions sometimes need a few minutes after upload — try again shortly."
    )
  return cues, short_lang(track["languageCode"])


def captions_as_text(cues: list[dict]) -> str:
  lines: list[str] = []
  for cue in cues:
    total = max(0, int(cue["startSec"]))
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = f"{total % 60:02d}"
    clock = f"{hours}:{minutes:02d}:{seconds}" if hours else f"{minutes}:{seconds}"
    lines.append(f"[{clock}] {cue['text']}")
  return "\n".join(lines)


# —— Playlist (mirrors playlist.ts) ——

def walk(node: Any, visit) -> None:
  if isinstance(node, list):
    for item in node:
      walk(item, visit)
    return
  if not isinstance(node, dict):
    return
  visit(node)
  for value in node.values():
    walk(value, visit)


def continuation_token(payload: Any) -> str | None:
  found: list[str] = []

  def visit(item: dict) -> None:
    if found:
      return
    endpoint = item.get("continuationEndpoint") or item.get("nextContinuationData")
    if isinstance(endpoint, dict):
      command = endpoint.get("continuationCommand")
      if isinstance(command, dict) and isinstance(command.get("token"), str):
        found.append(command["token"])
        return
    if isinstance(item.get("token"), str) and (item.get("clickTrackingParams") or item.get("continuation")):
      found.append(item["token"])

  walk(payload, visit)
  return found[0] if found else None


def title_from_runs(title_obj: Any) -> str | None:
  if not isinstance(title_obj, dict):
    return None
  if isinstance(title_obj.get("content"), str):
    return title_obj["content"]
  if isinstance(title_obj.get("simpleText"), str):
    return title_obj["simpleText"]
  runs = title_obj.get("runs")
  if isinstance(runs, list) and runs and isinstance(runs[0], dict) and isinstance(runs[0].get("text"), str):
    return runs[0]["text"]
  return None


def videos_from_payload(payload: Any) -> list[dict]:
  found: list[dict] = []
  seen: set[str] = set()

  def push(video_id: str, title: str) -> None:
    if not VIDEO_ID_RE.match(video_id) or video_id in seen:
      return
    seen.add(video_id)
    found.append({"videoId": video_id, "title": title or video_id, "index": len(found) + 1})

  def visit(item: dict) -> None:
    classic = item.get("playlistVideoRenderer")
    if isinstance(classic, dict) and isinstance(classic.get("videoId"), str):
      push(classic["videoId"], title_from_runs(classic.get("title")) or classic["videoId"])
      return
    lockup = item.get("lockupViewModel")
    if isinstance(lockup, dict):
      content_id = lockup.get("contentId") if isinstance(lockup.get("contentId"), str) else None
      meta = lockup.get("metadata") if isinstance(lockup.get("metadata"), dict) else None
      lockup_meta = meta.get("lockupMetadataViewModel") if isinstance(meta, dict) else None
      title = title_from_runs(lockup_meta.get("title") if isinstance(lockup_meta, dict) else None)
      if not title and isinstance(lockup.get("accessibilityText"), str):
        title = lockup["accessibilityText"]
      if content_id:
        push(content_id, title or content_id)

  walk(payload, visit)
  return found


def browse_playlist(body: dict, user_agent: str) -> Any:
  return http_json(
    "https://www.youtube.com/youtubei/v1/browse?prettyPrint=false",
    method="POST",
    body=body,
    user_agent=user_agent,
  )


def android_context(preferred: Lang) -> dict:
  hl = "te" if preferred == "te" else "en"
  return {
    "client": {
      "clientName": "ANDROID",
      "clientVersion": "20.10.38",
      "hl": hl,
      "gl": "IN" if preferred in ("te", "auto") else "US",
    }
  }


def web_context(preferred: Lang) -> dict:
  hl = "te" if preferred == "te" else "en"
  return {
    "client": {
      "clientName": "WEB",
      "clientVersion": "2.20240304.00.00",
      "hl": hl,
      "gl": "IN" if preferred in ("te", "auto") else "US",
    }
  }


def collect_from_browse(playlist_id: str, preferred: Lang, max_videos: int, mode: str) -> list[dict]:
  context = android_context(preferred) if mode == "android" else web_context(preferred)
  user_agent = ANDROID_UA if mode == "android" else WEB_UA
  payload = browse_playlist({"context": context, "browseId": f"VL{playlist_id}"}, user_agent)
  videos: list[dict] = []
  seen: set[str] = set()

  for _ in range(20):
    if len(videos) >= max_videos:
      break
    for item in videos_from_payload(payload):
      if item["videoId"] in seen:
        continue
      seen.add(item["videoId"])
      videos.append({**item, "index": len(videos) + 1})
      if len(videos) >= max_videos:
        break
    token = continuation_token(payload)
    if not token or len(videos) >= max_videos:
      break
    payload = browse_playlist({"context": context, "continuation": token}, user_agent)
  return videos


def collect_from_html(playlist_id: str, max_videos: int) -> list[dict]:
  try:
    page = http_text(
      f"https://www.youtube.com/playlist?list={urllib.parse.quote(playlist_id)}",
      user_agent=WEB_UA,
    )
  except Exception:
    return []
  m = re.search(r"ytInitialData\s*=\s*(\{[\s\S]*?\});\s*</script>", page)
  if not m:
    return []
  try:
    data = json.loads(m.group(1))
  except json.JSONDecodeError:
    return []
  return [{**v, "index": i + 1} for i, v in enumerate(videos_from_payload(data)[:max_videos])]


def fetch_playlist_videos(playlist_id: str, preferred: Lang = "te", max_videos: int = 80) -> list[dict]:
  videos = collect_from_browse(playlist_id, preferred, max_videos, "android")
  if not videos:
    videos = collect_from_browse(playlist_id, preferred, max_videos, "web")
  if not videos:
    videos = collect_from_html(playlist_id, max_videos)
  if not videos:
    raise RuntimeError("No videos found in that playlist. Check the playlist ID and that it is public.")
  return videos


def safe_title_slug(title: str, max_len: int = 80) -> str:
  """Filesystem-safe slug that keeps the real title (Telugu marks included)."""
  slug = (title or "").strip()
  # Drop only Windows/path-forbidden chars; keep letters, marks, punctuation lightly
  slug = re.sub(r'[\\/:*?"<>|]+', "", slug)
  slug = re.sub(r"\s+", "-", slug)
  slug = re.sub(r"[^\S\r\n]+", "-", slug)  # any leftover odd whitespace
  slug = re.sub(r"-{2,}", "-", slug).strip(".- ")
  if len(slug) > max_len:
    slug = slug[:max_len].rstrip("-.")
  return slug or "video"


def safe_caption_filename(
  index: int | None,
  video_id: str,
  title: str,
  language: str,
) -> str:
  """Name: [NN-]{actual-title}-{lang}-captions[{videoId}].txt"""
  label = safe_title_slug(title)
  prefix = f"{index:02d}-" if index is not None else ""
  return f"{prefix}{label}-{language}-captions[{video_id}].txt"


def fetch_video_title(video_id: str) -> str:
  try:
    player = fetch_player(video_id, "auto")
    details = player.get("videoDetails") if isinstance(player, dict) else None
    if isinstance(details, dict):
      title = details.get("title")
      if isinstance(title, str) and title.strip():
        return title.strip()
  except Exception:
    pass
  return video_id


# —— Optional yt-dlp engine ——

def ensure_yt_dlp_cmd() -> list[str]:
  """Prefer `python -m yt_dlp` (avoids WinError 193 from a bad PATH binary)."""
  module_cmd = [sys.executable, "-m", "yt_dlp"]
  try:
    r = subprocess.run(module_cmd + ["--version"], capture_output=True, timeout=15)
    if r.returncode == 0:
      return module_cmd
  except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
    pass
  print("yt-dlp not found — installing with pip…", file=sys.stderr)
  subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"])
  r = subprocess.run(module_cmd + ["--version"], capture_output=True, timeout=15)
  if r.returncode == 0:
    return module_cmd
  raise RuntimeError("Could not run yt-dlp. Try: python -m pip install -U yt-dlp")


def _vtt_lang_code(path: Path, video_id: str) -> str:
  # yt-dlp names: VIDEOID.te.vtt / VIDEOID.en-US.vtt
  name = path.name
  prefix = f"{video_id}."
  if name.startswith(prefix) and name.endswith(".vtt"):
    return short_lang(name[len(prefix) : -4])
  return "und"


def _pick_vtt(paths: list[Path], video_id: str, preferred: Lang) -> Path:
  def rank(p: Path) -> tuple[int, ...]:
    code = _vtt_lang_code(p, video_id)
    if preferred == "auto":
      return (lang_family(code),)
    if preferred == "te":
      match = 0 if code in ("te", "tel") else 1
    else:
      match = 0 if code == "en" else 1
    return (match, lang_family(code))

  return sorted(paths, key=rank)[0]


def fetch_captions_yt_dlp(video_id: str, preferred: Lang, work: Path) -> tuple[list[dict], str]:
  """Fallback via yt-dlp VTT → cue list (approximate same [m:ss] text format)."""
  ytdlp_cmd = ensure_yt_dlp_cmd()
  work.mkdir(parents=True, exist_ok=True)
  outtmpl = str(work / f"{video_id}.%(ext)s")
  if preferred == "auto":
    langs = "all"
  elif preferred == "te":
    langs = "te.*,te,tel"
  else:
    langs = "en.*,en"
  cmd = [
    *ytdlp_cmd,
    "--skip-download",
    "--write-auto-subs",
    "--write-subs",
    "--sub-langs",
    langs,
    "--sub-format",
    "vtt/best",
    "-o",
    outtmpl,
    f"https://www.youtube.com/watch?v={video_id}",
  ]
  subprocess.run(cmd, check=False, capture_output=True)
  vtts = sorted(work.glob(f"{video_id}*.vtt"))
  if not vtts:
    raise RuntimeError("yt-dlp did not produce subtitle files for that video/language.")
  chosen = _pick_vtt(vtts, video_id, preferred)
  lang = _vtt_lang_code(chosen, video_id)
  return vtt_to_cues(chosen.read_text(encoding="utf-8", errors="replace")), lang


def vtt_ts_to_sec(ts: str) -> float:
  # 00:01:02.000 or 01:02.000
  parts = ts.strip().replace(",", ".").split(":")
  parts = [float(p) for p in parts]
  if len(parts) == 3:
    return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if len(parts) == 2:
    return parts[0] * 60 + parts[1]
  return float(parts[0])


def vtt_to_cues(vtt: str) -> list[dict]:
  cues: list[dict] = []
  blocks = re.split(r"\n\s*\n", vtt.replace("\r\n", "\n"))
  for block in blocks:
    timing: str | None = None
    text_lines: list[str] = []
    for ln in block.split("\n"):
      if "-->" in ln:
        timing = ln.split("-->")[0].strip()
        text_lines = []
        continue
      if timing is None:
        continue
      stripped = ln.strip()
      if stripped and not re.match(r"^\d+$", stripped) and not stripped.startswith("WEBVTT"):
        text_lines.append(clean_caption_text(re.sub(r"<[^>]+>", "", ln)))
    if timing and text_lines:
      text = " ".join(t for t in text_lines if t)
      if text:
        cues.append({"startSec": vtt_ts_to_sec(timing), "text": text})
  if not cues:
    raise RuntimeError("Could not parse VTT captions from yt-dlp output.")
  return cues


# —— CLI ——

def write_text(path: Path, text: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text, encoding="utf-8", newline="\n")
  print(f"Wrote {path} ({len(text.splitlines())} lines)")


def download_one(video_input: str, lang: Lang, engine: str, out: Path | None) -> Path:
  video_id = parse_youtube_id(video_input)
  if not video_id:
    raise SystemExit("Enter a YouTube video ID or URL.")
  title = fetch_video_title(video_id)
  if engine == "yt-dlp":
    cues, used_lang = fetch_captions_yt_dlp(video_id, lang, Path(".yt-dlp-cache") / video_id)
  else:
    cues, used_lang = fetch_youtube_captions(video_id, lang)
  text = captions_as_text(cues)
  if out is None:
    name = safe_caption_filename(None, video_id, title, used_lang)
    dest = Path(name)
  else:
    dest = out
  # Prefer a titled header when saving default-named files
  if out is None and title and title != video_id:
    text = f"# {title}\n# https://www.youtube.com/watch?v={video_id}\n# language={used_lang}\n\n{text}"
  write_text(dest, text)
  print(
    f"OK: {len(cues)} cue lines · language={used_lang} (requested={lang}) · "
    f"engine={engine} · {dest.name}"
  )
  return dest


def download_playlist(playlist_input: str, lang: Lang, engine: str, out: Path | None, max_videos: int) -> Path:
  playlist_id = parse_playlist_id(playlist_input)
  if not playlist_id:
    raise SystemExit("Enter a YouTube playlist ID or URL (list=…).")

  videos = fetch_playlist_videos(playlist_id, lang, max_videos)
  print(f"Playlist {playlist_id}: {len(videos)} video(s)")

  folder_tag = lang if lang != "auto" else "auto"
  out_dir = out or Path(f"{playlist_id}-{folder_tag}-captions")
  out_dir.mkdir(parents=True, exist_ok=True)
  entries: list[tuple[str, str]] = []
  failures: list[str] = []
  ok_count = 0
  cue_total = 0

  for video in videos:
    vid = video["videoId"]
    title = video["title"]
    idx = video["index"]
    print(f"  [{idx}/{len(videos)}] {vid} — {title[:60]}")
    try:
      if engine == "yt-dlp":
        cues, used_lang = fetch_captions_yt_dlp(vid, lang, Path(".yt-dlp-cache") / vid)
      else:
        cues, used_lang = fetch_youtube_captions(vid, lang)
      name = safe_caption_filename(idx, vid, title, used_lang)
      text = captions_as_text(cues)
      body = (
        f"# {title}\n"
        f"# https://www.youtube.com/watch?v={vid}\n"
        f"# language={used_lang}\n\n"
        f"{text}\n"
      )
      write_text(out_dir / name, body)
      entries.append((name, body))
      ok_count += 1
      cue_total += len(cues)
      time.sleep(0.35)
    except Exception as e:
      msg = f"{vid} — {title}\n   {e}"
      failures.append(msg)
      print(f"    FAIL: {e}", file=sys.stderr)

  if not entries:
    raise SystemExit(f"Playlist captions failed. {failures[0] if failures else 'No files.'}")

  if failures:
    report = f"Playlist {playlist_id}\nSucceeded: {ok_count}\nFailed: {len(failures)}\n\n" + "\n\n".join(
      f"{i+1}. {f}" for i, f in enumerate(failures)
    )
    write_text(out_dir / "_failures.txt", report + "\n")

  manifest = "\n".join(
    [
      f"Playlist: {playlist_id}",
      f"Language preference: {lang}",
      f"Videos in playlist (capped): {len(videos)}",
      f"Caption files: {ok_count}",
      f"Failures: {len(failures)}",
      f"Total cue lines: {cue_total}",
      "",
      *[name for name, _ in entries],
      "",
    ]
  )
  write_text(out_dir / "_manifest.txt", manifest)

  zip_path = Path(f"{playlist_id}-{folder_tag}-captions.zip")
  with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("_manifest.txt", manifest)
    for name, body in entries:
      zf.writestr(name, body)
    if failures:
      zf.writestr("_failures.txt", (out_dir / "_failures.txt").read_text(encoding="utf-8"))
  print(f"Zip: {zip_path} ({ok_count}/{len(videos)} ok, {cue_total} cues)")
  return zip_path


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Download YouTube captions like QLU admin Prepare UI (Innertube API by default)."
  )
  parser.add_argument("video", nargs="?", help="Video ID or URL")
  parser.add_argument("--playlist", "-p", help="Playlist ID or URL")
  parser.add_argument(
    "--lang",
    "-l",
    choices=("auto", "te", "en"),
    default="auto",
    help="Caption language: auto picks available track (te→en→other); default auto",
  )
  parser.add_argument(
    "--engine",
    choices=("innertube", "yt-dlp"),
    default="innertube",
    help="innertube = same as admin UI (default); yt-dlp = optional fallback (auto-installs)",
  )
  parser.add_argument("-o", "--out", type=Path, help="Output .txt file, or folder for playlist")
  parser.add_argument("--max-videos", type=int, default=80, help="Playlist safety cap (default 80)")
  args = parser.parse_args()

  if not args.playlist and not args.video:
    parser.error("Provide a video ID/URL or --playlist")

  if args.playlist:
    download_playlist(args.playlist, args.lang, args.engine, args.out, args.max_videos)
  else:
    download_one(args.video, args.lang, args.engine, args.out)


if __name__ == "__main__":
  main()
