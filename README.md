# qlu-newsletter-tools

Standalone tools for Quantum Life University newsletter / reading prep.

Companion to:

- [`quantum-life-university`](../quantum-life-university) — app + admin Prepare UI
- [`quantum-life-university-news`](../quantum-life-university-news) — Payload + Astro magazine
- [`qlu-monthly-newsletter`](../qlu-monthly-newsletter) — WordPress magazine sibling

## Setup for a new developer

1. **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)  
   On Windows, check **Add python.exe to PATH**.
2. Install packages (includes **yt-dlp** + a bundled **ffmpeg** for frame extract):

```powershell
cd c:\Users\dhana\GitHub\qlu-newsletter-tools
python -m pip install -r requirements.txt
```

3. Start the hub: `.\start.cmd` (also runs `pip install -r requirements.txt` if needed).

| Need | Covered by |
|------|------------|
| Captions (default) | Python stdlib only |
| Captions (yt-dlp engine) | `yt-dlp` in requirements.txt |
| Extract frame | `yt-dlp` + `imageio-ffmpeg` (bundled ffmpeg) |
| System ffmpeg (optional) | `winget install Gyan.FFmpeg` or `FFMPEG_PATH` |
| Theme import / static export CLI | Stdlib; Payload `:3000` and/or Astro `:4321` running |

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
| **Voice type** | Whisper (+ QLU glossary) mic/upload, or quick browser speech — Telugu default |
| **Beautify / Publication prompts** | ChatGPT prompts for newsletter wording / full articles |

```powershell
# or (after pip install -r requirements.txt)
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

### Whisper transcription (Voice type — accurate)

Needs **faster-whisper** + **ffmpeg** (from `requirements.txt`). First run downloads the model.

```powershell
python scripts/whisper_transcribe.py path\to\audio.webm --lang te --model small
python scripts/whisper_transcribe.py path\to\lecture.mp3 --lang en --model medium
```

UI: **Tools → Voice type → Whisper** — record with the mic or upload audio. Glossary priming improves spiritual / Sanskrit spellings.

### Extract frame at time (same as app Tools)

Needs **yt-dlp** + **ffmpeg**. After `pip install -r requirements.txt`, ffmpeg comes from **imageio-ffmpeg** (no separate install). Falls back to system `ffmpeg` / `FFMPEG_PATH` when present.

```powershell
python scripts/extract_youtube_frame.py VIDEO_ID --time 00:01:30
python scripts/extract_youtube_frame.py "https://youtu.be/VIDEO_ID" -t 90 -o out\frame.jpg
```

Optional env: `YT_DLP_PATH`, `FFMPEG_PATH`.

### Pick best portrait / smile frames

Clone of the frame extract flow, but runs three steps: **sample** → **score** (face + smile via OpenCV) → **keep top picks**. Filenames match Extract frame: `{title}[{videoId}]_00h01m30s.jpg`.

**UI:** Tools → Extract frame → mode **Best portrait / smile** (video or playlist → zip). API: `POST /api/pick-portrait`.

```powershell
python scripts/pick_best_portrait_frame.py VIDEO_ID
python scripts/pick_best_portrait_frame.py VIDEO_ID --start 00:45:00 --end 01:15:00 --every-min 1 --top 3
python scripts/pick_best_portrait_frame.py "https://youtu.be/VIDEO_ID" -o out\portraits --top 5 --every-min 2
python scripts/pick_best_portrait_frame.py --playlist PLxxxx -o out\portraits --top 1 --start 00:30:00 --end 01:00:00
```

Defaults: **start `00:45:00`**, **end `01:15:00`**, **sample every 1 minute** (short videos clamp the window). Writes JPGs under `out/portrait-picks` (playlist → `{playlistId}-portrait-picks.zip`). First run may `pip install opencv-python-headless`.

### Import theme Read More → Payload CMS

Reads theme `.md` files (legacy Newsletter/Read More **or** master publication lecture editions) and appends Theme Items. **Skips day numbers already present** unless `--replace-existing`.

```powershell
python scripts/import_theme_readmore.py --folder "C:\Users\dhana\Downloads\QLU_Ganesha_Days_535-538_Revised_ReadMore" --month 2026-11 --dry-run
python scripts/import_theme_readmore.py --folder "C:\Users\dhana\Downloads\QLU_Ganesha_Days_535-538_Revised_ReadMore" --month 2026-11
```

#### From a shared Google Drive folder

```powershell
python scripts/import_theme_readmore_gdrive.py --dry-run
python scripts/import_theme_readmore_gdrive.py --month 2026-11 --heading-needle "దేవీ నవరాత్రి" --create-section --set-heading "దేవీ నవరాత్రుల జ్ఞానం"
```

Default folder: [Devi Navratri Drive folder](https://drive.google.com/drive/folders/1lWK1kKW5eb1Zy3ZOfxjKJYWTMC4-cQLX) (must be shared “Anyone with the link”). Downloads into `out/gdrive-theme-import/`, picks the best **Telugu + English** file per day (pairs by Jnanodayam day into `*Te` / `*En` fields), skips days already on the Issue unless `--replace-existing` (or fills missing EN).

CMS must be running (`http://localhost:3000`).

