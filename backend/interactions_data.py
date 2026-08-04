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
- Written so it can be dropped into a prompt verbatim. "A" and "B" name the cast
  in mention order and are substituted for the real image tags at build time —
  the model cannot resolve a name but can resolve @image1.
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
    },
}
