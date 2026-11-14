#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Download theme frame images from a shared Google Drive folder and attach them
to QLU News Issue → Themes → themeItems.image + themeItems.images gallery.

All frames that match a theme (video id / day / title) are attached. The primary
card image is chosen with --pick (first|last|largest).

Requires: pip install gdown  (listed in requirements.txt)

Example:

  python scripts/import_theme_images_gdrive.py --dry-run

  python scripts/import_theme_images_gdrive.py ^
    --folder-url "https://drive.google.com/drive/folders/1lWK1kKW5eb1Zy3ZOfxjKJYWTMC4-cQLX" ^
    --month 2026-11 ^
    --heading-needle "నవరాత్ర"

Auth (same as import_theme_readmore.py):
  PAYLOAD_URL, SEED_ADMIN_EMAIL, SEED_ADMIN_PASSWORD
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from import_theme_images import (  # noqa: E402
  DEFAULT_HEADING_NEEDLE,
  collect_image_files,
  import_theme_images,
)
from import_theme_readmore_gdrive import (  # noqa: E402
  download_drive_folder,
  extract_folder_id,
)

# Devi Navratri pack (markdown + stills) — override with --folder-url as needed
DEFAULT_FOLDER_URL = (
  "https://drive.google.com/drive/folders/1lWK1kKW5eb1Zy3ZOfxjKJYWTMC4-cQLX"
)


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
    default=str(ROOT / "out" / "gdrive-theme-images"),
    help="Local download/cache directory",
  )
  ap.add_argument("--month", default="2026-11", help="Issue month YYYY-MM")
  ap.add_argument(
    "--heading-needle",
    default=DEFAULT_HEADING_NEEDLE,
    help="Match themes section heading (substring)",
  )
  ap.add_argument("--base-url", default=os.environ.get("PAYLOAD_URL", "http://localhost:3000"))
  ap.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL", "admin@qlu.local"))
  ap.add_argument(
    "--password",
    default=os.environ.get("SEED_ADMIN_PASSWORD", "qlu-admin-change-me"),
  )
  ap.add_argument("--dry-run", action="store_true", help="Download + plan only; no upload/PATCH")
  ap.add_argument(
    "--replace-existing",
    action="store_true",
    help="Replace theme item galleries instead of merging",
  )
  ap.add_argument(
    "--pick",
    choices=("first", "last", "largest"),
    default="first",
    help="Which matched frame becomes the primary card image (default: earliest timestamp)",
  )
  ap.add_argument(
    "--skip-download",
    action="store_true",
    help="Reuse files already in --cache-dir",
  )
  args = ap.parse_args()

  folder_id = args.folder_id.strip() or extract_folder_id(args.folder_url)
  cache = Path(args.cache_dir)
  dest = cache / folder_id

  if args.skip_download:
    if not dest.is_dir():
      raise SystemExit(f"--skip-download but cache missing: {dest}")
    print(f"Using cached folder {dest}")
  else:
    download_drive_folder(folder_id, dest)

  files = collect_image_files(dest)
  if not files:
    raise SystemExit(f"No image files found under {dest}")

  print(f"Selected image files ({len(files)}):")
  for path in files:
    print(f"  · {path.name}")

  return import_theme_images(
    files,
    month=args.month,
    heading_needle=args.heading_needle,
    base_url=args.base_url,
    email=args.email,
    password=args.password,
    dry_run=args.dry_run,
    replace_existing=args.replace_existing,
    pick=args.pick,
  )


if __name__ == "__main__":
  sys.exit(main())
