#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Download theme Read More / lecture .md files from a shared Google Drive folder
and import into QLU News Issue → Themes (skips days already present).

Requires: pip install gdown  (listed in requirements.txt)

Example:

  python scripts/import_theme_readmore_gdrive.py --dry-run

  python scripts/import_theme_readmore_gdrive.py ^
    --folder-url "https://drive.google.com/drive/folders/1lWK1kKW5eb1Zy3ZOfxjKJYWTMC4-cQLX" ^
    --month 2026-11 ^
    --heading-needle "దేవీ నవరాత్రి" ^
    --create-section ^
    --set-heading "దేవీ నవరాత్రుల జ్ఞానం"

Auth (same as import_theme_readmore.py):
  PAYLOAD_URL, SEED_ADMIN_EMAIL, SEED_ADMIN_PASSWORD
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from import_theme_readmore import (  # noqa: E402
  import_theme_files,
  select_theme_md_files,
)

DEFAULT_FOLDER_URL = (
  "https://drive.google.com/drive/folders/1lWK1kKW5eb1Zy3ZOfxjKJYWTMC4-cQLX"
)
DEFAULT_HEADING_NEEDLE = "నవరాత్ర"
FOLDER_ID_RE = re.compile(r"/folders/([a-zA-Z0-9_-]+)")


def extract_folder_id(url_or_id: str) -> str:
  text = (url_or_id or "").strip()
  if not text:
    raise SystemExit("Provide --folder-url or --folder-id")
  m = FOLDER_ID_RE.search(text)
  if m:
    return m.group(1)
  if re.fullmatch(r"[a-zA-Z0-9_-]{10,}", text):
    return text
  raise SystemExit(f"Could not parse Google Drive folder id from: {text}")


def ensure_gdown():
  try:
    import gdown  # noqa: F401

    return
  except ImportError:
    pass
  print("gdown not found — installing with pip…", file=sys.stderr)
  import subprocess

  subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "gdown"])


def download_drive_folder(folder_id: str, dest: Path, *, resume: bool = True) -> Path:
  ensure_gdown()
  import gdown

  dest.mkdir(parents=True, exist_ok=True)
  print(f"Downloading Google Drive folder {folder_id} → {dest}")
  result = gdown.download_folder(
    id=folder_id,
    output=str(dest),
    quiet=False,
    resume=resume,
  )
  if not result:
    raise SystemExit(
      "Drive download returned no files. Confirm the folder is shared "
      "(Anyone with the link can view) and try again."
    )
  return dest


def main() -> int:
  ap = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter,
  )
  ap.add_argument(
    "--folder-url",
    default=DEFAULT_FOLDER_URL,
    help="Google Drive folder URL (or bare folder id)",
  )
  ap.add_argument(
    "--folder-id",
    default="",
    help="Override folder id (if set, --folder-url is ignored)",
  )
  ap.add_argument(
    "--cache-dir",
    default=str(ROOT / "out" / "gdrive-theme-import"),
    help="Local download/cache directory",
  )
  ap.add_argument("--month", default="2026-11", help="Issue month YYYY-MM")
  ap.add_argument(
    "--heading-needle",
    default=DEFAULT_HEADING_NEEDLE,
    help="Match themes section heading (substring)",
  )
  ap.add_argument(
    "--set-heading",
    default="దేవీ నవరాత్రుల జ్ఞానం",
    help="Set/create themes headingTe",
  )
  ap.add_argument(
    "--create-section",
    action="store_true",
    default=True,
    help="Create themes section when heading-needle is missing (default: on)",
  )
  ap.add_argument(
    "--no-create-section",
    action="store_true",
    help="Do not create a new themes section",
  )
  ap.add_argument("--base-url", default=os.environ.get("PAYLOAD_URL", "http://localhost:3000"))
  ap.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL", "admin@qlu.local"))
  ap.add_argument(
    "--password",
    default=os.environ.get("SEED_ADMIN_PASSWORD", "qlu-admin-change-me"),
  )
  ap.add_argument("--dry-run", action="store_true", help="Download + plan only; no PATCH")
  ap.add_argument(
    "--replace-existing",
    action="store_true",
    help="Replace same day numbers instead of skipping",
  )
  ap.add_argument(
    "--skip-download",
    action="store_true",
    help="Reuse files already in --cache-dir",
  )
  args = ap.parse_args()

  folder_id = args.folder_id.strip() or extract_folder_id(args.folder_url)
  cache = Path(args.cache_dir)
  # Isolate per folder id so re-runs don't mix series
  dest = cache / folder_id

  if args.skip_download:
    if not dest.is_dir():
      raise SystemExit(f"--skip-download but cache missing: {dest}")
    print(f"Using cached folder {dest}")
  else:
    download_drive_folder(folder_id, dest)

  files = select_theme_md_files(dest)
  if not files:
    raise SystemExit(f"No Telugu theme .md files found under {dest}")

  print("Selected Telugu theme files:")
  for path in files:
    print(f"  · {path.name}")

  create_section = False if args.no_create_section else True
  return import_theme_files(
    files,
    month=args.month,
    heading_needle=args.heading_needle,
    set_heading=args.set_heading,
    create_section=create_section,
    base_url=args.base_url,
    email=args.email,
    password=args.password,
    dry_run=args.dry_run,
    replace_existing=args.replace_existing,
  )


if __name__ == "__main__":
  sys.exit(main())
