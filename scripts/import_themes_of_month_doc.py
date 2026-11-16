#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Replace Issue Themes with Sep–Oct 2026 series summaries from the editorial doc.

- Section leadEn  ← short teaser (not per-card blurb)
- themeItems      ← 6 series cards (EN blurbs trimmed ≈160–180 words;
                    fullStoryEn = full series write-up)
- TE fields kept from matched existing cards; new cards get TE placeholder
- Images / IDs reused when title keywords match

  python scripts/import_themes_of_month_doc.py --month 2026-11
  python scripts/import_themes_of_month_doc.py --month 2026-11 --dry-run
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

LEAD_EN = (
  "From the wisdom of Sri Krishna and the deeper significance of Sri Ganesha's "
  "forms to the art of peaceful communication, the spiritual meaning of Navratri, "
  "and reflections on death and the afterlife, this month offered many "
  "opportunities to look beyond the surface.\n\n"
  "Through stories, teachings and self-inquiry, we were invited to explore the "
  "wisdom hidden in our traditions and discover how it can transform the way we "
  "think, relate, and live."
)

HEADING_EN = "Themes That Resonated Through the Month"
HEADING_TE = "ఈ నెల ప్రతిధ్వనించిన థీమ్‌లు"

# Blurbs trimmed to ~160–180 words where needed; fullStory keeps the editorial text.
THEMES: list[dict] = [
  {
    "key": "krishna",
    "match": ("krishna", "కృష్ణ"),
    "titleEn": "Sri Krishna Series: Looking Beyond the Story",
    "titleTe": "శ్రీ కృష్ణ శ్రేణి: కథను దాటి",
    "playlist": "https://www.youtube.com/playlist?list=PLfZnHCOJdkFQ",
    "blurbEn": (
      "The teachings around Sri Krishna invited us to explore the deeper wisdom "
      "in the Bhagavatam and the Bhagavad Gita. Rather than treating these "
      "narratives only as Purana events, we looked for the spiritual principles "
      "they represent.\n\n"
      "Krishna's birth and the appearance of Mahamaya opened reflection on the "
      "Divine Mother's presence and the creative power that pervades existence. "
      "Traditions such as Bathukamma were also explored as ways to recognise and "
      "celebrate the life we have been given.\n\n"
      "The story of the Pandavas carrying a pumpkin on pilgrimage at Krishna's "
      "request made the point simply: sacred travel alone does not transform us. "
      "The real pilgrimage is inward — through meditation, awareness, and "
      "practice. These teachings ask us to examine our own lives and live with "
      "greater awareness."
    ),
    "fullStoryEn": (
      "The teachings around Sri Krishna invited us to explore the deeper wisdom "
      "contained in the stories of the Bhagavatam and the Bhagavad Gita. Rather "
      "than viewing these narratives merely as events from the Puranas, we were "
      "encouraged to look for the spiritual principles and insights they "
      "represent.\n\n"
      "The account of Sri Krishna's birth and the appearance of Mahamaya opened "
      "a reflection on the Divine Mother's presence and the creative power that "
      "pervades existence. The discussion also explored the deeper significance "
      "of traditions such as Bathukamma, inviting us to recognise and celebrate "
      "the life and creative energy that we have been given.\n\n"
      "Another memorable teaching used the story of the Pandavas taking a "
      "pumpkin on their pilgrimage at Sri Krishna's request. Despite being "
      "carried to sacred places and immersed in holy waters, the pumpkin "
      "remained unchanged. The message was simple yet profound: travelling to "
      "sacred places does not automatically transform us. The real pilgrimage "
      "must happen within, through meditation, awareness and inner practice.\n\n"
      "These teachings reminded us that the wisdom of Sri Krishna is not limited "
      "to stories or scriptures. It invites us to examine our own lives and "
      "bring greater awareness to the way we live."
    ),
  },
  {
    "key": "ganesha",
    "match": ("ganesha", "ganapati", "గణేశ"),
    "titleEn": "Sri Ganesha Series: Discovering the Tattva Within",
    "titleTe": "శ్రీ గణేశ శ్రేణి: అంతర్గత తత్త్వం",
    "playlist": "https://www.youtube.com/playlist?list=PLRfMqghM5qNw",
    "blurbEn": (
      "The Sri Ganesha series moved beyond familiar avatar stories to the deeper "
      "tattva they represent. Drawing mainly from the Mudgala Purana, the "
      "sessions showed that the asuras can also mirror tendencies in our own "
      "minds.\n\n"
      "The eight avatars were linked with jealousy, pride, delusion, greed, "
      "anger, desire, possessiveness, and ego — and with the qualities that "
      "transform them: humility, contentment, generosity, discernment, and "
      "universal love. Ganesha's mouse pointed to the restless mind chasing "
      "distraction and attachment.\n\n"
      "Obstacles were reframed as chances to pause and see what needs to change "
      "within. Understanding Ganesha Tattva is not only knowing the stories; it "
      "is awakening the wisdom, humility, and awareness they point toward."
    ),
    "fullStoryEn": (
      "The Sri Ganesha series took us beyond the familiar stories of Ganesha's "
      "avatars to explore the deeper tattva, or spiritual principles, "
      "represented by them. Drawing primarily from the Mudgala Purana, the "
      "sessions encouraged us to recognise that the asuras and their stories can "
      "also represent tendencies within our own minds.\n\n"
      "The eight avatars were connected with qualities such as jealousy, pride, "
      "delusion, greed, anger, desire, possessiveness and ego. Each story offered "
      "an opportunity to understand how these tendencies influence our thoughts "
      "and actions, and how they can be transformed into qualities such as "
      "humility, contentment, generosity, discernment and universal love.\n\n"
      "We also explored the symbolism behind Ganesha's form, including the mouse "
      "as a representation of the restless mind and its tendency to run after "
      "distractions and attachments. The deeper message was to develop awareness "
      "and mastery over these tendencies rather than remain governed by them.\n\n"
      "The teachings also invited us to look differently at obstacles. A "
      "difficulty in life need not always be seen as something to resist or "
      "remove immediately. It can become an opportunity to pause, examine "
      "ourselves and recognise what needs to change within us.\n\n"
      "Ultimately, the series reminded us that understanding Ganesha Tattva is "
      "not merely about knowing the stories or worshipping the forms. It is "
      "about awakening the wisdom, humility and awareness that they point towards."
    ),
  },
  {
    "key": "speak_peace",
    "match": ("speak peace", "శాంతి", "nvc"),
    "titleEn": "Speak Peace Series: Transforming Relationships Through Understanding",
    "titleTe": "స్పీక్ పీస్ శ్రేణి: అవగాహనతో సంబంధాలు",
    "playlist": "https://www.youtube.com/playlist?list=PLXFH6NabgD9o",
    "blurbEn": (
      "Based on Marshall Rosenberg's Speak Peace in a World of Conflict and "
      "Nonviolent Communication (NVC), this series brought spiritual awareness "
      "into everyday speech. Conflict often rises not only from words, but from "
      "feelings, judgments, and unmet needs behind them.\n\n"
      "We worked with NVC's four elements — observation, feelings, needs, and "
      "requests — to separate what happened from our interpretations, and to "
      "respond with clarity and empathy. Peaceful communication is not mere "
      "politeness; it begins by noticing our own inner state before we answer.\n\n"
      "Gratitude, self-empathy, and recognising others' efforts were also "
      "central. The invitation was to make understanding and compassion a way of "
      "life in our relationships — including how we speak to ourselves."
    ),
    "fullStoryEn": (
      "The Speak Peace series, based on Marshall Rosenberg's Speak Peace in a "
      "World of Conflict and the principles of Nonviolent Communication (NVC), "
      "brought spiritual awareness into one of the most familiar aspects of our "
      "lives: the way we communicate with one another.\n\n"
      "The sessions explored how conflict often arises not simply from what is "
      "said, but from the feelings, judgments and unmet needs behind our words. "
      "We were introduced to the four key elements of NVC: observation, "
      "feelings, needs and requests. By learning to distinguish what actually "
      "happened from our interpretations of it, we can begin to communicate with "
      "greater clarity and empathy.\n\n"
      "An important insight was that peaceful communication is not simply about "
      "choosing polite words. It begins with observing our own inner state. When "
      "anger, hurt or disappointment arises, can we pause and understand what we "
      "are feeling before responding? Can we listen to another person's needs "
      "instead of immediately trying to defend our position or change their "
      "behaviour?\n\n"
      "The series also explored gratitude, self-empathy and the importance of "
      "recognising the efforts and contributions of others. We were reminded that "
      "the way we speak to ourselves matters too. Taking responsibility for a "
      "mistake does not require harsh self-judgment; it requires understanding, "
      "acceptance and a willingness to respond differently.\n\n"
      "The larger invitation was to make peaceful communication a way of life, "
      "allowing understanding and compassion to find expression in our everyday "
      "relationships."
    ),
  },
  {
    "key": "death",
    "match": ("death", "afterlife", "nachiketa", "మరణ"),
    "titleEn": "Death and Afterlife: Looking Beyond the Physical",
    "titleTe": "మరణం మరియు పరలోకం: శరీరాన్ని దాటి",
    "playlist": "https://www.youtube.com/playlist?list=PLTAPemtsgTSw",
    "blurbEn": (
      "These reflections asked one of life's deepest questions: What are we "
      "beyond the physical body?\n\n"
      "Through Nachiketa's meeting with Yama, the teachings distinguished the "
      "temporary from the eternal. Nachiketa's refusal of worldly comforts in "
      "favor of Self-knowledge became a model for seeking lasting wisdom over "
      "short-lived gratification.\n\n"
      "The sessions also introduced gross, subtle, and causal dimensions of "
      "existence, inviting us past identification with body, thoughts, and "
      "emotions. Rather than meeting death only with fear, we were asked to "
      "inquire into consciousness and the Self that remains amid change."
    ),
    "fullStoryEn": (
      "The reflections on death and the afterlife invited us to contemplate one "
      "of life's most profound questions: What are we beyond the physical body?\n\n"
      "Drawing on the story of Nachiketa and his encounter with Yama, the "
      "teachings explored the distinction between what is temporary and what is "
      "eternal. Nachiketa's unwavering desire to understand the nature of the "
      "Self, even when offered worldly comforts and pleasures, became an example "
      "of the importance of seeking lasting wisdom over temporary "
      "gratification.\n\n"
      "The discussions also introduced the gross, subtle and causal dimensions "
      "of existence, encouraging us to look beyond our identification with the "
      "physical body, thoughts and emotions. We were invited to reflect on the "
      "nature of consciousness and the possibility of recognising the Self as "
      "something beyond the changing experiences of life.\n\n"
      "Rather than approaching death only through fear or uncertainty, these "
      "teachings encouraged deeper inquiry into our true nature and the "
      "importance of self-knowledge."
    ),
  },
  {
    "key": "navaratri",
    "match": ("navratri", "navaratri", "devi", "దేవీ", "నవరాత్ర"),
    "titleEn": "Navratri: From Celebration to Inner Transformation",
    "titleTe": "నవరాత్రి: ఉత్సవం నుంచి అంతర పరివర్తన వరకు",
    "playlist": "https://www.youtube.com/playlist?list=PLY8cw6DnA5GI",
    "blurbEn": (
      "The Navratri sessions looked past outward celebration to the spiritual "
      "meaning of the nine days — Shakti and consciousness, the Divine Mother's "
      "energy, surrender, and the awakening of wisdom within.\n\n"
      "Stories from the Devi Mahatmya treated asuras as inner tendencies: "
      "desire, anger, jealousy, attachment, pride, and ego. The Mother's battles "
      "became a map of the inner work needed to outgrow our limits.\n\n"
      "The nine days also framed iccha, kriya, and jnana shakti — will, action, "
      "and wisdom — moving from purifying tendencies toward discernment and "
      "deeper awareness. Navratri is not only an outer festival; it is time for "
      "meditation, practice, and meeting the Divine within."
    ),
    "fullStoryEn": (
      "The Navratri sessions invited us to look beyond the outward celebrations "
      "and rituals to understand the spiritual significance of the nine days. "
      "The teachings explored Shakti and consciousness, the Divine Mother's "
      "energy, surrender and the awakening of wisdom within.\n\n"
      "Through stories from the Devi Mahatmya, the various asuras were examined "
      "as representations of tendencies that can operate within us, including "
      "desire, anger, jealousy, attachment, pride and ego. The battles between "
      "the Divine Mother and these forces became a way of understanding the "
      "inner work required to overcome our own limitations.\n\n"
      "The nine days also offered a framework for reflecting on the three "
      "fundamental powers: iccha shakti (will), kriya shakti (action) and jnana "
      "shakti (wisdom). The journey moved from recognising and purifying inner "
      "tendencies towards developing discernment, surrender and deeper "
      "awareness.\n\n"
      "An important message was that Navratri is not merely a festival to be "
      "observed externally. It is an opportunity to dedicate ourselves to "
      "meditation and spiritual practice, direct our energy towards "
      "self-knowledge and experience the Divine principles within us."
    ),
  },
  {
    "key": "daily_life",
    "match": ("daily life", "spirituality in daily", "రోజువారీ"),
    "titleEn": "Spirituality in Daily Life",
    "titleTe": "రోజువారీ జీవితంలో ఆధ్యాత్మికత",
    "playlist": "https://www.youtube.com/playlist?list=PLMcnBt93ZLlU",
    "blurbEn": (
      "Across nine Jnanodayam sessions, the presenters explore how the awareness "
      "we cultivate in meditation can guide ordinary choices. When anger or "
      "frustration arises, we can pause, notice what we feel, and choose how to "
      "respond. Walking, drawing, or dancing can give those feelings room and "
      "help us return to a conversation with a fresh perspective.\n\n"
      "The same awareness shapes how we earn and spend money, use our time, and "
      "care for our bodies. We can question beliefs about scarcity and "
      "self-worth, direct attention toward what matters, and support well-being "
      "through nourishment, movement, and rest.\n\n"
      "In relationships, spirituality means meeting real needs, listening "
      "without judgment, and serving without craving recognition. Gratitude "
      "helps us notice what already sustains us. The practice closes inward: "
      "release blame, accept what is present, and take responsibility for how "
      "we respond."
    ),
    "fullStoryEn": (
      "Across nine Jñānodayam sessions, the presenters explore how the awareness "
      "we cultivate in meditation can guide ordinary choices. When anger or "
      "frustration arises, we can pause, notice what we feel, and choose how to "
      "respond. Walking, drawing, or dancing can give those feelings room to be "
      "expressed and help us return to a conversation with a fresh perspective.\n\n"
      "The same awareness shapes how we earn and spend money, use our time, and "
      "care for our bodies. We can question beliefs about scarcity and "
      "self-worth, direct our attention toward what matters, and support our "
      "well-being through nourishment, movement, and rest. Personal growth often "
      "happens quietly, like roots spreading underground, as we take the next "
      "step without seeing the whole path.\n\n"
      "In relationships, spirituality takes the form of meeting another "
      "person's actual needs, listening without judgment, and serving without "
      "expecting recognition. Gratitude helps us notice what already sustains "
      "us, even in difficult circumstances. The series closes by bringing the "
      "practice inward: let go of blame, accept what is present, and take "
      "responsibility for how we respond."
    ),
  },
]


