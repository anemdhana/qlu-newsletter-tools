#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Replace Issue Highlight Classes from Sec 2 editorial doc (wipe existing + images).

  python scripts/import_highlight_classes_doc.py --month 2026-11
  python scripts/import_highlight_classes_doc.py --month 2026-11 --dry-run
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
SPEAKER = "Dr. Newton Kondaveti"

HEADING_EN = "Featured Classes & Insights"
HEADING_TE = "ఈ నెల విశిష్ట తరగతులు – జ్ఞానాంశాలు"

# Section teaser from the doc (→ leadEn)
LEAD_EN = (
  "During Devi Navratri, Brahmarshi Chakravarthy Dr. Newton Kondaveti led a "
  "special series of nine classes exploring the deeper spiritual significance "
  "of the festival. Moving beyond rituals and traditions, the sessions invited "
  "participants to understand Shakti and consciousness, recognise the Deva and "
  "Asura tendencies within, and explore the symbolism hidden in the stories of "
  "the Divine Mother. Through meditation, self-inquiry and surrender, each "
  "class offered an opportunity to turn inward and discover how the wisdom of "
  "Navratri can become a living part of everyday life."
)

NAVRATRI_INSIGHT = (
  "Navratri is often celebrated through devotion, rituals, music and "
  "festivities — but what lies beneath these traditions? Across nine classes, "
  "Dr. Newton Kondaveti invited participants to look beyond outward celebration "
  "and explore the spiritual wisdom woven into the festival.\n\n"
  "Through Purana stories, yogic concepts and practical reflections, the series "
  "unfolded as a journey of inner awareness, transformation and surrender — "
  "from understanding Shakti and consciousness, to recognising Deva and Asura "
  "tendencies within, to carrying that wisdom into everyday living."
)

NAVRATRI_FULL = """Navratri is often celebrated through devotion, rituals, music and festivities. But what lies beneath these traditions? During the nine days of Devi Navratri, Brahmarshi Chakravarthy Dr. Newton Kondaveti invited participants to look beyond the external celebrations and explore the spiritual wisdom woven into the festival. Through stories from the Puranas, yogic concepts and practical reflections, the sessions unfolded as a journey of inner awareness, transformation and surrender.

## From Festival to Inner Practice

The opening classes explored why festivals carry a deeper purpose. Dr. Newton reflected on Bathukamma, the symbolism of the Divine Mother and the principle of creation, sustenance and dissolution. Even the immersion of a deity's form was presented as a reminder that all forms eventually dissolve, inviting us to reflect on the gradual dissolution of the ego and our limited sense of "I" and "mine".

The significance of the nine nights was also explored as an opportunity for inward practice. Rather than allowing our energy to remain scattered through everyday distractions, participants were encouraged to direct their attention inward through meditation and self-inquiry.

## Understanding Shakti and Consciousness

A central thread throughout the series was the relationship between Shakti and Chaitanya, energy and consciousness. Dr. Newton explained how the Divine Mother is represented through different forms, including Durga, Lakshmi, Saraswati and Kali, while emphasising that these forms point towards the same underlying energy.

He also distinguished between enjoyment and celebration. Enjoyment often depends on fulfilling a desire, whereas true celebration arises from within and does not depend on external circumstances. The nine days were presented as an opportunity to experience this inner joy through meditation, service and Self-knowledge.

An important practice introduced during the sessions was Devi Samarpana, surrender to the Divine Mother. Participants were encouraged to offer their ego, difficulties and aspirations with humility, while recognising the presence of Jaganmata in themselves, other people and nature. Total Acceptance was another key practice: accepting ourselves, others and our present circumstances without giving up the possibility of growth.

## The Deva and Asura Within Us

The classes then turned to the symbolic meaning of the devas and asuras. Rather than viewing them only as characters in Puranic stories, Dr. Newton invited participants to recognise them as tendencies within human beings. Harmony, clarity and awareness reflect our divine nature, while anger, pride, possessiveness and excessive desire can create inner discord.

The three gunas — Tamas, Rajas and Sattva — were discussed in this context. Participants were encouraged to observe which qualities influence their thoughts and actions and consciously cultivate greater balance, clarity and service.

The three stages of Navratri were connected to three forms of Shakti: Mahadurga, representing the will to overcome obstacles; Mahalakshmi, nurturing positive qualities and inner resources; and Mahasaraswati, guiding the seeker towards discernment and Self-knowledge. Together, they represent a progression from overcoming limitations to developing noble qualities and awakening wisdom.

## Discovering the Stories Within the Stories

Several sessions explored the deeper meanings of stories from the Devi Mahatmyam. The story of Rambha and Karambha, for instance, was used to examine the two currents within us: worldly desires and the longing for liberation. Dr. Newton encouraged participants not to suppress desires blindly, but to understand what lies beneath them and recognise the habits and impressions that continue to influence our responses.

The six emissaries of Mahishasura were connected with six inner adversaries: Kama (desire), Krodha (anger), Lobha (greed), Moha (attachment), Mada (pride) and Matsarya (jealousy). The story of Mahishasuramardini was explored as a symbolic account of overcoming these tendencies through awareness and spiritual practice.

The later classes examined Shumbha, Nishumbha and other asuras as representations of attachment to pleasure, aversion to pain, self-deception and the multiplying nature of ego. The sword of the Divine Mother became a symbol of wisdom and discernment, reminding participants that the real battle is within.

## Wisdom in Everyday Living

As the series progressed, the teachings extended beyond meditation and mythology into everyday conduct. Participants were encouraged to recognise nature as an expression of the Divine Mother and to reflect on whether their actions truly demonstrated respect for the Earth and other living beings.

Dr. Newton also highlighted the lasting impact of words through the story of a father who asked his angry son to hammer nails into a wall whenever he lost his temper. Although the nails could later be removed, the holes remained. The story offered a simple reminder that words spoken in anger can leave lasting impressions, making awareness and compassion in communication essential.

The final class brought together the relationship between Shakti, consciousness and Jnana, or wisdom. It explored the importance of directing the energy gathered through spiritual practice towards a higher purpose. The distinction between Jnana Siddhi, the realisation of wisdom, and Karya Siddhi, accomplishment in the world, highlighted that inner growth and meaningful action need not be separate.

## A Journey Beyond the Nine Days

Across the nine classes, one message remained constant: the deeper purpose of Navratri is not simply to celebrate the Divine Mother, but to recognise and experience the principles she represents within ourselves and throughout creation.

Through meditation, self-inquiry, surrender and conscious action, the festival becomes more than an annual observance. It becomes an invitation to transform the way we think, relate, speak and live, carrying the wisdom of these nine days into every day that follows."""

