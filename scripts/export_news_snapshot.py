#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Snapshot the live Astro News reader (HTML + qlu.css + images + drawer JS)
into docs/ so GitHub Pages matches http://localhost:4321/issues/{month}/{lang}/

Example (Astro + CMS must be running):

  python scripts/export_news_snapshot.py --month 2026-11
  python scripts/export_news_snapshot.py --month 2026-11 --lang te
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from export_print_snapshot import main as snapshot_main  # noqa: E402


def main() -> int:
  return snapshot_main(sys.argv[1:], default_view="news")


if __name__ == "__main__":
  sys.exit(main())
