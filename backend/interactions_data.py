"""How two people stand near each other — the pose library for a CAST.

Every one of the 551 entries in `poses_data.py` describes one body: "shoulders
squared to the camera", "head tilted to the right shoulder". None of them can say
that two people are touching, or that one is listening to the other. So a scene
with a cast had no vocabulary for the thing that actually makes it read as two
people who know each other rather than two people who happen to be in frame.

Same shape and rules as the pose library:

- The text describes ARRANGEMENT and ACTION, never anyone's face or body. Identity
  comes from the references; describing a person here would cost 0.86 -> 0.53, the
  measurement the whole pipeline is built around.
- Written so it can be dropped into a prompt verbatim. "A", "B" and "C" name the
  cast in mention order and are substituted for the real image tags at build time
  — the model cannot resolve a name but can resolve @image1.

  They are matched on a WORD BOUNDARY, so "All", "Both" and "Caught" are safe to
  write. The one thing that is not: a standalone capital A used as the English
  article, which would be substituted as if it named the first character. Start
  such a sentence with "One of them" instead.
- `min_cast` is the gate. An interaction is offered only when the cast is at least
  that big, so a solo scene never sees a two-person pose.

THE ARRANGEMENT IS AN IDENTITY LEVER, AND A BIG ONE. Measured 2026-08-04, same
two characters, same brief, same getup, same light, same seed, one field changed:

                        Kiara            Ridhi
    cheek-to-cheek      0.118            0.228     both REJECTED
    both-to-camera      0.572            0.588     Ridhi KEPT

Five times the score for Kiara, from a dropdown. Nothing else moved — faces were
840-1040px in both, well above the plateau, and distinctness ruled out blending
either time. The cause is yaw: pressing two faces cheek to cheek turns both heads
30-36 degrees off axis, and corr(|yaw|, sim) = -0.761.

So the categories are not interchangeable, and it is worth knowing which way each
one pushes before choosing it:

    Posed        heads to the lens          best case for the gate
    Close        heads together and turned  costly, sometimes very
    Talking      turned toward each other   costly
    Candid       nobody facing the camera   costly by definition
    Walking      varies with the entry

None of that is a reason to prefer Posed. A year of squared-up group photographs
is not a record of a life, and the gate reporting `rejected` on a genuinely
candid frame is the gate working. It is a reason to know what a choice costs, and
to shoot a frontal frame of the same pairing when the point is to prove identity
rather than to make a picture.
"""