# First Navratri live (Day 1 of series list in the doc)
NAVRATRI_FIRST_URL = "https://www.youtube.com/live/zkXnkP0fIfA"
NAVRATRI_URLS = [
  "https://www.youtube.com/live/zkXnkP0fIfA",
  "https://www.youtube.com/live/dmLVPT3065I",
  "https://www.youtube.com/live/CgTrk319L1Q",
  "https://www.youtube.com/live/ErG8OR7pEak",
  "https://www.youtube.com/live/-PBG5i5WFyw",
  "https://www.youtube.com/live/NdVSw_huiNw",
  "https://www.youtube.com/live/TlWBXJ5zkfs",
  "https://www.youtube.com/live/RQxRUgDjGDI",
  "https://www.youtube.com/live/NbcWpRxBPaQ",
]

CLASSES: list[dict] = [
  {
    "titleEn": "Sri Krishna Janmashtami Special with Dr. Newton Kondaveti",
    "titleTe": "శ్రీ కృష్ణ జన్మాష్టమి ప్రత్యేక సమావేశం",
    "day": 524,
    "storyUrl": "https://www.youtube.com/live/Uu88QpHpXgE",
    "insightEn": (
      "A special Jnanodayam episode for Sri Krishna Janmashtami with "
      "Dr. Newton Kondaveti."
    ),
    "fullStoryEn": "",
  },
  {
    "titleEn": "Special Episode on Vinayaka Chavithi with Dr. Newton Kondaveti",
    "titleTe": "వినాయక చవితి ప్రత్యేక సమావేశం",
    "day": 534,
    "storyUrl": "https://www.youtube.com/live/9huEkbQEwzA",
    "insightEn": (
      "A Vinayaka Chavithi special exploring Ganesha's wisdom with "
      "Dr. Newton Kondaveti."
    ),
    "fullStoryEn": "",
  },
  {
    "titleEn": "Special Meditation with Dr. Newton Kondaveti — Day 546",
    "titleTe": "ప్రత్యేక ధ్యాన సమావేశం — రోజు 546",
    "day": 546,
    "storyUrl": "https://www.youtube.com/live/exQQl_XyLRM",
    "insightEn": (
      "A special meditation session with Dr. Newton Kondaveti, Founder & "
      "Chairman, Quantum Life University."
    ),
    "fullStoryEn": "",
  },
  {
    "titleEn": "Special Meditation with Dr. Newton Kondaveti — Day 547",
    "titleTe": "ప్రత్యేక ధ్యాన సమావేశం — రోజు 547",
    "day": 547,
    "storyUrl": "https://www.youtube.com/live/jQhvBrq5DnE",
    "insightEn": (
      "A continued special meditation session with Dr. Newton Kondaveti, "
      "Founder & Chairman, Quantum Life University."
    ),
    "fullStoryEn": "",
  },
  {
    "titleEn": "The Wisdom of Devi Navratri: Nine Days of Inner Awakening",
    "titleTe": "దేవీ నవరాత్రి జ్ఞానం: అంతర జాగృతి తొమ్మిది రోజులు",
    "day": None,
    "date": "9 Days",
    "storyUrl": NAVRATRI_FIRST_URL,
    "insightEn": NAVRATRI_INSIGHT,
    "fullStoryEn": NAVRATRI_FULL
    + "\n\n### Session links\n\n"
    + "\n".join(f"- [Day {i + 1}]({u})" for i, u in enumerate(NAVRATRI_URLS)),
  },
  {
    "titleEn": "Vijaya Dashami Episode with Dr. Newton Kondaveti",
    "titleTe": "విజయదశమి ప్రత్యేక సమావేశం",
    "day": None,
    "date": "Vijaya Dashami",
    "storyUrl": "https://www.youtube.com/live/v5fVqCcscOk",
    "insightEn": (
      "A Vijaya Dashami special with Dr. Newton Kondaveti, completing the "
      "Navratri journey of inner victory."
    ),
    "fullStoryEn": "",
  },
]


