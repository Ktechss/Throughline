"""Moments — whole believable slices of an ordinary day.

A pose says how a body is arranged. A place says where. Neither says what is
HAPPENING, and a year of images with no activity in them reads as a catalogue of
one woman standing in rooms rather than a record of a life.

A moment is one click that fills every axis at once: where she is, what she is
doing, how she is arranged, who held the camera, how imperfect the frame is.
Everything it fills stays editable — a moment is a starting point, not a
decision.

FIELDS

    place       a key from HOME_CORNERS or REGULAR_PLACES (main.py), or "" for
                somewhere the brief describes. Validated on import: a typo here
                would silently produce a scene with no setting.
    activity    what is happening. Concrete and photographable — "steam rising
                from the pan", never "enjoying the morning".
    pose        how ONE body is arranged. Used when the cast is 1.
    interaction an id from interactions_data. Used INSTEAD of `pose` when the
                cast is bigger, because two people need arrangement relative to
                each other, not two separate poses.
    holder      who held the camera (CAMERA_HOLDERS)
    flaws       how imperfect the frame is (SNAPSHOT_FLAWS)
    shot_type   photographic register (SHOT_TYPES)
    min_cast    hidden below this many characters

WRITING RULE, same as everywhere else here: describe the scene and the action,
never the woman. Her face, hair, skin and build come from her references. A
moment that describes her would cost identity the same 0.86 -> 0.53 the rest of
this pipeline is built to avoid.
"""