def media_id(value) -> int | str | None:
  if value is None:
    return None
  if isinstance(value, dict):
    return value.get("id")
  return value


def item_blob(item: dict) -> str:
  return " ".join(
    str(item.get(k) or "")
    for k in ("titleEn", "titleTe", "blurbEn", "blurbTe", "storyUrl")
  ).lower()


def match_existing(theme: dict, pool: list[dict]) -> dict | None:
  needles = tuple(n.lower() for n in theme["match"])
  for item in pool:
    blob = item_blob(item)
    if any(n in blob for n in needles):
      return item
  return None


def word_count(text: str) -> int:
  return len((text or "").split())


def build_rows(existing_items: list[dict]) -> list[dict]:
  used: set[int] = set()
  rows: list[dict] = []
  for theme in THEMES:
    old = match_existing(theme, existing_items)
    if old is not None:
      used.add(id(old))

    row: dict = {
      "titleEn": theme["titleEn"],
      "titleTe": (old or {}).get("titleTe") or theme["titleTe"],
      "blurbEn": theme["blurbEn"],
      "blurbTe": (old or {}).get("blurbTe") or TE_PENDING,
      "fullStoryEn": theme["fullStoryEn"],
      "fullStoryTe": (old or {}).get("fullStoryTe") or TE_PENDING,
      "storyUrl": theme["playlist"],
      "images": [],
    }
    if old and old.get("id"):
      row["id"] = old["id"]
    img = media_id((old or {}).get("image"))
    if img is not None:
      row["image"] = img
      # Keep gallery if present
      gallery = []
      for g in (old or {}).get("images") or []:
        gid = media_id(g.get("image") if isinstance(g, dict) else g)
        if gid is not None:
          gallery.append({"image": gid})
      if gallery:
        row["images"] = gallery

    print(
      f"  {theme['key']}: blurb={word_count(theme['blurbEn'])}w "
      f"full={word_count(theme['fullStoryEn'])}w "
      f"reuse_id={row.get('id')} image={row.get('image')} "
      f"te={'kept' if old and (old.get('blurbTe') or '').strip() else 'pending'}"
    )
    rows.append(row)
  return rows


