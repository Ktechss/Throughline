"""Getup — what was DONE to her today, per character, per scene.

THE LINE THIS LIBRARY MUST NOT CROSS

Her hair's colour, length and texture are IDENTITY. They live in the part tree as
`hair.colour`, `hair.length`, `hair.texture`, they are `identity=True`, and
`compose(has_reference=True)` drops them precisely so that nothing competes with
her reference image. Commit a9cc83cd exists because a styling word in a prompt
quietly overrode the picture: "never describe her hair over a reference".

So HAIR_STYLING says only what was done to it this morning — pulled back, braided,
still wet — and never what it IS. "Long dark auburn waves" belongs in her bio and
nowhere else; "half-up with a twist at the crown" belongs here. Same relation
between MAKEUP and her persistent `grooming.makeup`, which is her everyday
default; this is the departure from it.

WHY THESE ARE TEXT AND NOT REFERENCES

Every image reference costs identity — 2 refs 0.622, 3 refs 0.579 measured. A
cast of three is already three faces before anyone puts on a shoe. Hair, makeup,
accessories and footwear are all things a sentence reproduces well enough, so
they ride as text and cost nothing. Outfits and manicures are the exceptions
that earn a slot, because a garment and a nail design are exactly what a
description reproduces worst — and both of those already have picker UIs.

Every vocabulary here is also free-text overridable. The list is a starting
point, not the set of things that can happen to a person.
"""

# --------------------------------------------------------------------------
# HAIR STYLING — what was done to it, never what it is.
# --------------------------------------------------------------------------
HAIR_STYLING: dict[str, dict[str, str]] = {

    "Down": {
        "loose-down": "worn loose and down, falling naturally",
        "centre-part-down": "down with a clean centre parting",
        "side-part-down": "down with a deep side parting, more of it on one side",
        "tucked-one-side": "down with one side tucked behind the ear",
        "pushed-back": "pushed back off the face, held there by nothing in "
                       "particular",
        "wind-blown": "down and pushed around by the wind, a few strands across "
                      "the face",
    },

    "Half up": {
        "half-up-clip": "half pulled back and clipped at the crown, the rest left "
                        "down",
        "half-up-twist": "half up with a twist at the crown, the rest falling "
                         "loose",
        "half-up-braided": "half up with the front sections braided back and "
                           "joined behind",
        "pinned-back": "the front sections pinned back off the face, the rest "
                       "down",
    },

    "Tied up": {
        "high-ponytail": "in a high ponytail, pulled tight and smooth",
        "low-ponytail": "in a low ponytail at the nape",
        "messy-bun": "in a loose messy bun with pieces escaping around the face",
        "tight-bun": "in a sleek tight bun, nothing loose",
        "top-knot": "in a top knot on the crown",
        "claw-clip": "twisted up and held with a claw clip, ends sticking out "
                     "above it",
        "half-fallen-out": "tied up this morning and half fallen out since",
    },

    "Braided": {
        "single-braid": "in a single braid down the back",
        "two-braids": "in two braids, one over each shoulder",
        "fishtail": "in a loose fishtail braid over one shoulder",
        "crown-braid": "braided back and pinned around the crown",
        "braid-with-flyaways": "braided, with flyaways loose all round the "
                               "hairline",
    },

    "Condition": {
        "just-washed": "freshly washed and still slightly damp at the ends",
        "shower-wet": "wet from the shower, combed straight back",
        "second-day": "second-day hair, flatter at the roots, a little more "
                      "texture through the lengths",
        "slept-on": "slept on and not yet dealt with, flat on one side",
        "salon-fresh": "just done — smooth, glossy, deliberately set",
        "humidity": "gone soft and frizzy in the humidity",
    },

    "Held back": {
        "headband": "held back with a fabric headband",
        "scarf-tied": "tied back with a scarf knotted behind",
        "sunglasses-as-band": "pushed back off the face by sunglasses sitting on "
                              "the crown",
        "pencil-through-bun": "twisted up and held with whatever was to hand",
    },
}


# --------------------------------------------------------------------------
# MAKEUP — the departure from her everyday default.
# --------------------------------------------------------------------------
MAKEUP: dict[str, dict[str, str]] = {

    "Bare": {
        "none": "no makeup at all, bare skin",
        "just-woken": "no makeup, skin still creased from sleep",
        "sunscreen-only": "no makeup beyond sunscreen, a faint sheen from it",
        "yesterdays": "yesterday's makeup half worn off, a little smudged under "
                      "the eyes",
    },

    "Everyday": {
        "minimal": "minimal everyday makeup — a light base, groomed brows, a "
                   "little mascara",
        "tinted-balm": "barely anything: a tinted balm and brushed brows",
        "concealer-mascara": "concealer under the eyes and mascara, nothing else",
        "everyday-plus-liner": "her usual light base with a thin line along the "
                               "upper lash",
    },

    "Done": {
        "soft-glam": "properly done in a soft way — smooth base, defined eyes, a "
                     "neutral lip",
        "bold-lip": "a bold saturated lip with the rest kept deliberately bare",
        "smoky-eye": "a smoked-out dark eye with a nude lip",
        "graphic-liner": "a sharp graphic liner flicked well past the eye corner",
        "glossy-skin": "high-shine skin, glossed lids and a wet-look lip",
        "full-glam": "full evening makeup — sculpted base, strong eye, defined "
                     "lip, everything deliberate",
    },

    "Occasion": {
        "festive": "festive makeup — warm metallics on the lids, a deep lip, a "
                   "little shimmer high on the cheek",
        "bridal-guest": "dressed-up wedding-guest makeup, polished and "
                        "long-wearing",
        "editorial-odd": "something deliberately editorial and slightly odd — an "
                         "unexpected colour placed where it would not normally go",
        "no-makeup-makeup": "the kind of makeup that takes an hour to look like "
                            "none at all",
    },

    "Worn": {
        "end-of-day": "makeup that has been on since morning: base broken up, "
                      "lip mostly gone",
        "cried-off": "makeup slightly cried off, eyes a little pink",
        "sweated-off": "sweated off in the heat, shine coming through the base",
        "swim-off": "washed off in water, only a trace of mascara left",
    },
}