MOMENTS: dict[str, dict[str, dict]] = {

    "Morning": {
        "sunday-morning-chai": {
            "label": "Sunday morning chai", "place": "kitchen",
            "activity": "making chai at the stove, steam rising off the pan, a "
                        "cup and a strainer waiting on the counter",
            "pose": "one hand resting on the counter, looking down into the pan",
            "interaction": "cooking-side-by-side",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "still-half-asleep": {
            "label": "Still half asleep", "place": "bedroom",
            "activity": "sitting on the edge of an unmade bed, phone in hand, "
                        "morning light coming in flat and grey",
            # "hair unbrushed" described HER, which the reference is supposed to
            # carry. Same class as the era-hair regression: a styling word in a
            # prompt quietly competing with the image.
            "pose": "shoulders rounded, still in what she slept in, looking down "
                    "at the screen",
            "interaction": "", "holder": "timer", "flaws": "snapshot",
            "shot_type": "candid", "min_cast": 1},
        "getting-ready": {
            "label": "Getting ready", "place": "bathroom",
            "activity": "leaning toward the mirror mid-routine, a few things "
                        "scattered across the vanity",
            "pose": "one hand near her face, weight on the counter",
            "interaction": "showing-something",
            "holder": "mirror", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "balcony-first-light": {
            "label": "Balcony, first light", "place": "balcony",
            "activity": "standing at the railing with a cup, the city still "
                        "quiet below, early haze over the buildings",
            "pose": "forearms on the railing, looking out",
            "interaction": "both-looking-elsewhere",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
    },

    "Commute": {
        "waiting-on-the-platform": {
            "label": "Waiting on the platform", "place": "reg_commute",
            "activity": "standing behind the yellow line with the train not yet "
                        "in, bag over one shoulder",
            "pose": "weight on one hip, looking down the track",
            "interaction": "waiting-together",
            "holder": "stranger", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
        "walking-to-work": {
            "label": "Walking to work", "place": "reg_street",
            "activity": "walking along the road past parked two-wheelers and "
                        "shuttered shopfronts, morning traffic behind",
            "pose": "mid-stride, bag strap in one hand",
            "interaction": "side-by-side-walking",
            "holder": "friend", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
        "caught-in-the-rain": {
            "label": "Caught in the rain", "place": "reg_street",
            "activity": "wet tarmac reflecting the light, rain coming down "
                        "steadily, shoulders damp",
            "pose": "one hand shielding her head, hurrying",
            "interaction": "sharing-an-umbrella",
            "holder": "friend", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
    },

    "Work": {
        "at-the-desk": {
            "label": "At the desk", "place": "reg_desk",
            "activity": "working at a monitor with a mug and a lanyard beside "
                        "the keyboard, other desks behind",
            "pose": "leaning back slightly, one hand on the mouse",
            "interaction": "sharing-a-phone-screen",
            "holder": "stranger", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "working-from-home": {
            "label": "Working from home", "place": "office",
            "activity": "laptop open on the desk, notes and a pinboard behind, "
                        "afternoon light across the room",
            "pose": "chin on one hand, reading the screen",
            "interaction": "across-a-table",
            "holder": "timer", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "coffee-break": {
            "label": "Coffee break", "place": "reg_cafe",
            "activity": "standing at the counter waiting for a coffee, the "
                        "espresso machine and menu board behind",
            "pose": "leaning on the counter, looking off toward the window",
            "interaction": "mid-sentence-turned-in",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
    },

    "Errands": {
        "unpacking-groceries": {
            "label": "Unpacking groceries", "place": "kitchen",
            "activity": "bags on the counter half unpacked, vegetables and "
                        "packets spread across it",
            "pose": "reaching into a bag, half turned away",
            "interaction": "carrying-bags-together",
            "holder": "friend", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "shopping-street": {
            "label": "Out on the shopping street", "place": "reg_street",
            "activity": "walking past shopfronts with a couple of bags, awnings "
                        "and signage overhead",
            "pose": "mid-stride, bags in one hand",
            "interaction": "pointing-at-something",
            "holder": "friend", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
    },

    "Eating": {
        "cooking-dinner": {
            "label": "Cooking dinner", "place": "kitchen",
            "activity": "chopping at the counter with pans going on the stove, "
                        "warm evening light in the room",
            "pose": "both hands working, head down at the board",
            "interaction": "cooking-side-by-side",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "dinner-at-the-table": {
            "label": "Dinner at the table", "place": "dining",
            "activity": "seated at the dining table mid-meal, plates and a "
                        "pendant light overhead",
            "pose": "leaning forward on her forearms, mid-sentence",
            "interaction": "across-a-table",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "cafe-table": {
            "label": "A long lunch", "place": "reg_cafe",
            "activity": "at a wooden table by the window, cups and plates "
                        "between them, street visible outside",
            "pose": "one elbow on the table, chin resting on her hand",
            "interaction": "both-mid-laugh",
            "holder": "stranger", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
    },

    "Downtime": {
        "reading-on-the-sofa": {
            "label": "Reading on the sofa", "place": "living_room",
            "activity": "curled into the corner of the sofa with a book, a lamp "
                        "on and the rest of the room dim",
            "pose": "legs tucked up, book resting on her knees",
            "interaction": "one-in-focus-one-behind",
            "holder": "timer", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "phone-on-the-sofa": {
            "label": "Scrolling", "place": "living_room",
            "activity": "slumped into the sofa with the phone held up, screen "
                        "light on her face, the room dark around her",
            "pose": "one arm behind her head, phone in the other hand",
            "interaction": "sharing-a-phone-screen",
            "holder": "timer", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "terrace-at-dusk": {
            "label": "Terrace at dusk", "place": "terrace",
            "activity": "sitting out among the plants as the light goes, string "
                        "lights just coming on",
            "pose": "sitting sideways on a chair, one arm over its back",
            "interaction": "sitting-close-knees-touching",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
    },

    "Social": {
        "friends-at-the-cafe": {
            "label": "Friends at the cafe", "place": "reg_cafe",
            "activity": "crowded around a small table with coffees, the room "
                        "busy behind them",
            "pose": "turned in her seat, laughing at something",
            "interaction": "one-laughing-at-the-other",
            "holder": "stranger", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "getting-ready-to-go-out": {
            "label": "Getting ready to go out", "place": "closet",
            "activity": "in front of the full-length mirror among the racks, "
                        "deciding, a couple of options still on hangers",
            "pose": "half turned, checking the back of the outfit",
            "interaction": "showing-something",
            "holder": "mirror", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "party-selfie": {
            "label": "At a party", "place": "",
            "activity": "at a crowded evening party, low warm light and people "
                        "out of focus behind",
            "pose": "arm up holding the phone, leaning into frame",
            "interaction": "taking-a-selfie-together",
            "holder": "selfie", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
    },

    "Exercise": {
        "at-the-gym": {
            "label": "At the gym", "place": "reg_gym",
            "activity": "between sets on the gym floor, racks and mirrors "
                        "behind, water bottle in hand",
            "pose": "one hand on a machine, catching her breath",
            "interaction": "waiting-together",
            "holder": "friend", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "evening-walk": {
            "label": "Evening walk", "place": "reg_street",
            "activity": "walking the block as the light goes, streetlights just "
                        "coming on overhead",
            "pose": "hands in pockets, mid-stride",
            "interaction": "side-by-side-walking",
            "holder": "friend", "flaws": "subtle", "shot_type": "street",
            "min_cast": 1},
    },

    "Night": {
        "getting-home": {
            "label": "Getting home", "place": "entryway",
            "activity": "just through the door with keys and a bag still in "
                        "hand, hallway light on",
            "pose": "half turned toward the door, bag sliding off her shoulder",
            "interaction": "carrying-bags-together",
            "holder": "timer", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "late-kitchen": {
            "label": "Late in the kitchen", "place": "kitchen",
            "activity": "standing at the counter late at night with one light "
                        "on, the rest of the flat dark",
            "pose": "leaning back against the counter, cup in both hands",
            "interaction": "leaning-in-to-hear",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "winding-down": {
            "label": "Winding down", "place": "bedroom",
            "activity": "sitting back against the headboard with the bedside "
                        "lamp on, the room otherwise dark",
            "pose": "knees up, head tipped back against the wall",
            "interaction": "", "holder": "timer", "flaws": "subtle",
            "shot_type": "candid", "min_cast": 1},
    },
}