### Import theme frame images → Payload CMS

Downloads YouTube stills from Drive (names like `{title}[{videoId}]_00h59m51s.jpg`) and sets each matching Themes entry’s `image`. Match order: **video id → day number → title tokens**. When several frames share a day/video, keeps the earliest timestamp (`--pick last|largest` to change).

```powershell
python scripts/import_theme_images_gdrive.py --dry-run
python scripts/import_theme_images_gdrive.py --month 2026-11 --heading-needle "గణేశ"
```

Default folder: [Ganesha frame stills](https://drive.google.com/drive/folders/1JlcjTqqFHliDlc5TibjmJ6Viq7J_pbJF). Local-only: `python scripts/import_theme_images.py --folder out\frames --month 2026-11`.

CMS must already expose `themeItems.image` (QLU News Issues schema). Skips items that already have an image unless `--replace-existing`.

### Export section → static GitHub Pages (`docs/`)

Pulls one Issue section from Payload and writes TE + EN HTML under `docs/issues/{month}/…` (catalog at `docs/index.html`).

```powershell
python scripts/export_section_pages.py --month 2026-11 --section themes
python scripts/export_section_pages.py --month 2026-11 --section all
```

Section keys: `themes`, `highlight-classes`, `experiences`, `visits`, `vanya`, `campus`, `upcoming`, or **`all`**.

### Snapshot Astro Print (exact look)

Copies the live Print view HTML, `qlu.css`, logos/media images, and story pages into `docs/` (same look as `http://localhost:4321/issues/{month}/te/?view=print`).

```powershell
# Astro (4321) + CMS (3000) must be running
python scripts/export_print_snapshot.py --month 2026-11
python scripts/export_print_snapshot.py --month 2026-11 --lang te
```

Open `docs/issues/2026-11/te/index.html`. Enable **GitHub Pages**: Settings → Pages → Deploy from branch → `master` (or `main`) → folder **`/docs`**.

## Layout

```text
qlu-newsletter-tools/
  README.md
  requirements.txt
  Tools/                         # static HTML hub (from QLU Tools/)
  docs/                          # GitHub Pages magazine exports
  scripts/
    download_youtube_captions.py
    extract_youtube_frame.py
    import_theme_readmore.py
    import_theme_readmore_gdrive.py
    import_theme_images.py
    import_theme_images_gdrive.py
    export_section_pages.py
    export_print_snapshot.py
  out/
```

## Requirements

```powershell
python -m pip install -r requirements.txt
# installs yt-dlp + imageio-ffmpeg (bundled ffmpeg for Extract frame)

# optional system ffmpeg instead of / in addition to the bundle:
# winget install Gyan.FFmpeg
```

See comments in [`requirements.txt`](requirements.txt) for the full new-developer checklist.