def word_count(text: str) -> int:
  return len((text or "").split())


def build_rows() -> list[dict]:
  rows: list[dict] = []
  for c in CLASSES:
    row = {
      "titleEn": c["titleEn"],
      "titleTe": c["titleTe"],
      "speaker": SPEAKER,
      "insightEn": c["insightEn"],
      "insightTe": TE_PENDING,
      "fullStoryEn": c.get("fullStoryEn") or "",
      "fullStoryTe": TE_PENDING if c.get("fullStoryEn") else "",
      "storyUrl": c.get("storyUrl") or "",
      "image": None,
      "date": c.get("date") or "",
    }
    if c.get("day") is not None:
      row["jnanodayamDay"] = c["day"]
    print(
      f"  {(c['titleEn'])[:54]}… day={c.get('day')} "
      f"insight={word_count(c['insightEn'])}w "
      f"full={word_count(c.get('fullStoryEn') or '')}w"
    )
    rows.append(row)
  return rows


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

  idxs = [i for i, s in enumerate(sections) if s.get("key") == "highlight-classes"]
  if not idxs:
    raise SystemExit("No highlight-classes section on issue")

  print(f"Issue {args.month} id={issue_id}")
  print(f"Existing class sections: {len(idxs)}; wiping classItems + images")
  print(f"leadEn words: {word_count(LEAD_EN)}")
  rows = build_rows()

  primary = idxs[0]
  sec = dict(sections[primary])
  old_n = len(sec.get("classItems") or [])
  sec.update(
    {
      "headingEn": HEADING_EN,
      "headingTe": sec.get("headingTe") or HEADING_TE,
      "leadEn": LEAD_EN,
      "leadTe": TE_PENDING,
      "asCard": True,
      "classItems": rows,
      "images": [],
    }
  )
  sections[primary] = sec

  for i in sorted(idxs[1:], reverse=True):
    print(f"  removing extra highlight-classes index={i}")
    sections.pop(i)

  if args.dry_run:
    print(f"[dry-run] would replace {old_n} → {len(rows)} class cards")
    return 0

  http_json(
    "PATCH",
    f"{base}/api/issues/{issue_id}",
    token=token,
    body={"sections": sections},
  )
  print(f"Done. Highlight classes {old_n} → {len(rows)} cards (no images).")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
