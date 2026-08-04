"""Moments — whole believable slices of an ordinary day.

A pose says how a body is arranged. A place says where. Neither says what is
HAPPENING, and a year of images with no activity in them reads as a catalogue of
one woman standing in rooms rather than a record of a life.

A moment is one click that fills every axis at once: where she is, what she is
doing, how she is arranged, who held the camera, how the frame is cropped, what
the light is doing, what hour it is, how imperfect the picture is.

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
    framing     a key from framing_data. The one field most worth pre-filling:
                a moment knows whether it is a close conversation or a wide
                street, and framing decides how many pixels a face gets.
    lighting    a key from lighting_data.LIGHTING
    time_of_day a key from lighting_data.TIME_OF_DAY
    holder      who held the camera (CAMERA_HOLDERS)
    flaws       how imperfect the frame is (SNAPSHOT_FLAWS)
    shot_type   photographic register (SHOT_TYPES)
    min_cast    hidden below this many characters

WRITING RULE, same as everywhere else here: describe the scene and the action,
never the woman. Her face, hair, skin and build come from her references. A
moment that describes her would cost identity the same 0.86 -> 0.53 the rest of
this pipeline is built to avoid.

A NOTE ON FRAMING AND THE GATE. Several of these are deliberately wide or
full-length — a woman crossing a road, a room she is small inside. Those will
score low or abstain, and that is correct rather than a bug: the gate reports
face size and yaw alongside every number precisely so a wide shot is not mistaken
for drift. Do not narrow this library to what measures well, or the year it
produces will be three hundred close-ups.
"""

