#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import Sec 7 — Upcoming Programs (Nov 2026) into Issue → upcoming.

Wipes existing eventItems. Creates the upcoming section if missing.

  python scripts/import_upcoming_programs_doc.py --month 2026-11
  python scripts/import_upcoming_programs_doc.py --month 2026-11 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from import_jnanodayam_reading import login  # noqa: E402
from import_theme_readmore import find_issue, http_json  # noqa: E402

TE_PENDING = "తెలుగు అనువాదం త్వరలో."

HEADING_EN = "Upcoming Events & Announcements"
HEADING_TE = "రాబోయే ఆధ్యాత్మిక కార్యక్రమాలు – ప్రకటనలు"

# Section intro → bodyEn (above the event cards)
BODY_EN = """November brings a wonderful mix of learning, celebration, self-exploration and service to the QLU community. Whether you wish to deepen your spiritual understanding, explore patterns that may be influencing your life, or reconnect with nature and the community, there is an opportunity waiting for you.

Here is what's coming up this month!"""

EVENTS: list[dict] = [
  {
    "when": "November 2026",
    "titleEn": "Make November a Month of Discovery",
    "titleTe": TE_PENDING,
    "venueEn": "",
    "venueTe": "",
    "detailsEn": (
      "Whether it is a new insight, a deeper connection or a step towards inner "
      "transformation, let this November be an opportunity to participate, "
      "explore and grow.\n\n"
      "Explore the programmes, find what resonates with you and reserve your place!"
    ),
    "detailsTe": TE_PENDING,
    "fullStoryEn": "",
    "fullStoryTe": "",
  },
  {
    "when": "14–24 November 2026",
    "titleEn": "Soul Coach Training Program | Telugu",
    "titleTe": TE_PENDING,
    "venueEn": "Telugu",
    "venueTe": TE_PENDING,
    "detailsEn": (
      "Ready to explore the deeper dimensions of spiritual science and "
      "transformation? The Telugu Soul Coach Training Program offers an "
      "immersive opportunity to learn, experience and deepen your understanding "
      "of the principles and practices of soul coaching. A journey of "
      "self-exploration that can open new perspectives on life and inner growth."
    ),
    "detailsTe": TE_PENDING,
    "fullStoryEn": "",
    "fullStoryTe": "",
  },
  {
    "when": "24 November 2026",
    "titleEn": "Brahma Jnana Diwas | Celebrating Wisdom and Gratitude",
    "titleTe": TE_PENDING,
    "venueEn": "QLU Campus, Vikarabad",
    "venueTe": TE_PENDING,
    "detailsEn": (
      "A special day for the QLU family! Brahma Jnana Diwas celebrates the light "
      "of wisdom on the annual day of Quantum Life University and the birthday "
      "of its Founder and Chairman, Dr. Newton Kondaveti.\n\n"
      "Join the QLU community in Vikarabad for a morning of celebration, "
      "gratitude and togetherness as we honour the vision and journey of QLU."
    ),
    "detailsTe": TE_PENDING,
    "fullStoryEn": "",
    "fullStoryTe": "",
  },
  {
    "when": "21–22 November 2026",
    "titleEn": "Family Constellation and Transgenerational Healing",
    "titleTe": TE_PENDING,
    "venueEn": "Delhi",
    "venueTe": TE_PENDING,
    "detailsEn": (
      "Could some of the patterns you experience today have roots in your family "
      "history? This workshop invites you to explore the influence of ancestral "
      "patterns and family dynamics on your present-day life. An opportunity to "
      "bring greater awareness to inherited patterns, deepen self-understanding "
      "and embrace life with a fresh perspective."
    ),
    "detailsTe": TE_PENDING,
    "fullStoryEn": "",
    "fullStoryTe": "",
  },
  {
    "when": "21–22 November 2026",
    "titleEn": "Vanya Maitreya | As Above, So Below",
    "titleTe": TE_PENDING,
    "venueEn": "QLU Campus, Vikarabad",
    "venueTe": TE_PENDING,
    "detailsEn": (
      "What is reflected within us, and what is reflected in the world around "
      "us? This month's Vanya Maitreya theme, As Above, So Below, invites "
      "participants to explore this fascinating connection through a weekend of "
      "yoga, Dhyana Yogam, Jnana Yogam and Seva Yogam.\n\n"
      "A free residential weekend programme, Vanya Maitreya brings together "
      "meditation, wisdom sharing, Vruksha Seva, GoSeva and Annadaana. Come "
      "experience the joy of learning, serving and growing together."
    ),
    "detailsTe": TE_PENDING,
    "fullStoryEn": "",
    "fullStoryTe": "",
  },
]


def ensure_upcoming_section(sections: list[dict]) -> tuple[int, dict]:
  for i, s in enumerate(sections):
    if s.get("key") == "upcoming":
      return i, s
  new = {
    "key": "upcoming",
    "headingEn": HEADING_EN,
    "headingTe": HEADING_TE,
    "asCard": True,
    "eventItems": [],
    "bodyEn": "",
    "bodyTe": "",
  }
  # Prefer after campus / visits; else append
  insert_at = len(sections)
  order_after = ("campus", "vanya", "visits", "experiences", "highlight-classes", "themes")
  for key in order_after:
    for i, s in enumerate(sections):
      if s.get("key") == key:
        insert_at = i + 1
        break
    else:
      continue
    break
  sections.insert(insert_at, new)
  return insert_at, new


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--month", default="2026-11")
  ap.add_argument("--base", default=os.environ.get("PAYLOAD_URL", "http://localhost:3000"))
  ap.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL", "admin@qlu.local"))
  ap.add_argument(
    "--password",
    default=os.environ.get("SEED_ADMIN_PASSWORD", "qlu-admin-change-me"),
  )
  ap.add_argument("--dry-run", action="store_true")
  args = ap.parse_args()

  base = args.base.rstrip("/")
  token = login(base, args.email, args.password)
  issue = find_issue(base, args.month, token)
  issue_id = issue.get("id")
  sections = list(issue.get("sections") or [])

  print(f"Issue {args.month} id={issue_id}; sections={len(sections)}")
  print(f"  keys={[s.get('key') for s in sections]}")

  idx, upcoming = ensure_upcoming_section(sections)
  old_n = len(upcoming.get("eventItems") or [])
  rows = [{**e, "storyUrl": ""} for e in EVENTS]
  print(f"upcoming index={idx}; wipe {old_n} → {len(rows)} events")
  for r in rows:
    print(f"  • {r['when']} — {r['titleEn'][:56]}")

  upcoming = dict(upcoming)
  upcoming.update(
    {
      "headingEn": HEADING_EN,
      "headingTe": upcoming.get("headingTe") or HEADING_TE,
      "asCard": True,
      "bodyEn": BODY_EN,
      "bodyTe": TE_PENDING,
      "eventItems": rows,
      "images": [],
    }
  )
  sections[idx] = upcoming

  drop = [i for i, s in enumerate(sections) if s.get("key") == "upcoming" and i != idx]
  for i in sorted(drop, reverse=True):
    print(f"  removing extra upcoming index={i}")
    sections.pop(i)

  if args.dry_run:
    print("[dry-run] skip PATCH")
    print("--- bodyEn ---")
    print(BODY_EN[:280], "…")
    return 0

  http_json(
    "PATCH",
    f"{base}/api/issues/{issue_id}",
    token=token,
    body={"sections": sections},
  )
  print("Done. Upcoming Programs imported.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