INTERACTIONS: dict[str, dict[str, dict]] = {

    # The ones that read as intimacy — people who are comfortable standing close.
    "Close": {
        "arm-around-shoulder": {
            "text": "A has an arm draped around B's shoulders, the two of them "
                    "leaning into each other, both turned toward the camera.",
            "min_cast": 2},
        "heads-together": {
            "text": "The two of them stand shoulder to shoulder with their heads "
                    "tipped in until they nearly touch, both smiling at the lens.",
            "min_cast": 2},
        "linked-arms": {
            "text": "A and B stand side by side with their arms linked at the "
                    "elbow, bodies angled slightly toward one another.",
            "min_cast": 2},
        "one-hand-on-back": {
            "text": "A rests a hand lightly on B's upper back, both standing "
                    "square to the camera in a relaxed, unposed way.",
            "min_cast": 2},
        "hug-mid-embrace": {
            "text": "Caught mid-hug, arms around each other, one face visible "
                    "over the other's shoulder toward the camera.",
            "min_cast": 2},
        "sitting-close-knees-touching": {
            "text": "Both seated close together, knees almost touching, turned "
                    "slightly inward toward each other.",
            "min_cast": 2},
        "head-on-shoulder": {
            "text": "B has her head resting on A's shoulder, both settled and "
                    "still, looking in the same direction.",
            "min_cast": 2},
        "arms-around-waist": {
            "text": "Standing front to front with arms loosely around each "
                    "other's waists, heads turned toward the camera.",
            "min_cast": 2},
        "cheek-to-cheek": {
            "text": "Faces pressed side by side, cheek against cheek, both "
                    "squeezed into the same part of the frame.",
            "min_cast": 2},
        "holding-hands": {
            "text": "Standing side by side holding hands between them, the join "
                    "clearly visible, both facing forward.",
            "min_cast": 2},
        "one-hand-on-forearm": {
            "text": "B has one hand resting on A's forearm, a small steadying "
                    "contact while they both look ahead.",
            "min_cast": 2},
        "leaning-back-into": {
            "text": "B leans her back against A's front, A's arms crossed loosely "
                    "in front of her, both facing the camera.",
            "min_cast": 2},
        "forehead-to-forehead": {
            "text": "Foreheads touching, eyes down or closed, neither looking at "
                    "the camera.",
            "min_cast": 2},
        "hug-from-behind": {
            "text": "A comes around B from behind with both arms, B's hands "
                    "resting over A's forearms.",
            "min_cast": 2},
        "wrapped-in-one-shawl": {
            "text": "Both pulled in under one shawl or blanket, shoulders "
                    "overlapping inside it.",
            "min_cast": 2},
        "hands-clasped-between": {
            "text": "Facing each other with both pairs of hands clasped together "
                    "between them at chest height.",
            "min_cast": 2},
        "one-tucking-the-others-collar": {
            "text": "A reaches over to straighten B's collar; B stands still for "
                    "it, chin lifted slightly out of the way.",
            "min_cast": 2},
        "one-leaning-on-the-other-seated": {
            "text": "Both seated, B slumped sideways against A's shoulder, A "
                    "upright and letting her.",
            "min_cast": 2},
        "shoulder-to-shoulder-still": {
            "text": "Standing shoulder pressed to shoulder, both facing forward, "
                    "neither talking.",
            "min_cast": 2},
        "arm-through-arm-close": {
            "text": "One arm threaded through the other's, pulled in tight, "
                    "walking pace stopped for the moment.",
            "min_cast": 2},
        "chin-on-shoulder": {
            "text": "A rests her chin on B's shoulder from behind, both faces "
                    "turned the same way toward the camera.",
            "min_cast": 2},
        "curled-up-together": {
            "text": "Both curled into the same corner of a sofa, legs overlapping, "
                    "nothing between them.",
            "min_cast": 2},
        "pressed-into-a-doorway": {
            "text": "Both crowded into a narrow doorway together, shoulders turned "
                    "to fit, laughing at the squeeze.",
            "min_cast": 2},
        "hands-on-each-others-shoulders": {
            "text": "Facing each other at arm's length with a hand on each other's "
                    "shoulders, mid-conversation.",
            "min_cast": 2},
        "one-pulling-the-other-in": {
            "text": "A reaches out and pulls B into frame by the arm, B half "
                    "off-balance and laughing.",
            "min_cast": 2},
    },

    # Conversation. The tell is that one of them is clearly not talking.
    "Talking": {
        "mid-sentence-turned-in": {
            "text": "A is mid-sentence with one hand raised in a small gesture, "
                    "turned toward B who is listening and watching her face.",
            "min_cast": 2},
        "listening-chin-on-hand": {
            "text": "B rests her chin on one hand, attention entirely on A, who "
                    "is speaking and looking back at her.",
            "min_cast": 2},
        "both-mid-laugh": {
            "text": "Both caught mid-laugh at the same moment, heads tipped back "
                    "slightly, looking at each other rather than the camera.",
            "min_cast": 2},
        "leaning-in-to-hear": {
            "text": "A leans in close to B's ear to say something, B smiling and "
                    "looking off toward the room.",
            "min_cast": 2},
        "across-a-table": {
            "text": "The two of them face each other across a small table, elbows "
                    "resting on it, mid-conversation.",
            "min_cast": 2},
        "one-glancing-away": {
            "text": "A is talking and looking at B, while B's attention has drifted "
                    "to something out of frame.",
            "min_cast": 2},
        "both-talking-at-once": {
            "text": "Both speaking over each other with hands moving, neither "
                    "waiting for a gap.",
            "min_cast": 2},
        "one-explaining-with-hands": {
            "text": "A is describing something with both hands shaping it in the "
                    "air; B watches the hands rather than her face.",
            "min_cast": 2},
        "counting-on-fingers": {
            "text": "A is counting points off on her fingers; B is following "
                    "along, head tilted.",
            "min_cast": 2},
        "interrupted-mid-word": {
            "text": "B has cut in and A has stopped mid-word, mouth still open, "
                    "turning toward her.",
            "min_cast": 2},
        "leaning-across-to-listen": {
            "text": "B leans right across the space between them to hear over the "
                    "noise, one hand cupped near her ear.",
            "min_cast": 2},
        "nodding-along": {
            "text": "B nods steadily while A talks, eyes on her, saying nothing.",
            "min_cast": 2},
        "one-hand-raised-to-stop": {
            "text": "B holds one hand up to stop A mid-sentence; A pauses, "
                    "eyebrows up.",
            "min_cast": 2},
        "telling-a-long-story": {
            "text": "A is well into a long story with both hands going; B has "
                    "settled in, chin propped, listening.",
            "min_cast": 2},
        "sharing-a-secret": {
            "text": "A has her hand half over her mouth, leaning in to B's ear; B "
                    "is already reacting.",
            "min_cast": 2},
        "arguing-a-point": {
            "text": "Both leaned in over the table, each pressing a point, hands "
                    "flat on the surface.",
            "min_cast": 2},
        "agreeing-emphatically": {
            "text": "Both nodding hard at the same time, pointing at each other, "
                    "clearly landing on the same conclusion.",
            "min_cast": 2},
        "asking-a-question": {
            "text": "B has asked something and stopped, head tilted, waiting; A is "
                    "thinking before she answers.",
            "min_cast": 2},
        "talking-while-walking-turned": {
            "text": "Both walking but half turned to each other, more attention on "
                    "the conversation than on where they are going.",
            "min_cast": 2},
        "one-standing-one-seated-talking": {
            "text": "A stands beside B who is seated, bent slightly toward her, "
                    "the two of them mid-conversation.",
            "min_cast": 2},
        "over-a-shoulder-conversation": {
            "text": "B is turned away doing something and talking back over her "
                    "shoulder to A, who is behind her.",
            "min_cast": 2},
        "quiet-conversation-close": {
            "text": "Heads close and voices clearly low, both looking down rather "
                    "than at each other.",
            "min_cast": 2},
        "explaining-on-paper": {
            "text": "A is drawing something out on paper between them; B is bent "
                    "over it following the line of her hand.",
            "min_cast": 2},
        "one-trailing-off": {
            "text": "A has trailed off mid-thought and is looking away; B is still "
                    "waiting for the rest of it.",
            "min_cast": 2},
        "catching-up-after-a-while": {
            "text": "Both talking quickly and at once with a lot to get through, "
                    "leaning toward each other across the gap.",
            "min_cast": 2},
    },

    # Doing something together. Objects give hands a job, which is what stops a
    # two-person shot looking staged.
    "Doing something together": {
        "sharing-a-phone-screen": {
            "text": "Both heads bent over one phone held between them, faces lit "
                    "from below by the screen, absorbed in it.",
            "min_cast": 2},
        "showing-something": {
            "text": "A holds something up to show B, who is leaning in to look at "
                    "it; both hands and attention are on the object.",
            "min_cast": 2},
        "sharing-an-umbrella": {
            "text": "The two of them crowd under a single umbrella, shoulders "
                    "pressed together, one holding it over both.",
            "min_cast": 2},
        "cooking-side-by-side": {
            "text": "Working at the same counter, one stirring and one reaching "
                    "past for something, entirely occupied with the task.",
            "min_cast": 2},
        "carrying-bags-together": {
            "text": "Both carrying bags, one handing something across to the "
                    "other, caught mid-transfer.",
            "min_cast": 2},
        "taking-a-selfie-together": {
            "text": "A holds a phone out at arm's length to take a selfie of them "
                    "both; A and B press their heads together into the frame.",
            "min_cast": 2},
        "pointing-at-something": {
            "text": "A points at something out of frame and B follows her line "
                    "of sight, both looking the same way.",
            "min_cast": 2},
        "reading-the-same-page": {
            "text": "Both bent over the same page held between them, reading "
                    "rather than talking.",
            "min_cast": 2},
        "passing-a-cup": {
            "text": "A hands a cup across to B, caught at the moment both hands "
                    "are on it.",
            "min_cast": 2},
        "one-pouring-for-the-other": {
            "text": "A pours while B holds the cup steady, both watching the "
                    "pour rather than each other.",
            "min_cast": 2},
        "assembling-something": {
            "text": "Both working on the same object from opposite sides, hands "
                    "busy and heads down.",
            "min_cast": 2},
        "one-holding-one-working": {
            "text": "B holds something steady while A works on it, neither "
                    "looking up.",
            "min_cast": 2},
        "folding-laundry-together": {
            "text": "Both folding at the same surface, one shaking something out "
                    "while the other stacks.",
            "min_cast": 2},
        "washing-up-side-by-side": {
            "text": "One washing and one drying at the same sink, a rhythm going "
                    "between them.",
            "min_cast": 2},
        "photographing-each-other": {
            "text": "A is holding a phone up taking a picture of B, who is posing "
                    "for it and not for this camera.",
            "min_cast": 2},
        "looking-at-a-screen-together": {
            "text": "Both turned to the same laptop screen, one pointing at "
                    "something on it.",
            "min_cast": 2},
        "trying-something-on": {
            "text": "B is trying something on and A is standing back with her head "
                    "tilted, assessing it.",
            "min_cast": 2},
        "sharing-headphones": {
            "text": "One earphone each from the same pair, the cord running "
                    "between them, both still.",
            "min_cast": 2},
        "measuring-something": {
            "text": "Both holding opposite ends of the same tape or length of "
                    "fabric, pulled taut between them.",
            "min_cast": 2},
        "carrying-something-heavy": {
            "text": "Both carrying one heavy thing between them, one at each end, "
                    "leaning away from the weight.",
            "min_cast": 2},
        "one-teaching-the-other": {
            "text": "A guides B's hands through something; B is concentrating "
                    "entirely on her own hands.",
            "min_cast": 2},
        "watering-plants": {
            "text": "Both working along a row of plants, one watering and one "
                    "moving pots, half turned from each other.",
            "min_cast": 2},
        "packing-a-bag-together": {
            "text": "One packing and one handing things over, an open bag between "
                    "them and a pile beside it.",
            "min_cast": 2},
        "one-fixing-the-others-sleeve": {
            "text": "A is dealing with B's sleeve or hem; B has her arms out, "
                    "waiting for it to be over.",
            "min_cast": 2},
        "splitting-a-bill": {
            "text": "Both looking at the same slip of paper, one holding it and "
                    "the other pointing at a line on it.",
            "min_cast": 2},
    },

    # Motion. Bodies mid-stride read as a moment rather than a photograph.
    "Walking": {
        "side-by-side-walking": {
            "text": "Walking side by side in step, both mid-stride, talking as "
                    "they go.",
            "min_cast": 2},
        "one-turning-back": {
            "text": "Both walking away from the camera, one half-turned back over "
                    "her shoulder toward it.",
            "min_cast": 2},
        "one-leading-by-the-hand": {
            "text": "A walks ahead pulling B along by the hand, B a half-step "
                    "behind and laughing.",
            "min_cast": 2},
        "crossing-a-street": {
            "text": "The two of them crossing a street together mid-stride, "
                    "traffic and buildings behind them.",
            "min_cast": 2},
        "climbing-stairs": {
            "text": "Both on a flight of stairs at different steps, one looking "
                    "back down at the other.",
            "min_cast": 2},
        "walking-toward-camera": {
            "text": "Both walking straight toward the camera in step, mid-stride, "
                    "talking as they come.",
            "min_cast": 2},
        "one-ahead-one-behind": {
            "text": "A is several steps ahead and B is trailing, the gap between "
                    "them clearly visible.",
            "min_cast": 2},
        "running-a-few-steps": {
            "text": "Both breaking into a short run for something, arms up, "
                    "slightly blurred.",
            "min_cast": 2},
        "walking-arm-in-arm": {
            "text": "Walking with arms linked at the elbow, matching pace, heads "
                    "turned toward each other.",
            "min_cast": 2},
        "stopping-to-look-back": {
            "text": "A has stopped and turned back; B is still walking on, a few "
                    "steps past her.",
            "min_cast": 2},
        "going-down-steps": {
            "text": "Both descending a flight of steps, one holding the rail, the "
                    "other a step below and turned back.",
            "min_cast": 2},
        "hurrying-through-a-crowd": {
            "text": "Both pushing through a crowd, one leading, the other close "
                    "behind and half obscured.",
            "min_cast": 2},
        "stepping-around-a-puddle": {
            "text": "Both picking their way around standing water, one hand out "
                    "for balance, hems lifted.",
            "min_cast": 2},
        "walking-a-narrow-path": {
            "text": "Single file along something too narrow for two, the one "
                    "behind watching where the one in front puts her feet.",
            "min_cast": 2},
        "boarding-something": {
            "text": "One already stepping up and in, the other waiting to follow, "
                    "both mid-movement.",
            "min_cast": 2},
        "walking-and-eating": {
            "text": "Walking side by side with food in hand, both eating and "
                    "moving at once.",
            "min_cast": 2},
        "one-carrying-more": {
            "text": "Both walking, one loaded with almost everything and the "
                    "other carrying nothing, clearly noticed.",
            "min_cast": 2},
        "turning-a-corner": {
            "text": "Caught turning a corner together, both leaning into the "
                    "turn, the street opening up ahead.",
            "min_cast": 2},
        "walking-in-rain": {
            "text": "Both hurrying through rain with heads down and shoulders up, "
                    "one half a step ahead.",
            "min_cast": 2},
        "strolling-slowly": {
            "text": "Walking as slowly as it is possible to walk, in no hurry, "
                    "talking the whole way.",
            "min_cast": 2},
        "one-walking-backwards": {
            "text": "A walks backwards facing B so she can keep talking; B walks "
                    "forward watching her not fall over.",
            "min_cast": 2},
        "pausing-at-a-window": {
            "text": "Both stopped at a shop window, one already moving on and one "
                    "still looking.",
            "min_cast": 2},
        "stepping-off-a-kerb": {
            "text": "Both stepping down off a kerb into the road, looking the "
                    "same way for traffic.",
            "min_cast": 2},
        "leaving-a-doorway": {
            "text": "Both coming out through a doorway into brighter light, one "
                    "holding it for the other.",
            "min_cast": 2},
        "walking-with-a-bag-between": {
            "text": "Both walking with one bag carried between them, a handle in "
                    "each hand, matching pace out of necessity.",
            "min_cast": 2},
    },

    # Unposed. Nobody is performing for the lens.
    "Candid": {
        "one-laughing-at-the-other": {
            "text": "B has said something and A is laughing properly at it, "
                    "neither of them looking at the camera.",
            "min_cast": 2},
        "caught-mid-gesture": {
            "text": "Both caught mid-movement and slightly blurred, entirely "
                    "unaware of the camera.",
            "min_cast": 2},
        "one-in-focus-one-behind": {
            "text": "A is close to the camera and sharp; B is a step behind and "
                    "softly out of focus, doing her own thing.",
            "min_cast": 2},
        "both-looking-elsewhere": {
            "text": "The two of them are near each other but attending to "
                    "different things, neither aware of the lens.",
            "min_cast": 2},
        "waiting-together": {
            "text": "Standing near each other waiting, one on her phone, the "
                    "other looking off down the road.",
            "min_cast": 2},

        # Three, unposed. Until these existed a cast of three could only be
        # offered `three-in-a-row` and `three-clustered` — both Posed, both
        # looking down the lens — so there was no way to ask for three people
        # who simply had not noticed the camera. The moment library is full of
        # scenes that want exactly that.
        #
        # A, B and C are assigned in mention order, so whoever is named first in
        # the brief is the one talking, laughing hardest or turned away. Where
        # the roles are interchangeable the text says "one of them" instead and
        # lets the model choose — naming a role that does not matter only
        # invents a constraint the brief has to fight.
        "three-mid-conversation": {
            "text": "A is mid-sentence with one hand raised in a small gesture; "
                    "B and C are both turned toward her, listening. None of them "
                    "is looking at the camera.",
            "min_cast": 3},
        "three-one-laughing-hardest": {
            "text": "All three are laughing at once — A hardest, her head tipped "
                    "back — while B and C watch her rather than the lens.",
            "min_cast": 3},
        "three-eating-and-talking": {
            "text": "The three of them eat and talk over one another, hands and "
                    "food in the way, attention entirely on each other and not "
                    "on the camera.",
            "min_cast": 3},
        "three-two-together-one-away": {
            "text": "A and B are absorbed in something between them while C has "
                    "turned to look at something out of frame; none of the three "
                    "is aware of the camera.",
            "min_cast": 3},
        "three-heads-over-one-phone": {
            "text": "All three crowd around a single phone held between them, "
                    "heads at three different heights, faces lit from below by "
                    "the screen.",
            "min_cast": 3},
        "mid-yawn": {
            "text": "A is caught mid-yawn with her hand not quite up in time; B "
                    "has noticed and is amused.",
            "min_cast": 2},
        "one-checking-the-time": {
            "text": "B glances down at the time while A is still talking, not "
                    "quite hiding it.",
            "min_cast": 2},
        "eating-mid-bite": {
            "text": "Both caught mid-bite with their hands full, neither ready to "
                    "be photographed.",
            "min_cast": 2},
        "reacting-to-something-offscreen": {
            "text": "Both turned sharply toward something out of frame, the same "
                    "expression arriving on both at once.",
            "min_cast": 2},
        "one-fixing-her-own-clothes": {
            "text": "B is sorting out her own hem or strap while A waits, looking "
                    "off elsewhere.",
            "min_cast": 2},
        "half-out-of-frame": {
            "text": "A is fully in shot and B is only half in it at the edge, cut "
                    "off by the crop, unaware.",
            "min_cast": 2},
        "blinking-badly-timed": {
            "text": "Caught at the wrong instant — one with her eyes half closed, "
                    "the other mid-word.",
            "min_cast": 2},
        "sneezing-or-coughing": {
            "text": "A has turned away into her elbow; B has leaned back out of "
                    "the way, laughing.",
            "min_cast": 2},
        "one-not-ready": {
            "text": "B is composed and looking at the lens; A had no idea the "
                    "picture was being taken.",
            "min_cast": 2},
        "in-the-middle-of-moving": {
            "text": "Both in the middle of getting up or sitting down, nothing "
                    "settled, limbs at odd angles.",
            "min_cast": 2},
        "distracted-by-a-phone": {
            "text": "B is entirely absorbed in her phone while A talks to her "
                    "anyway.",
            "min_cast": 2},
        "shielding-eyes-from-sun": {
            "text": "Both squinting with hands up against the sun, faces "
                    "half-shadowed.",
            "min_cast": 2},
        "caught-arriving": {
            "text": "A is already in the room and settled; B is only just coming "
                    "in behind her, still in motion.",
            "min_cast": 2},
        "laughing-at-a-bad-photo": {
            "text": "Both looking down at a screen and reacting to what is on it, "
                    "one covering her face.",
            "min_cast": 2},
        "waiting-and-bored": {
            "text": "Both visibly waiting with nothing to do, leaning on "
                    "different things, not talking.",
            "min_cast": 2},
    },

    # Disagreement, distance, and the moments that are not warm. A year of a
    # life that contains only laughing and linked arms reads as an advertisement.
    # These are the ones that make a set look like a record of people who
    # actually know each other.
    "Tension": {
        "turned-away": {
            "text": "A has turned away mid-conversation and B is still looking at "
                    "her, the space between them wider than it was.",
            "min_cast": 2},
        "arms-folded-listening": {
            "text": "B stands with her arms folded, listening to A without "
                    "agreeing, weight settled back on one hip.",
            "min_cast": 2},
        "one-consoling": {
            "text": "A has a hand on B's arm and is leaning in; B is looking down "
                    "and away, not at the camera.",
            "min_cast": 2},
        "talking-past-each-other": {
            "text": "Both talking at once and neither listening, hands moving, "
                    "attention on their own point.",
            "min_cast": 2},
        "waiting-for-an-answer": {
            "text": "A has said something and stopped; B has not replied yet, and "
                    "the pause is visible in both of them.",
            "min_cast": 2},
        "goodbye-at-a-door": {
            "text": "One half through a doorway, the other still inside, both "
                    "mid-sentence in the last thing said before leaving.",
            "min_cast": 2},
        "sitting-apart-on-one-sofa": {
            "text": "Both on the same sofa but at opposite ends, a clear gap "
                    "between them, neither filling it.",
            "min_cast": 2},
        "one-walking-out": {
            "text": "A is leaving the frame and B has not moved to follow, still "
                    "facing where she was.",
            "min_cast": 2},
        "not-looking-up": {
            "text": "A is saying something and B has not lifted her eyes from "
                    "what is in front of her.",
            "min_cast": 2},
        "back-turned-mid-argument": {
            "text": "B has turned her back and stayed there; A is still facing "
                    "her, hands half raised.",
            "min_cast": 2},
        "one-apologising": {
            "text": "A leans in with both hands open, clearly apologising; B is "
                    "turned partly away and not yet answering.",
            "min_cast": 2},
        "cold-politeness": {
            "text": "Both upright and correct with a careful distance between "
                    "them, saying the minimum.",
            "min_cast": 2},
        "one-comforting-after": {
            "text": "B is sitting with her head down and A has crouched beside "
                    "her, one hand on her back.",
            "min_cast": 2},
        "eyes-meeting-across": {
            "text": "Both across a room from each other, a look passing between "
                    "them that nobody else in the frame is part of.",
            "min_cast": 2},
        "one-holding-back-tears": {
            "text": "B is looking hard at the ceiling to keep it together and A "
                    "has noticed and gone quiet.",
            "min_cast": 2},
        "unfinished-sentence": {
            "text": "A has said something and stopped; neither A nor B is looking "
                    "at the other.",
            "min_cast": 2},
        "one-blocking-the-way": {
            "text": "A stands in the doorway and B has stopped short in front of "
                    "her, neither moving aside.",
            "min_cast": 2},
        "phone-put-face-down": {
            "text": "B turns her phone face down on the table without answering "
                    "it; A has watched her do it.",
            "min_cast": 2},
        "waiting-to-be-let-in": {
            "text": "A is on one side of a doorway and B on the other, the "
                    "threshold clearly not crossed.",
            "min_cast": 2},
        "reconciling-awkwardly": {
            # Started as "A half-hug that neither..." — the English article, which
            # the word-boundary substitution cannot tell from the placeholder and
            # would have sent as "@image1 half-hug". The exact trap the module
            # docstring warns about, walked into while writing the docstring's own
            # library. Rephrased so no standalone capital A survives.
            "text": "Half a hug, and neither of them has fully committed to it; "
                    "both slightly out of position.",
            "min_cast": 2},
        "one-explaining-to-a-wall": {
            "text": "A is explaining at length; B has stopped listening some time "
                    "ago and is not hiding it.",
            "min_cast": 2},
        "sitting-in-silence": {
            "text": "Both seated, both still, neither talking, and it has "
                    "clearly been like that for a while.",
            "min_cast": 2},
        "one-leaving-the-table": {
            "text": "B is standing up and gathering her things; A is still seated, "
                    "looking up at her.",
            "min_cast": 2},
        "half-turned-away-listening": {
            "text": "B is turned mostly away but her head is angled back — "
                    "listening without facing it.",
            "min_cast": 2},
        "tense-in-a-crowd": {
            "text": "Both surrounded by people and clearly not part of the room's "
                    "mood, standing closer to each other than to anyone else.",
            "min_cast": 2},
    },

    # Hands full, attention elsewhere. Objects are what stop a group shot looking
    # like a group shot.
    "Errands & tasks": {
        "queueing-together": {
            "text": "Standing in a queue one behind the other, one leaning "
                    "sideways to see how far ahead it goes.",
            "min_cast": 2},
        "reading-the-same-thing": {
            "text": "Both bent over the same piece of paper or menu held between "
                    "them, heads close, reading rather than talking.",
            "min_cast": 2},
        "paying-at-a-counter": {
            "text": "One paying at a counter while the other waits beside her "
                    "holding what they bought.",
            "min_cast": 2},
        "choosing-between-two": {
            "text": "A holds up two things, one in each hand, and B is looking "
                    "between them deciding.",
            "min_cast": 2},
        "helping-with-a-strap": {
            "text": "A is fixing something on B — a strap, a collar, a stray "
                    "thread — and B is standing still for it, looking elsewhere.",
            "min_cast": 2},
        "loading-a-vehicle": {
            "text": "Both handing things into a vehicle, one inside and one out, "
                    "caught mid-pass.",
            "min_cast": 2},
        "checking-a-list": {
            "text": "A holds a list and B is looking over her arm at it, both "
                    "reading rather than talking.",
            "min_cast": 2},
        "weighing-produce": {
            "text": "Both at a stall watching something being weighed, attention "
                    "entirely on the scale.",
            "min_cast": 2},
        "hailing-something": {
            "text": "A has her arm out flagging something down; B stands beside "
                    "her with the bags.",
            "min_cast": 2},
        "counting-out-change": {
            "text": "Both looking down at coins and notes counted out into one "
                    "palm between them.",
            "min_cast": 2},
        "waiting-at-a-counter": {
            "text": "Both leaning on a counter waiting for something to be "
                    "brought out, neither talking.",
            "min_cast": 2},
        "reading-a-sign": {
            "text": "Both stopped and looking up at the same sign, one pointing "
                    "at a line of it.",
            "min_cast": 2},
        "asking-for-directions": {
            "text": "Both turned to someone out of frame, one talking and one "
                    "looking the way that is being indicated.",
            "min_cast": 2},
        "unloading-shopping": {
            "text": "Bags coming out and onto a surface, one lifting and one "
                    "sorting what has already landed.",
            "min_cast": 2},
        "trying-to-fit-it-all-in": {
            "text": "Both pressing things into a bag that is clearly too small, "
                    "four hands involved.",
            "min_cast": 2},
        "returning-something": {
            "text": "A holds an item out across a counter while B stands beside "
                    "her holding the receipt.",
            "min_cast": 2},
        "picking-up-a-parcel": {
            "text": "One signing for something while the other takes the weight "
                    "of it in both arms.",
            "min_cast": 2},
        "queue-not-moving": {
            "text": "Both in a queue that has stopped, one craning to see ahead, "
                    "the other resigned.",
            "min_cast": 2},
        "comparing-two-things": {
            "text": "Each holding a different option up beside the other, heads "
                    "tilted, deciding between them.",
            "min_cast": 2},
        "filling-a-form": {
            "text": "Both bent over the same form on a counter, one writing and "
                    "one reading out what goes where.",
            "min_cast": 2},
        "carrying-flowers": {
            "text": "Both carrying something awkward and bulky between them, "
                    "adjusting their grip as they go.",
            "min_cast": 2},
        "one-holding-a-place": {
            "text": "A stays holding their place while B goes off to fetch "
                    "something, both looking in different directions.",
            "min_cast": 2},
        "reading-a-receipt": {
            "text": "Both looking down the length of a receipt held between them, "
                    "one running a finger down it.",
            "min_cast": 2},
        "loading-a-lift": {
            "text": "Both getting into a small lift with more than they can "
                    "comfortably carry, pressed to the back wall.",
            "min_cast": 2},
        "locking-up": {
            "text": "A is locking a door while B waits a step behind with "
                    "everything in her hands.",
            "min_cast": 2},
    },

    # Three, unposed and doing something. The Candid group covers three people
    # who have not noticed the camera; these are three people with a task.
    "Three together": {
        "three-round-a-table": {
            "text": "All three around a small table with things spread between "
                    "them, two talking and one reaching across.",
            "min_cast": 3},
        "three-walking-abreast": {
            "text": "All three walking abreast and in step, the middle one turned "
                    "slightly toward one side, talking.",
            "min_cast": 3},
        "three-one-behind-two": {
            "text": "Two of them close together in front with the third just "
                    "behind and between, leaning in over their shoulders.",
            "min_cast": 3},
        "three-passing-something": {
            "text": "Something is being handed along the three of them, caught at "
                    "the moment it is between two pairs of hands.",
            "min_cast": 3},
        "three-two-talking-one-arriving": {
            "text": "Two of them mid-conversation as the third arrives into the "
                    "frame from one side, not yet part of it.",
            "min_cast": 3},
        "three-huddled-against-weather": {
            "text": "All three pressed close under one cover against the weather, "
                    "shoulders overlapping, faces turned in.",
            "min_cast": 3},
        "three-arms-linked": {
            "text": "All three walking with arms linked in a row, the middle one "
                    "joined to both.",
            "min_cast": 3},
        "three-in-a-triangle": {
            "text": "All three standing turned inward to each other in a loose "
                    "triangle, mid-conversation, none facing the camera.",
            "min_cast": 3},
        "three-two-seated-one-standing": {
            "text": "Two of them seated and the third standing beside them with a "
                    "hand on the back of a chair, all three talking.",
            "min_cast": 3},
        "three-on-a-sofa": {
            "text": "All three along one sofa at different angles, the middle one "
                    "turned to whichever side is talking.",
            "min_cast": 3},
        "three-cheersing": {
            "text": "All three lifting cups or glasses in toward one point above "
                    "the table, hands meeting in the middle.",
            "min_cast": 3},
        "three-one-in-the-middle": {
            "text": "B stands between A and C with an arm around each, all three "
                    "pressed together.",
            "min_cast": 3},
        "three-crowded-round-a-mirror": {
            "text": "All three trying to fit into the same mirror, one crouching "
                    "so the others can see past.",
            "min_cast": 3},
        "three-carrying-between-them": {
            "text": "All three carrying one awkward thing between them, spread "
                    "along its length.",
            "min_cast": 3},
        "three-heads-in-a-row": {
            "text": "All three lined up at slightly different heights, heads "
                    "close, everyone looking the same way.",
            "min_cast": 3},
        "three-one-crouching": {
            "text": "Two standing and one crouched in front of them, all three "
                    "arranged to fit into the same frame.",
            "min_cast": 3},
        "three-in-a-doorway": {
            "text": "All three crowded into one doorway, overlapping heavily, "
                    "nobody willing to step back.",
            "min_cast": 3},
        "three-sharing-food": {
            "text": "One plate in the middle and three sets of hands going to it, "
                    "all three leaning in.",
            "min_cast": 3},
        "three-getting-ready": {
            "text": "All three occupied with different parts of getting ready in "
                    "the same space, none of them looking up.",
            "min_cast": 3},
        "three-one-explaining-to-two": {
            "text": "A is explaining something with her hands; B and C are both "
                    "turned to her, listening.",
            "min_cast": 3},
        "three-different-directions": {
            "text": "All three facing different ways in the same frame, each "
                    "attending to something the others are not.",
            "min_cast": 3},
        "three-piling-in": {
            "text": "All three squeezing into the back of the same vehicle, "
                    "half-seated and rearranging.",
            "min_cast": 3},
        "three-around-a-counter": {
            "text": "All three standing around the same counter working on "
                    "different parts of one task.",
            "min_cast": 3},
        "three-leaning-on-a-railing": {
            "text": "All three along the same railing on their forearms, spaced "
                    "unevenly, looking out.",
            "min_cast": 3},
        "three-one-taking-the-photo": {
            "text": "A holds the phone out for a selfie of all three; B and C "
                    "lean in from either side to make the frame.",
            "min_cast": 3},
    },

    # Four and up. A group photograph is a different problem from a two-hander:
    # the failure is no longer blending, it is faces at the back landing under
    # the gate's floor. min_cast keeps these away from smaller casts, and the
    # framing library's face-size estimate is what says whether they are gateable.
    "Group": {
        "group-in-a-line": {
            "text": "All of them in one row facing the camera, shoulders "
                    "overlapping, arms behind each other's backs.",
            "min_cast": 4},
        "group-clustered-tight": {
            "text": "All of them crowded into the frame at different heights, "
                    "everyone looking at the lens, nobody quite centred.",
            "min_cast": 4},
        "group-round-a-table": {
            "text": "All of them around one table, some turned to the camera and "
                    "some still talking to each other.",
            "min_cast": 4},
        "group-mid-laugh": {
            "text": "The whole group caught laughing at the same thing, nobody "
                    "looking at the camera, several half-blurred.",
            "min_cast": 4},
        "group-walking-toward": {
            "text": "All of them walking toward the camera in a loose line, mid-"
                    "stride and unevenly spaced.",
            "min_cast": 4},
        "group-one-taking-it": {
            "text": "One of them holds the phone out at arm's length and the rest "
                    "crowd in behind her to fit in the frame.",
            "min_cast": 4},
        "group-two-rows": {
            "text": "The group arranged in two rows, the front row lower than the "
                    "back, everyone's face clear of the one in front.",
            "min_cast": 4},
        "group-arms-around": {
            "text": "All of them in a line with arms across each other's backs, "
                    "pulled tight enough to fit the frame.",
            "min_cast": 4},
        "group-on-steps": {
            "text": "The group spread across a flight of steps at different "
                    "heights, all turned toward the camera.",
            "min_cast": 4},
        "group-crowded-on-a-sofa": {
            "text": "All of them packed onto one sofa, some seated and some on "
                    "the arms, nobody with much room.",
            "min_cast": 4},
        "group-half-not-ready": {
            "text": "Half the group is looking at the camera and the other half "
                    "has not noticed it yet.",
            "min_cast": 4},
        "group-around-a-cake": {
            "text": "All of them leaning in around one lit cake, faces lit from "
                    "below, the rest of the room dark.",
            "min_cast": 4},
        "group-jumping": {
            "text": "The whole group caught mid-jump at slightly different "
                    "heights, arms up, several blurred.",
            "min_cast": 4},
        "group-in-a-doorway": {
            "text": "All of them crammed into one doorway, heavily overlapping, "
                    "the ones at the back on tiptoe.",
            "min_cast": 4},
        "group-turning-to-camera": {
            "text": "The group caught in the moment of turning toward the camera, "
                    "some already there and some still moving.",
            "min_cast": 4},
        "group-eating-together": {
            "text": "All of them around one table mid-meal, hands and plates "
                    "everywhere, several conversations at once.",
            "min_cast": 4},
        "group-huddle": {
            "text": "All of them leaned into a tight circle with heads down "
                    "toward the middle, shot from above.",
            "min_cast": 4},
        "group-strung-out-walking": {
            "text": "The group walking in a loose strung-out line rather than "
                    "together, spread across the width of the frame.",
            "min_cast": 4},
        "group-one-in-front": {
            "text": "One of them close to the camera and sharp with the rest "
                    "gathered behind her and softer.",
            "min_cast": 4},
        "group-leaning-on-a-wall": {
            "text": "All of them along the same wall in a row, each leaning "
                    "differently, facing out.",
            "min_cast": 4},
        "group-toasting": {
            "text": "The whole group lifting glasses in toward one point, arms "
                    "crossing over each other.",
            "min_cast": 4},
        "group-goodbye": {
            "text": "The group breaking up to leave, several mid-hug, others "
                    "already turning away.",
            "min_cast": 4},
        "group-watching-something": {
            "text": "All of them turned the same way watching something out of "
                    "frame, nobody aware of the camera.",
            "min_cast": 4},
        "group-crouched-and-standing": {
            "text": "Some crouched at the front and the rest standing behind, "
                    "everyone's face visible.",
            "min_cast": 4},
        "group-squeezing-in": {
            "text": "The group compressing toward the middle so everyone fits, "
                    "the ones on the ends leaning inward hard.",
            "min_cast": 4},
    },

    # Deliberately for the camera — the posed group photograph.
    "Posed": {
        "both-to-camera": {
            "text": "Both standing square to the camera side by side, relaxed, "
                    "looking straight into the lens.",
            "min_cast": 2},
        "one-behind-the-other": {
            "text": "B stands just behind A's shoulder, both faces clearly "
                    "visible and turned to the camera.",
            "min_cast": 2},
        "back-to-back": {
            "text": "Standing back to back with heads turned toward the camera, "
                    "arms folded.",
            "min_cast": 2},
        "seated-and-standing": {
            "text": "A is seated and B stands beside her with a hand on the back "
                    "of the chair, both facing the lens.",
            "min_cast": 2},
        "three-in-a-row": {
            "text": "All three standing in a row, arms around each other's "
                    "shoulders, facing the camera together.",
            "min_cast": 3},
        "three-clustered": {
            "text": "All three clustered close with heads at slightly different "
                    "heights, everyone looking at the lens.",
            "min_cast": 3},
        "three-stepped-depth": {
            "text": "All three at different distances from the camera, staggered "
                    "back one behind the other, all turned to the lens.",
            "min_cast": 3},
        "seated-row": {
            "text": "All of them seated in a row, turned slightly inward toward "
                    "the centre, hands in their laps.",
            "min_cast": 3},
        "one-front-rest-behind": {
            "text": "One of them close to the camera and centred, the others "
                    "arranged behind her shoulders, everyone facing the lens.",
            "min_cast": 3},
        "side-by-side-hands-clasped": {
            "text": "Standing square to the camera with hands clasped in front, "
                    "shoulders just touching.",
            "min_cast": 2},
        "angled-in-toward-each-other": {
            "text": "Both bodies angled inward toward each other with heads "
                    "turned back out to the lens.",
            "min_cast": 2},
        "one-seated-one-leaning": {
            "text": "A is seated square to the camera and B leans in over the "
                    "back of the chair, both looking at the lens.",
            "min_cast": 2},
        "hands-on-hips-both": {
            "text": "Both standing with hands on hips, weight settled, looking "
                    "straight into the lens.",
            "min_cast": 2},
        "arms-crossed-both": {
            "text": "Both with arms crossed, standing squarely, chins level.",
            "min_cast": 2},
        "staggered-depth": {
            "text": "One a step closer to the camera than the other, both turned "
                    "to the lens, the nearer one sharper.",
            "min_cast": 2},
        "profile-and-front": {
            "text": "A stands in full profile and B square to the camera beside "
                    "her, deliberately mismatched.",
            "min_cast": 2},
        "both-looking-up": {
            "text": "Both with chins lifted looking just past the lens, shot from "
                    "slightly below.",
            "min_cast": 2},
        "leaning-on-each-other-back": {
            "text": "Standing back to back, each leaning her weight into the "
                    "other, arms folded, heads turned out to the camera.",
            "min_cast": 2},
        "seated-facing-camera": {
            "text": "Both seated square to the camera at the same height, hands in "
                    "their laps, still.",
            "min_cast": 2},
        "one-hand-on-the-others-shoulder": {
            "text": "A stands slightly behind with one hand on B's shoulder, both "
                    "looking straight ahead.",
            "min_cast": 2},
        "mirrored-stance": {
            "text": "Both in the same stance mirrored — same weight, same angle, "
                    "facing the lens.",
            "min_cast": 2},
        "framed-in-an-opening": {
            "text": "Both standing inside a doorway or arch that frames them, "
                    "centred and facing out.",
            "min_cast": 2},
        "seated-on-steps": {
            "text": "Both seated on steps at different levels, turned toward the "
                    "camera, elbows on knees.",
            "min_cast": 2},
        "three-quarter-turn-both": {
            "text": "Both turned three-quarters away with heads rotated back to "
                    "the lens over the shoulder line.",
            "min_cast": 2},
        "one-kneeling-one-standing": {
            "text": "A on one knee at the front and B standing behind her, both "
                    "squared to the camera.",
            "min_cast": 2},
    },
}