MOMENTS: dict[str, dict[str, dict]] = {

    "Morning": {
        "sunday-morning-chai": {
            "label": "Sunday morning chai", "place": "kitchen",
            "activity": "making chai at the stove, steam rising off the pan, a "
                        "cup and a strainer waiting on the counter",
            "pose": "one hand resting on the counter, looking down into the pan",
            "interaction": "cooking-side-by-side",
            "framing": "waist_up", "lighting": "soft-window",
            "time_of_day": "early-morning",
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
            "interaction": "", "framing": "chest_up", "lighting": "overcast-flat",
            "time_of_day": "early-morning",
            "holder": "timer", "flaws": "snapshot",
            "shot_type": "candid", "min_cast": 1},
        "getting-ready": {
            "label": "Getting ready", "place": "bathroom",
            "activity": "leaning toward the mirror mid-routine, a few things "
                        "scattered across the vanity",
            "pose": "one hand near her face, weight on the counter",
            "interaction": "showing-something",
            "framing": "chest_up", "lighting": "warm-lamp",
            "time_of_day": "early-morning",
            "holder": "mirror", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "balcony-first-light": {
            "label": "Balcony, first light", "place": "balcony",
            "activity": "standing at the railing with a cup, the city still "
                        "quiet below, early haze over the buildings",
            "pose": "forearms on the railing, looking out",
            "interaction": "both-looking-elsewhere",
            "framing": "waist_up", "lighting": "backlit-rim", "time_of_day": "dawn",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "packing-a-bag": {
            "label": "Packing a bag", "place": "bedroom",
            "activity": "packing a bag on the bed, things half in and half out, "
                        "checking what is missing",
            "pose": "bent over the bed, one hand sorting through it",
            "interaction": "helping-with-a-strap",
            "framing": "waist_up", "lighting": "soft-window",
            "time_of_day": "mid-morning",
            "holder": "timer", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "breakfast-standing-up": {
            "label": "Breakfast standing up", "place": "kitchen",
            "activity": "eating standing at the counter, already half ready to "
                        "leave, plate held in one hand",
            "pose": "leaning against the counter mid-bite, looking at nothing",
            "interaction": "talking-past-each-other",
            "framing": "chest_up", "lighting": "soft-window",
            "time_of_day": "early-morning",
            "holder": "friend", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
    },

    "Commute": {
        "waiting-on-the-platform": {
            "label": "Waiting on the platform", "place": "reg_commute",
            "activity": "standing behind the yellow line with the train not yet "
                        "in, bag over one shoulder",
            "pose": "weight on one hip, looking down the track",
            "interaction": "waiting-together",
            "framing": "knee_up", "lighting": "overhead-fluoro",
            "time_of_day": "early-morning",
            "holder": "stranger", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
        "walking-to-work": {
            "label": "Walking to work", "place": "reg_street",
            "activity": "walking along the road past parked two-wheelers and "
                        "shuttered shopfronts, morning traffic behind",
            "pose": "mid-stride, bag strap in one hand",
            "interaction": "side-by-side-walking",
            "framing": "knee_up", "lighting": "hard-sun",
            "time_of_day": "mid-morning",
            "holder": "friend", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
        "caught-in-the-rain": {
            "label": "Caught in the rain", "place": "reg_street",
            "activity": "wet tarmac reflecting the light, rain coming down "
                        "steadily, shoulders damp",
            "pose": "one hand shielding her head, hurrying",
            "interaction": "sharing-an-umbrella",
            "framing": "waist_up", "lighting": "overcast-flat",
            "time_of_day": "afternoon",
            "holder": "friend", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
        "in-the-back-of-an-auto": {
            "label": "In the back of an auto", "place": "",
            "activity": "sitting in the back of an auto-rickshaw with the city "
                        "moving past on both sides, one hand on the rail",
            "pose": "turned toward the open side, watching the street go by",
            "interaction": "sitting-close-knees-touching",
            "framing": "chest_up", "lighting": "dappled", "time_of_day": "afternoon",
            "holder": "friend", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "crossing-the-road": {
            "label": "Crossing the road", "place": "reg_street",
            "activity": "crossing between stopped traffic, looking for the gap, "
                        "the road wide and busy around her",
            "pose": "mid-stride with one arm out for balance, head turned",
            "interaction": "crossing-a-street",
            "framing": "full_body", "lighting": "hard-sun", "time_of_day": "midday",
            "holder": "stranger", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
        "stuck-in-traffic": {
            "label": "Stuck in traffic", "place": "",
            "activity": "not moving, in a line of vehicles, everything idling and "
                        "hot, nothing to do but wait",
            "pose": "chin on one hand, elbow on the window edge",
            "interaction": "waiting-together",
            "framing": "chest_up", "lighting": "hard-sun", "time_of_day": "afternoon",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
    },

    "Work": {
        "at-the-desk": {
            "label": "At the desk", "place": "reg_desk",
            "activity": "working at a monitor with a mug and a lanyard beside "
                        "the keyboard, other desks behind",
            "pose": "leaning back slightly, one hand on the mouse",
            "interaction": "sharing-a-phone-screen",
            "framing": "waist_up", "lighting": "overhead-fluoro",
            "time_of_day": "mid-morning",
            "holder": "stranger", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "working-from-home": {
            "label": "Working from home", "place": "office",
            "activity": "laptop open on the desk, notes and a pinboard behind, "
                        "afternoon light across the room",
            "pose": "chin on one hand, reading the screen",
            "interaction": "across-a-table",
            "framing": "chest_up", "lighting": "soft-window",
            "time_of_day": "afternoon",
            "holder": "timer", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "coffee-break": {
            "label": "Coffee break", "place": "reg_cafe",
            "activity": "standing at the counter waiting for a coffee, the "
                        "espresso machine and menu board behind",
            "pose": "leaning on the counter, looking off toward the window",
            "interaction": "mid-sentence-turned-in",
            "framing": "chest_up", "lighting": "mixed-domestic",
            "time_of_day": "mid-morning",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "presenting-to-the-room": {
            "label": "Presenting", "place": "reg_desk",
            "activity": "standing at the front of a meeting room mid-explanation, "
                        "a screen behind and people seated in front",
            "pose": "one hand raised in a small gesture, weight on one foot",
            "interaction": "pointing-at-something",
            "framing": "knee_up", "lighting": "overhead-fluoro",
            "time_of_day": "mid-morning",
            "holder": "stranger", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "late-at-the-office": {
            "label": "Late at the office", "place": "reg_desk",
            "activity": "the only lit desk left, the rest of the floor dark, one "
                        "screen still going",
            "pose": "slumped forward on her forearms, still reading",
            "interaction": "one-in-focus-one-behind",
            "framing": "waist_up", "lighting": "screen-glow",
            "time_of_day": "late-night",
            "holder": "timer", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "a-difficult-conversation": {
            "label": "A difficult conversation", "place": "reg_desk",
            "activity": "two of them off to one side of the floor, not at a desk, "
                        "talking about something that is not going well",
            "pose": "arms folded, looking at the floor",
            "interaction": "arms-folded-listening",
            "framing": "chest_up", "lighting": "overhead-fluoro",
            "time_of_day": "afternoon",
            "holder": "", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 2},
    },

    "Errands": {
        "unpacking-groceries": {
            "label": "Unpacking groceries", "place": "kitchen",
            "activity": "bags on the counter half unpacked, vegetables and "
                        "packets spread across it",
            "pose": "reaching into a bag, half turned away",
            "interaction": "carrying-bags-together",
            "framing": "waist_up", "lighting": "warm-lamp",
            "time_of_day": "evening",
            "holder": "friend", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "shopping-street": {
            "label": "Out on the shopping street", "place": "reg_street",
            "activity": "walking past shopfronts with a couple of bags, awnings "
                        "and signage overhead",
            "pose": "mid-stride, bags in one hand",
            "interaction": "pointing-at-something",
            "framing": "knee_up", "lighting": "open-shade",
            "time_of_day": "afternoon",
            "holder": "friend", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
        "at-the-vegetable-market": {
            "label": "At the vegetable market", "place": "",
            "activity": "at a vegetable stall picking through what is there, "
                        "crates and scales and other buyers pressed close",
            "pose": "bent slightly toward the crates, one hand sorting",
            "interaction": "choosing-between-two",
            "framing": "waist_up", "lighting": "dappled",
            "time_of_day": "mid-morning",
            "holder": "stranger", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
        "at-the-tailor": {
            "label": "At the tailor", "place": "",
            "activity": "standing at a tailor's counter with fabric between them, "
                        "a measuring tape and a machine behind",
            "pose": "one arm held out, standing still to be measured",
            "interaction": "helping-with-a-strap",
            "framing": "waist_up", "lighting": "bright-retail",
            "time_of_day": "afternoon",
            "holder": "stranger", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "queue-at-the-chemist": {
            "label": "Queue at the chemist", "place": "",
            "activity": "waiting in a short queue at a chemist's counter, shelves "
                        "of boxes behind the glass",
            "pose": "weight on one hip, looking at nothing in particular",
            "interaction": "queueing-together",
            "framing": "chest_up", "lighting": "overhead-fluoro",
            "time_of_day": "evening",
            "holder": "stranger", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "at-the-mall": {
            "label": "At the mall", "place": "",
            "activity": "on an upper level of a shopping mall, atrium light "
                        "falling in, shopfronts and escalators behind",
            "pose": "leaning on the railing, looking down at the floors below",
            "interaction": "three-round-a-table",
            "framing": "waist_up", "lighting": "bright-retail",
            "time_of_day": "afternoon",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
    },

    "Eating": {
        "cooking-dinner": {
            "label": "Cooking dinner", "place": "kitchen",
            "activity": "chopping at the counter with pans going on the stove, "
                        "warm evening light in the room",
            "pose": "both hands working, head down at the board",
            "interaction": "cooking-side-by-side",
            "framing": "waist_up", "lighting": "warm-lamp",
            "time_of_day": "evening",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "dinner-at-the-table": {
            "label": "Dinner at the table", "place": "dining",
            "activity": "seated at the dining table mid-meal, plates and a "
                        "pendant light overhead",
            "pose": "leaning forward on her forearms, mid-sentence",
            "interaction": "across-a-table",
            "framing": "chest_up", "lighting": "warm-lamp",
            "time_of_day": "evening",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "cafe-table": {
            "label": "A long lunch", "place": "reg_cafe",
            "activity": "at a wooden table by the window, cups and plates "
                        "between them, street visible outside",
            "pose": "one elbow on the table, chin resting on her hand",
            "interaction": "both-mid-laugh",
            "framing": "chest_up", "lighting": "soft-window",
            "time_of_day": "afternoon",
            "holder": "stranger", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "street-food-stall": {
            "label": "At a street food stall", "place": "reg_street",
            "activity": "standing at a street food cart eating off a paper plate, "
                        "steam and a hot griddle behind",
            "pose": "plate held up close, mid-bite, half turned away from the cart",
            "interaction": "three-eating-and-talking",
            "framing": "chest_up", "lighting": "streetlight-sodium",
            "time_of_day": "evening",
            "holder": "friend", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
        "ice-cream-counter": {
            "label": "At the ice cream counter", "place": "",
            "activity": "at a gelato counter with tubs behind the glass, cones "
                        "and cups in hand, deciding and then eating",
            "pose": "leaning toward the glass, pointing at one of the tubs",
            "interaction": "three-eating-and-talking",
            "framing": "head_shoulders", "lighting": "bright-retail",
            "time_of_day": "afternoon",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "eating-alone-late": {
            "label": "Eating alone, late", "place": "kitchen",
            "activity": "eating something quick standing at the counter, one "
                        "light on and the rest of the flat dark",
            "pose": "leaning against the counter, bowl held up near her chest",
            "interaction": "", "framing": "chest_up", "lighting": "warm-lamp",
            "time_of_day": "late-night",
            "holder": "timer", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "sharing-a-dessert": {
            "label": "Sharing a dessert", "place": "reg_cafe",
            "activity": "one plate between them and two spoons, most of it "
                        "already gone",
            "pose": "leaning in over the plate, spoon halfway",
            "interaction": "showing-something",
            "framing": "head_shoulders", "lighting": "warm-lamp",
            "time_of_day": "evening",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 2},
    },

    "Downtime": {
        "reading-on-the-sofa": {
            "label": "Reading on the sofa", "place": "living_room",
            "activity": "curled into the corner of the sofa with a book, a lamp "
                        "on and the rest of the room dim",
            "pose": "legs tucked up, book resting on her knees",
            "interaction": "one-in-focus-one-behind",
            "framing": "waist_up", "lighting": "warm-lamp",
            "time_of_day": "evening",
            "holder": "timer", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "phone-on-the-sofa": {
            "label": "Scrolling", "place": "living_room",
            "activity": "slumped into the sofa with the phone held up, screen "
                        "light on her face, the room dark around her",
            "pose": "one arm behind her head, phone in the other hand",
            "interaction": "three-heads-over-one-phone",
            "framing": "chest_up", "lighting": "screen-glow",
            "time_of_day": "late-night",
            "holder": "timer", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "terrace-at-dusk": {
            "label": "Terrace at dusk", "place": "terrace",
            "activity": "sitting out among the plants as the light goes, string "
                        "lights just coming on",
            "pose": "sitting sideways on a chair, one arm over its back",
            "interaction": "sitting-close-knees-touching",
            "framing": "waist_up", "lighting": "string-lights",
            "time_of_day": "dusk",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "watching-something": {
            "label": "Watching something", "place": "living_room",
            "activity": "watching a screen in a dark room, light from it flickering "
                        "across everything, snacks half finished",
            "pose": "sunk low into the sofa, knees up",
            "interaction": "sitting-close-knees-touching",
            "framing": "chest_up", "lighting": "screen-glow",
            "time_of_day": "evening",
            "holder": "timer", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "sorting-the-closet": {
            "label": "Sorting the closet", "place": "closet",
            "activity": "everything pulled off the racks and piled up, sorting it "
                        "into what stays and what goes",
            "pose": "kneeling by a pile, holding something up to look at it",
            "interaction": "choosing-between-two",
            "framing": "knee_up", "lighting": "warm-lamp",
            "time_of_day": "afternoon",
            "holder": "timer", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "on-the-floor-talking": {
            "label": "On the floor, talking", "place": "living_room",
            "activity": "sitting on the floor with backs against the sofa, talking "
                        "for a long time, cups going cold",
            "pose": "knees up, arms around them, head tipped back",
            "interaction": "three-round-a-table",
            "framing": "waist_up", "lighting": "warm-lamp",
            "time_of_day": "late-night",
            "holder": "timer", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "doing-nothing-on-the-balcony": {
            "label": "Doing nothing", "place": "balcony",
            "activity": "sitting out on the balcony with nothing happening, the "
                        "afternoon going by below",
            "pose": "feet up on the railing, sunk down in the chair",
            "interaction": "both-looking-elsewhere",
            "framing": "knee_up", "lighting": "open-shade",
            "time_of_day": "afternoon",
            "holder": "timer", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
    },

    "Social": {
        "friends-at-the-cafe": {
            "label": "Friends at the cafe", "place": "reg_cafe",
            "activity": "crowded around a small table with coffees, the room "
                        "busy behind them",
            "pose": "turned in her seat, laughing at something",
            "interaction": "one-laughing-at-the-other",
            "framing": "chest_up", "lighting": "mixed-domestic",
            "time_of_day": "afternoon",
            "holder": "stranger", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "getting-ready-to-go-out": {
            "label": "Getting ready to go out", "place": "closet",
            "activity": "in front of the full-length mirror among the racks, "
                        "deciding, a couple of options still on hangers",
            "pose": "half turned, checking the back of the outfit",
            "interaction": "showing-something",
            "framing": "full_body", "lighting": "warm-lamp",
            "time_of_day": "evening",
            "holder": "mirror", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "party-selfie": {
            "label": "At a party", "place": "",
            "activity": "at a crowded evening party, low warm light and people "
                        "out of focus behind",
            "pose": "arm up holding the phone, leaning into frame",
            "interaction": "taking-a-selfie-together",
            "framing": "head_shoulders", "lighting": "neon-signage",
            "time_of_day": "late-night",
            "holder": "selfie", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "a-wedding": {
            "label": "At a wedding", "place": "",
            "activity": "at a wedding function under strung lights and marigolds, "
                        "a crowd of guests and music behind",
            "pose": "turned toward someone off frame, mid-conversation",
            "interaction": "group-clustered-tight",
            "framing": "waist_up", "lighting": "string-lights",
            "time_of_day": "evening",
            "holder": "stranger", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "a-birthday": {
            "label": "A birthday", "place": "dining",
            "activity": "a cake on the table with candles lit, everyone crowded "
                        "round it, the room otherwise dark",
            "pose": "leaning over the cake mid-laugh, lit from below",
            "interaction": "group-mid-laugh",
            "framing": "head_shoulders", "lighting": "candle-warm",
            "time_of_day": "evening",
            "holder": "friend", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "the-group-photo": {
            "label": "The group photo", "place": "",
            "activity": "everyone stopping what they were doing to line up for "
                        "one picture that somebody insisted on",
            "pose": "square to the camera, arm around whoever is next to her",
            "interaction": "group-in-a-line",
            "framing": "waist_up", "lighting": "on-camera-flash",
            "time_of_day": "evening",
            "holder": "stranger", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 2},
        "waiting-outside-a-venue": {
            "label": "Waiting outside", "place": "reg_street",
            "activity": "standing outside a venue in a queue that is not moving, "
                        "signage lit up behind",
            "pose": "arms folded against the cold, looking down the line",
            "interaction": "waiting-together",
            "framing": "knee_up", "lighting": "neon-signage",
            "time_of_day": "evening",
            "holder": "friend", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
        "leaving-a-place": {
            "label": "Leaving", "place": "entryway",
            "activity": "the goodbye at the door that takes twenty minutes, "
                        "everyone half in coats",
            "pose": "one hand on the door frame, turned back to say one more thing",
            "interaction": "goodbye-at-a-door",
            "framing": "waist_up", "lighting": "warm-lamp",
            "time_of_day": "late-night",
            "holder": "timer", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 2},
    },

    "Exercise": {
        "at-the-gym": {
            "label": "At the gym", "place": "reg_gym",
            "activity": "between sets on the gym floor, racks and mirrors "
                        "behind, water bottle in hand",
            "pose": "one hand on a machine, catching her breath",
            "interaction": "waiting-together",
            "framing": "waist_up", "lighting": "overhead-fluoro",
            "time_of_day": "early-morning",
            "holder": "friend", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "evening-walk": {
            "label": "Evening walk", "place": "reg_street",
            "activity": "walking the block as the light goes, streetlights just "
                        "coming on overhead",
            "pose": "hands in pockets, mid-stride",
            "interaction": "side-by-side-walking",
            "framing": "knee_up", "lighting": "golden-hour",
            "time_of_day": "golden",
            "holder": "friend", "flaws": "subtle", "shot_type": "street",
            "min_cast": 1},
        "stretching-after": {
            "label": "Stretching after", "place": "reg_gym",
            "activity": "on a mat at the edge of the floor afterwards, everything "
                        "quieter, still catching her breath",
            "pose": "seated on the mat, one leg out, reaching toward it",
            "interaction": "both-looking-elsewhere",
            "framing": "full_body", "lighting": "overhead-fluoro",
            "time_of_day": "early-morning",
            "holder": "timer", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "a-long-walk-somewhere-green": {
            "label": "A long walk", "place": "",
            "activity": "walking a path with trees over it, nothing urgent, some "
                        "distance still to go",
            "pose": "mid-stride, looking off to one side",
            "interaction": "side-by-side-walking",
            "framing": "wide", "lighting": "dappled", "time_of_day": "mid-morning",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
    },

    "Night": {
        "getting-home": {
            "label": "Getting home", "place": "entryway",
            "activity": "just through the door with keys and a bag still in "
                        "hand, hallway light on",
            "pose": "half turned toward the door, bag sliding off her shoulder",
            "interaction": "carrying-bags-together",
            "framing": "waist_up", "lighting": "warm-lamp",
            "time_of_day": "evening",
            "holder": "timer", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "late-kitchen": {
            "label": "Late in the kitchen", "place": "kitchen",
            "activity": "standing at the counter late at night with one light "
                        "on, the rest of the flat dark",
            "pose": "leaning back against the counter, cup in both hands",
            "interaction": "leaning-in-to-hear",
            "framing": "chest_up", "lighting": "warm-lamp",
            "time_of_day": "late-night",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "winding-down": {
            "label": "Winding down", "place": "bedroom",
            "activity": "sitting back against the headboard with the bedside "
                        "lamp on, the room otherwise dark",
            "pose": "knees up, head tipped back against the wall",
            "interaction": "", "framing": "chest_up", "lighting": "warm-lamp",
            "time_of_day": "late-night",
            "holder": "timer", "flaws": "subtle",
            "shot_type": "candid", "min_cast": 1},
        "walking-back-late": {
            "label": "Walking back late", "place": "reg_street",
            "activity": "walking home along an empty road under streetlights, "
                        "shopfronts shuttered, almost nobody about",
            "pose": "hands in pockets, head down, mid-stride",
            "interaction": "side-by-side-walking",
            "framing": "full_body", "lighting": "streetlight-sodium",
            "time_of_day": "late-night",
            "holder": "friend", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
        "taking-it-off": {
            "label": "Taking it all off", "place": "bathroom",
            "activity": "at the vanity at the end of the night taking the makeup "
                        "off, everything used and out of place",
            "pose": "leaning close to the mirror, one hand at her cheek",
            "interaction": "", "framing": "chest_up", "lighting": "warm-lamp",
            "time_of_day": "late-night",
            "holder": "mirror", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "cant-sleep": {
            "label": "Can't sleep", "place": "balcony",
            "activity": "out on the balcony in the middle of the night, the city "
                        "mostly dark, a few windows still lit",
            "pose": "forearms on the railing, looking out at nothing",
            "interaction": "both-looking-elsewhere",
            "framing": "waist_up", "lighting": "streetlight-sodium",
            "time_of_day": "late-night",
            "holder": "timer", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
    },

    "Weather & season": {
        "first-rain": {
            "label": "The first rain", "place": "balcony",
            "activity": "standing out as the first proper rain comes down, "
                        "everything darkening and running with water",
            "pose": "one hand out past the railing into it, looking up",
            "interaction": "sharing-an-umbrella",
            "framing": "waist_up", "lighting": "overcast-flat",
            "time_of_day": "afternoon",
            "holder": "friend", "flaws": "snapshot", "shot_type": "candid",
            "min_cast": 1},
        "flooded-street": {
            "label": "A flooded street", "place": "reg_street",
            "activity": "water standing across the whole road, traffic pushing "
                        "through it, everyone picking their way along the edge",
            "pose": "stepping carefully, one hand holding her hem clear",
            "interaction": "one-leading-by-the-hand",
            "framing": "full_body", "lighting": "overcast-flat",
            "time_of_day": "afternoon",
            "holder": "friend", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
        "winter-morning": {
            "label": "A winter morning", "place": "terrace",
            "activity": "out in the cold early with everything hazy and grey, "
                        "hands wrapped round a cup for the heat",
            "pose": "shoulders up against the cold, cup held at her chest",
            "interaction": "sitting-close-knees-touching",
            "framing": "chest_up", "lighting": "overcast-flat",
            "time_of_day": "dawn",
            "holder": "friend", "flaws": "subtle", "shot_type": "candid",
            "min_cast": 1},
        "the-hottest-part-of-the-day": {
            "label": "The hottest hour", "place": "reg_street",
            "activity": "the road bleached and empty at the worst hour, everyone "
                        "who can staying in the shade",
            "pose": "one hand up shading her eyes, squinting down the road",
            "interaction": "three-huddled-against-weather",
            "framing": "knee_up", "lighting": "hard-sun", "time_of_day": "midday",
            "holder": "friend", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
        "festive-lights": {
            "label": "Festive lights", "place": "reg_street",
            "activity": "the street strung with lights and decoration for the "
                        "season, crowds out late, everything busy",
            "pose": "looking up at the lights strung overhead",
            "interaction": "three-walking-abreast",
            "framing": "waist_up", "lighting": "string-lights",
            "time_of_day": "evening",
            "holder": "friend", "flaws": "snapshot", "shot_type": "street",
            "min_cast": 1},
    },

    "Portrait": {
        "just-a-portrait": {
            "label": "Just a portrait", "place": "",
            "activity": "nothing happening at all — a photograph taken because "
                        "somebody wanted one",
            "pose": "square to the camera, head level, looking into the lens",
            "interaction": "both-to-camera",
            "framing": "head_shoulders", "lighting": "soft-window",
            "time_of_day": "afternoon",
            "holder": "friend", "flaws": "", "shot_type": "editorial",
            "min_cast": 1},
        "against-a-wall": {
            "label": "Against a wall", "place": "",
            "activity": "standing against a plain sunlit wall, nothing else in "
                        "the frame, one hard shadow beside her",
            "pose": "back against the wall, hands behind her, chin level",
            "interaction": "one-behind-the-other",
            "framing": "waist_up", "lighting": "hard-sun", "time_of_day": "afternoon",
            "holder": "friend", "flaws": "", "shot_type": "editorial",
            "min_cast": 1},
        "in-a-doorway": {
            "label": "In a doorway", "place": "entryway",
            "activity": "framed in a doorway with the room behind her darker than "
                        "the light she is standing in",
            "pose": "one shoulder against the frame, weight on one hip",
            "interaction": "one-in-focus-one-behind",
            "framing": "knee_up", "lighting": "backlit-rim",
            "time_of_day": "mid-morning",
            "holder": "timer", "flaws": "subtle", "shot_type": "editorial",
            "min_cast": 1},
        "the-close-one": {
            "label": "Close", "place": "",
            "activity": "close enough that the frame is only her face and the "
                        "light falling across it",
            "pose": "head level, eyes on the lens, nothing else happening",
            "interaction": "heads-together",
            "framing": "close_up", "lighting": "soft-window",
            "time_of_day": "afternoon",
            "holder": "friend", "flaws": "", "shot_type": "editorial",
            "min_cast": 1},
        "from-behind-looking-out": {
            "label": "From behind", "place": "balcony",
            "activity": "photographed from behind looking out over the city, the "
                        "picture about the view and the posture rather than a face",
            "pose": "forearms on the railing, back to the camera",
            "interaction": "one-turning-back",
            "framing": "from_behind", "lighting": "golden-hour",
            "time_of_day": "golden",
            "holder": "friend", "flaws": "subtle", "shot_type": "editorial",
            "min_cast": 1},
    },
}
