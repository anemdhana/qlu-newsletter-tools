#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import Sec 4 — Our Founders' Travelogue into Issue → visits (wipe existing).

  python scripts/import_founders_travelogue_doc.py --month 2026-11
  python scripts/import_founders_travelogue_doc.py --month 2026-11 --dry-run
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

HEADING_EN = "Our Founders' Travelogue"
HEADING_TE = "మా వ్యవస్థాపకుల యాత్రా వృత్తాంతం"

NOTE_EN = (
  "A journey to Hyderabad, an unexpected car breakdown and an unplanned cab "
  "ride. What seemed like an inconvenient start to the day soon took an "
  "unexpected turn, bringing together people and circumstances in a way no one "
  "could have anticipated. Along the way, a simple conversation opened the "
  "door to a meaningful connection, reminding us that some of life's most "
  "significant moments are never planned. Join Harika as she recounts this "
  "unexpected journey and the beautiful encounter that gave it a deeper meaning."
)

FULL_STORY_EN = """The morning of 2nd October was bright and pleasant, and we were looking forward to another journey with Dr. Newton and Dr. Lakshmi. Travelling with them is always special. It is the time spent together, the conversations and the many little opportunities to learn along the way that make these journeys so enriching. This time, we were headed to Hyderabad for the Ahimsa Dhyana Yagnam, where Sir and Ma'am were scheduled to conduct a session.

We had driven from Vikarabad to Hyderabad to pick them up. Everything had gone smoothly, and the car had been running perfectly throughout the journey. When we reached to pick up Sir and Ma'am, the sun was beginning to get a little stronger. Just as they settled into the car and we were ready to leave, the vehicle decided to play a little game with us. It simply refused to start.

I remember feeling quite annoyed and, more than anything, apologetic. We had to ensure that Sir and Ma'am reached the venue on time, and here we were, suddenly stranded with no explanation for what had happened. The car had been running perfectly right up until that moment, all the way from Vikarabad. We tried repeatedly, but the car wouldn't respond. It was difficult to understand how a vehicle that had brought us all the way without a hitch could suddenly stop working. It was beginning to get hotter, and our frustration and anxiety were also rising.

Dr. Newton, however, remained remarkably calm. While the rest of us were trying to figure out what had gone wrong, he simply said, "There is a reason for everything. Don't worry. We have our plans, but this has its own plan."

Ultimately, with no other option, we booked a cab so that we could reach the venue on time. I was still annoyed at how a perfectly planned journey could take such an abrupt and uncertain turn.

However, little did we know that this unexpected change of vehicle would bring someone into our lives who was about to experience a change of his own.

## A Conversation We Hadn't Planned

When we got into the cab, the driver, Anand, was already on the phone. He sounded frustrated and deeply troubled by something happening in his life. His voice was raised, and the conversation seemed intense. We had just been through our own unexpected disruption, and the tension in his voice added to the unsettled mood. We exchanged a few quiet words among ourselves, hoping he would finish his calls and that the journey could settle down. I was further annoyed because I felt this was adding to the inconvenience Sir and Ma'am had already experienced after our car broke down.

Whenever we travel with Sir and Ma'am, we try to be quiet, listen and learn from them as they converse, or simply give them their own space. This time, however, we found ourselves listening to something quite different: loud, harsh and angry words being spoken over the phone.

Gradually, Anand's calls ended, and we continued our journey. The air began to grow cooler and more pleasant, and Sir and Ma'am started discussing something about the event. Their calm demeanour, gentle voices and peaceful temperament brought a noticeable shift in the atmosphere inside the car.

It seemed as though Anand, too, was affected by this. Eventually, he turned towards Dr. Newton and asked, "What do you do, sir?" Sir simply replied, "I teach meditation."

And that was how the conversation began.

I was amazed by how the great teachers and masters can remain so humble and how, time and again, they manage to stay connected to their very core. Yet, I couldn't hold back and found myself telling Anand that Sir and Ma'am were the founders of a university in Vikarabad, were great teachers and had travelled to more than 120 countries. I wanted him to know how fortunate we were to be travelling with them and that they were on their way to speak at the very event we were attending.

The word meditation somehow became the link between Anand and us. He told us that one of his cousins was a meditator and an active member of the Pyramid Society. That cousin had been urging Anand to practise meditation, but Anand had never had the opportunity to do so. On learning this, we invited Anand to attend the event, have food and then leave. It was almost noon, and he would be able to listen to Sir and Ma'am's lecture and have lunch before leaving. He initially hesitated but ultimately agreed to stay on.

## When Compassion Finds a Personal Meaning

The Ahimsa Dhyana Yagnam focused on vegetarianism and non-violence. During the programme, Dr. Newton and Dr. Lakshmi conducted a session that invited participants to look at compassion in a deeply personal way. The lecture was amazing and mesmerising, as usual, and towards the end, Ma'am guided everyone through a reflection.

She asked everyone to place their hands on their heart and feel all the animals as their own children. She invited them to consider that an animal's young is just as precious to its mother as our children are to us. The love a parent feels, the instinct to protect, and the pain of imagining its child suffering are not feelings that belong to human beings alone.

After the session concluded, we found Anand standing outside, waiting for us. He insisted on dropping us back at the place where he had picked us up. Then, he spoke his heart out. He said, "I heard your class, and I am very touched. I also have a very young child, about three years old. And you said that animals are like our children, and they are equally important to their mothers and fathers, their family. I could feel how I would feel if my child had pain. And from now on, I will become a vegetarian, and I will also meditate. From today, I will no longer have any non-vegetarian food."

His heartfelt words brought an instant smile to our faces. A person who had joined us almost by chance had found something that resonated with him so deeply that he wanted to make a change in his own life.

## The Higher Plan

Sir and Ma'am rejoiced and appreciated his decision to turn vegetarian. Throughout the journey, they kept telling him how happy they were.

And then Sir said to me, "Harika, now you know? I told you there's a bigger plan, there's a higher plan. The universe always does things for a reason. This is the higher plan. He had to turn vegetarian today. That's why the car did not start, and we had to come by cab. And why only this cab? Why only him?"

His words brought me back to the moment when the car had refused to start. We had been so caught up in the inconvenience, the delay and our responsibility to get Sir and Ma'am to the venue on time that all we could see was a problem that needed to be solved. We had no way of knowing that this unexpected cab ride would bring Anand into an environment where he could listen, reflect and discover something for himself.

No one had planned this encounter or set out that morning to change his mind. It had unfolded through an ordinary conversation, an invitation to attend a session and a reflection that connected with his own experience of love as a parent.

I keep thinking about Anand and the choice he made that day. One person's decision to embrace vegetarianism can mean many lives spared. And when that choice becomes part of a family's way of life, its influence may reach well beyond one individual.

We had set out that morning to take Sir and Ma'am to Hyderabad for a programme on ahimsa. Somewhere along the way, the journey became an experience of ahimsa itself, one that reached a stranger and gave him a reason to look at life differently.

The car had refused to start. But something meaningful had begun."""


