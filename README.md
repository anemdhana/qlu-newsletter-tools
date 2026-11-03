# qlu-newsletter-tools

Standalone tools for Quantum Life University newsletter / reading prep.

Companion to:

- [`quantum-life-university`](../quantum-life-university) — app + admin Prepare UI
- [`quantum-life-university-news`](../quantum-life-university-news) — Payload + Astro magazine
- [`qlu-monthly-newsletter`](../qlu-monthly-newsletter) — WordPress magazine sibling

## Start the Tools UI (recommended)

Captions + frame extract need a **local Python server** (browser pages cannot run `.py` as `file://`).

```powershell
cd c:\Users\dhana\GitHub\qlu-newsletter-tools
.\start.cmd
```

Starts the server and opens **http://127.0.0.1:8765/Tools/index.html** so you can click each tool:

| Page | Action |
|------|--------|
| **Download YouTube captions** | Video or playlist → `.txt` / zip in `out/` |
| **Extract frame at time** | Timestamp still → image in `out/` |

Also in the hub (browser-only): Telugu speech→text, newsletter beautify.

```powershell
# or
python serve.py
```

## CLI (Python 3.10+)

### Captions (same as admin Prepare UI)

Stdlib only by default (Innertube API). Optional `--engine yt-dlp`.

```powershell
python scripts/download_youtube_captions.py VIDEO_ID --lang te
python scripts/download_youtube_captions.py --playlist PLxxxx --lang te -o out\playlist
python scripts/download_youtube_captions.py VIDEO_ID --lang te --engine yt-dlp
```

### Extract frame at time (same as app Tools)

Needs **ffmpeg** on PATH (+ **yt-dlp**, auto-pip if missing).

```powershell
python scripts/extract_youtube_frame.py VIDEO_ID --time 00:01:30
python scripts/extract_youtube_frame.py "https://youtu.be/VIDEO_ID" -t 90 -o out\frame.jpg
```

Optional env: `YT_DLP_PATH`, `FFMPEG_PATH`.

## Layout

```text
qlu-newsletter-tools/
  README.md
  requirements.txt
  Tools/                         # static HTML hub (from QLU Tools/)
  scripts/
    download_youtube_captions.py
    extract_youtube_frame.py
  out/
```

## Requirements

```text
# optional (yt-dlp engine / frame extract)
pip install -r requirements.txt
# ffmpeg separately, e.g. winget install Gyan.FFmpeg
```
