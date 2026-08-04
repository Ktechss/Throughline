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
            "text": "A holds a phone out at arm's length to take a selfie of "
                    "them both; the two of them press their heads together into "
                    "the frame.",
            "min_cast": 2},
        "pointing-at-something": {
            "text": "A points at something out of frame and B follows her line "
                    "of sight, both looking the same way.",
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
    },
}