def collect_theme_items(sections: list[dict]) -> tuple[list[int], list[dict]]:
  idxs = [i for i, s in enumerate(sections) if s.get("key") == "themes"]
  items: list[dict] = []
  for i in idxs:
    items.extend(list(sections[i].get("themeItems") or []))
  return idxs, items


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
  theme_idxs, existing = collect_theme_items(sections)
  if not theme_idxs:
    raise SystemExit("No themes section on issue")

  print(f"Issue {args.month} id={issue_id}")
  print(f"Themes sections: {len(theme_idxs)}; existing cards: {len(existing)}")
  print(f"leadEn words: {word_count(LEAD_EN)}")
  rows = build_rows(existing)

  primary = theme_idxs[0]
  themes = dict(sections[primary])
  themes.update(
    {
      "headingEn": HEADING_EN,
      "headingTe": themes.get("headingTe") or HEADING_TE,
      "leadEn": LEAD_EN,
      # Keep existing TE lead until translation arrives
      "leadTe": themes.get("leadTe") or TE_PENDING,
      "asCard": True,
      "themeItems": rows,
    }
  )
  themes.pop("themeItemsNav", None)
  sections[primary] = themes

  # Drop extra themes sections (older per-series sections) so News/Print show one list
  drop = sorted(theme_idxs[1:], reverse=True)
  for i in drop:
    print(f"  removing extra themes section index={i} heading={sections[i].get('headingEn')!r}")
    sections.pop(i)

  if args.dry_run:
    print("[dry-run] skip PATCH")
    print("--- leadEn ---")
    print(LEAD_EN)
    print("--- first blurbEn ---")
    print(rows[0]["blurbEn"][:400])
    return 0

  http_json(
    "PATCH",
    f"{base}/api/issues/{issue_id}",
    token=token,
    body={"sections": sections},
  )
  print(f"Done. Themes → {len(rows)} cards; leadEn = teaser.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
