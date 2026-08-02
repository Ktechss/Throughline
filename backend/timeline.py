"""When a shot happens, and what that implies.

The gate answers "is this still her?". Nothing answered "is this still the same
*life*?" — and a year of images with no time in them is the tell that outlives
any face fix. Every shot was timeless, so the set read as a catalogue of one
woman rather than a record of one year: hair that never grew, weather that never
turned, a manicure that changed at random and therefore meant nothing.

So a run carries a DATE, and the date is load-bearing. Three things fall out of
it, each chosen because it is visible in a photograph and cheap to say:

- **Season.** Bangalore, so the calendar is monsoon-shaped, not four-seasons
  shaped. A June photo has wet ground in it or it is lying.
- **Era.** Hair length, colour and cut move in slow steps. Continuity here is
  what makes two photos six months apart read as the same person living, rather
  than two attempts at the same prompt. ⚠ An era's hair line DESCRIBES her, which
  is the one thing the pipeline otherwise refuses to do over a reference — so it
  is opt-in per era (`apply_hair`) and never on by default. See `clause`.
- **Manicure.** Polish has a lifespan of about two and a half weeks. Nails
  picked per-shot at random are noise; nails picked by date are a clock, and the
  chipped tail end of a cycle is the kind of detail nobody fakes.

None of this touches identity. It is all scene and grooming — the parts the
prompt is *supposed* to carry, per the measured rule that words specify a type
and only a reference specifies a person.
"""

from __future__ import annotations

import json
from datetime import date as _date
from pathlib import Path

# Bangalore's year, as a photograph sees it. Not meteorology — what is visibly
# different in the frame. Months are 1-indexed and every month is covered.
_SEASONS = [
    ((12, 1, 2), "cool dry season",
     "cool dry weather — clear light, chilly hazy mornings, a light layer or "
     "shawl in the early hours, dust on parked cars"),
    ((3, 4, 5), "hot dry season",
     "dry pre-monsoon heat — harsh high sun, bleached midday light, dusty air, "
     "hard shadows, sweat-damp hair at the temples"),
    ((6, 7, 8, 9), "monsoon",
     "monsoon — overcast grey light, wet reflective tarmac, puddles, damp "
     "clothes and frizz, umbrellas and wet footwear nearby"),
    ((10, 11), "post-monsoon",
     "post-monsoon — washed green foliage, soft bright light between showers, "
     "damp ground drying, mild warm air"),
]


def season(when: _date) -> tuple[str, str]:
    """(name, visible description) for the date's season."""
    for months, name, text in _SEASONS:
        if when.month in months:
            return name, text
    return "", ""   # unreachable: the tuples cover 1-12


# How long a manicure lives. Days 0-3 it is fresh and glossy, then it settles,
# and by the last stretch it has grown out at the cuticle and chipped at the
# tips. The tail matters most: a set of images where the polish is always
# perfect is a set where nobody was actually living between the photos.
MANICURE_DAYS = 18


def manicure(when: _date, nail_ids: list[str], epoch: _date | None = None
             ) -> tuple[str | None, str]:
    """Which manicure she is wearing on this date, and what state it is in.

    Deterministic: the same date always yields the same nails, so re-generating
    a shot doesn't silently repaint them. Returns (nail_id, wear description).
    """
    if not nail_ids:
        return None, ""
    day = (when - (epoch or _date(when.year, 1, 1))).days
    cycle, into = divmod(day, MANICURE_DAYS)
    nail = nail_ids[cycle % len(nail_ids)]
    if into <= 3:
        wear = "a fresh manicure, glossy and clean at the cuticle"
    elif into <= 12:
        wear = "a manicure a week or so old — still neat, slightly softened gloss"
    else:
        wear = ("a manicure at the end of its life — a little regrowth at the "
                "cuticle and light wear at the tips")
    return nail, wear


def era(when: _date, eras: list[dict]) -> dict:
    """The appearance era covering this date.

    `eras` is a per-character list of {"from": "YYYY-MM-DD", ...} entries, newest
    or oldest order irrelevant. The entry with the latest `from` on or before the
    date wins; nothing matches before the first entry, which is correct — an era
    that hasn't started yet should not describe her.
    """
    best, best_from = {}, None
    for e in eras or []:
        try:
            f = _date.fromisoformat(str(e.get("from", "")))
        except ValueError:
            continue
        if f <= when and (best_from is None or f > best_from):
            best, best_from = e, f
    return best


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return {}


def clause(when: _date, tl: dict, nail_ids: list[str] | None = None) -> tuple[str, dict]:
    """The sentence to append to a prompt, plus what it was derived from.

    Kept short on purpose: the prompter is held to 60-130 words and every word
    spent here is a word not spent on the place or the framing. Season and era
    earn their length; anything that isn't visible in the frame does not go in.
    """
    facts: dict = {"date": when.isoformat()}
    bits: list[str] = []

    name, text = season(when)
    facts["season"] = name
    if text:
        bits.append(text)

    e = era(when, tl.get("eras") or [])
    if e:
        facts["era"] = e.get("name") or e.get("from")
        # ⚠ Hair is IDENTITY, and identity is carried by the reference image, never
        # by words — `hair.base` is identity=True and gets dropped the moment a
        # reference exists, precisely so nobody describes her over it (measured:
        # reference + description 0.834 vs reference + terse 0.860).
        #
        # An era's hair line breaks that rule by construction: it is a description
        # of her, injected regardless of what the reference shows. Sometimes that
        # is exactly what you want — the whole point of an era is that she got a
        # haircut and the reference predates it — but it is a deliberate override
        # with a measured cost, not a default. So it stays silent unless the era
        # opts in, and `apply_hair` is recorded in the facts so a shot carrying an
        # overridden hairstyle can be told apart later from one that isn't.
        hair = (e.get("hair") or "").strip()
        if hair and e.get("apply_hair"):
            facts["hair_override"] = True
            bits.append(f"her hair at this point in the year: {hair}")
        note = (e.get("note") or "").strip()
        if note:
            bits.append(note)

    nail, wear = manicure(when, nail_ids or [])
    if nail:
        facts["nail_id"] = nail
    if wear:
        facts["manicure"] = wear
        bits.append(wear)

    if not bits:
        return "", facts
    return ("The date is " + when.strftime("%-d %B %Y") + ": " +
            "; ".join(bits) + "."), facts