# --------------------------------------------------------------------------
# ACCESSORIES — worn things that are not the outfit.
# --------------------------------------------------------------------------
# `face` marks the ones that sit ON the face. Sunglasses are not a style note,
# they are an identity decision: ArcFace keys hardest on the eye region, and the
# mirror-selfie clause in prompt.py exists because forcing her eyes onto the
# reflection moved the same shot from 0.334 to 0.628. Dark lenses remove both
# eyes. The composer surfaces `face` so the cost is visible before it is paid,
# and the existing `face_accessories` toggle can strip them.
ACCESSORIES: dict[str, dict[str, dict]] = {

    "Eyes": {
        "sunglasses-dark": {"text": "dark opaque sunglasses", "face": True},
        "sunglasses-tinted": {"text": "lightly tinted sunglasses with the eyes "
                                      "still visible through them", "face": True},
        "sunglasses-on-head": {"text": "sunglasses pushed up onto the crown of "
                                       "the head", "face": False},
        "glasses-clear": {"text": "clear-lens spectacles with fine frames",
                          "face": True},
    },

    "Ears & neck": {
        "gold-hoops": {"text": "small gold hoop earrings", "face": False},
        "big-hoops": {"text": "large statement hoop earrings", "face": False},
        "jhumkas": {"text": "traditional jhumka earrings", "face": False},
        "studs": {"text": "small plain studs", "face": False},
        "fine-chain": {"text": "a fine gold chain at the throat", "face": False},
        "layered-chains": {"text": "several fine chains layered at different "
                                   "lengths", "face": False},
        "chunky-pendant": {"text": "one heavy pendant on a short chain",
                           "face": False},
        "choker": {"text": "a close-fitting choker", "face": False},
    },

    "Hands & wrists": {
        "watch": {"text": "a watch on one wrist", "face": False},
        "stacked-bangles": {"text": "a stack of thin bangles on one wrist",
                            "face": False},
        "rings-several": {"text": "several rings across both hands",
                          "face": False},
        "one-ring": {"text": "a single ring", "face": False},
        "friendship-thread": {"text": "a worn thread tied at the wrist",
                              "face": False},
    },

    "Carried": {
        "shoulder-bag": {"text": "a leather shoulder bag", "face": False},
        "crossbody": {"text": "a small crossbody bag worn across the chest",
                      "face": False},
        "tote": {"text": "a large open tote over one shoulder", "face": False},
        "backpack": {"text": "a compact backpack on both shoulders",
                     "face": False},
        "clutch": {"text": "a small clutch held in one hand", "face": False},
        "shopping-bags": {"text": "a couple of shopping bags in one hand",
                          "face": False},
        "tiffin": {"text": "a steel tiffin carrier", "face": False},
        "yoga-mat": {"text": "a rolled mat under one arm", "face": False},
    },

    "Head & wrapped": {
        "cap": {"text": "a plain baseball cap", "face": True},
        "bucket-hat": {"text": "a soft bucket hat", "face": True},
        "dupatta-head": {"text": "a dupatta drawn loosely over the head",
                         "face": False},
        "scarf-neck": {"text": "a light scarf knotted at the neck",
                       "face": False},
        "stole": {"text": "a long stole over one shoulder", "face": False},
        "umbrella": {"text": "an open umbrella held overhead", "face": False},
    },
}


# --------------------------------------------------------------------------
# FOOTWEAR — only ever visible below a knee-up frame.
# --------------------------------------------------------------------------
# The composer greys these out above `knee_up`, because specifying shoes in a
# head-and-shoulders crop spends prompt attention on something outside the frame
# — and prompt attention is the scarce resource this whole package is rationing.
FOOTWEAR: dict[str, dict[str, str]] = {
    "Flat": {
        "sneakers-white": "clean white sneakers",
        "sneakers-worn": "well-worn trainers",
        "kolhapuris": "flat leather kolhapuri sandals",
        "flat-sandals": "plain flat sandals",
        "loafers": "leather loafers",
        "ballet-flats": "soft ballet flats",
        "flip-flops": "rubber flip-flops",
        "barefoot": "barefoot",
    },
    "Raised": {
        "block-heels": "low block heels",
        "stilettos": "fine high heels",
        "wedges": "wedge sandals",
        "heeled-boots": "ankle boots with a heel",
        "platform": "chunky platform soles",
    },
    "Covered": {
        "ankle-boots": "flat ankle boots",
        "tall-boots": "boots to below the knee",
        "juttis": "embroidered juttis",
        "sports-shoes": "proper running shoes",
    },
}