def word_count(text: str) -> int:
  return len((text or "").split())


def build_row() -> dict:
  return {
    "titleEn": "When the Universe Has Other Plans",
    "titleTe": TE_PENDING,
    "date": "2 October 2026",
    "place": "Hyderabad · Ahimsa Dhyana Yagnam",
    "byline": "As told by Harika",
    "noteEn": NOTE_EN,
    "noteTe": TE_PENDING,
    "fullStoryEn": FULL_STORY_EN,
    "fullStoryTe": TE_PENDING,
    "storyUrl": "",
  }


def ensure_visits_section(sections: list[dict]) -> tuple[int, dict]:
  for i, s in enumerate(sections):
    if s.get("key") == "visits":
      return i, s
  # Insert after highlight-classes when possible, else append
  new = {
    "key": "visits",
    "headingEn": HEADING_EN,
    "headingTe": HEADING_TE,
    "asCard": True,
    "visitItems": [],
  }
  insert_at = len(sections)
  for i, s in enumerate(sections):
    if s.get("key") == "highlight-classes":
      insert_at = i + 1
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

  idx, visits = ensure_visits_section(sections)
  old_n = len(visits.get("visitItems") or [])
  row = build_row()
  print(
    f"visits index={idx}; wipe {old_n} → 1 card; "
    f"note={word_count(NOTE_EN)}w full={word_count(FULL_STORY_EN)}w"
  )
  print(f"  title: {row['titleEn']}")
  print(f"  date/place: {row['date']} / {row['place']}")
  print(f"  byline: {row['byline']}")

  visits = dict(visits)
  visits.update(
    {
      "headingEn": HEADING_EN,
      "headingTe": visits.get("headingTe") or HEADING_TE,
      "asCard": True,
      "visitItems": [row],
      "images": [],
    }
  )
  sections[idx] = visits

  # Drop duplicate visits sections if any
  drop = [i for i, s in enumerate(sections) if s.get("key") == "visits" and i != idx]
  for i in sorted(drop, reverse=True):
    print(f"  removing extra visits index={i}")
    sections.pop(i)
    if i < idx:
      idx -= 1

  if args.dry_run:
    print("[dry-run] skip PATCH")
    print("--- note ---")
    print(NOTE_EN[:240], "…")
    print("--- fullStory head ---")
    print(FULL_STORY_EN[:320], "…")
    return 0

  http_json(
    "PATCH",
    f"{base}/api/issues/{issue_id}",
    token=token,
    body={"sections": sections},
  )
  print("Done. Founders' Travelogue imported into visits.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
