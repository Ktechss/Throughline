"""Add Exotic + Lustful categories to the single-body and cast pose libraries.

These are posing directions in the register a lingerie / boudoir shot list uses:
where the weight sits, where the spine bends, where the eyes go. They describe
BODY POSITION AND MOOD, which is what the generator needs, and nothing else —
the wardrobe is whatever the shot already put her in.

Written to match the house style of poses_data.py: one sentence, present tense,
camera-aware, no adjectives about her face (rule 1 — a reference image carries
that, words only specify a type).

Regenerates both files in place from their imported dicts, so ordering and
formatting stay stable and re-running is idempotent.
"""
import json
import re
from pathlib import Path
import sys

PROJ = Path("/home/ryuk/Projects/Throughline")
sys.path.insert(0, str(PROJ))
from backend import poses_data, interactions_data          # noqa: E402

# ---------------------------------------------------------------- single body

EXOTIC = {
    "arched-spine-standing": "Standing tall with her spine arched deeply backward, chest lifted and both arms reaching overhead, chin following the curve.",
    "serpentine-torso": "Hips pushed to one side and ribs counter-shifted to the other, her torso drawn into a long S-curve, one hand tracing the waist.",
    "floor-arch-back": "Lying on her back with hips lifted clear of the floor, weight on her shoulders and feet, one knee dropped open.",
    "cobra-lift": "Face down on the floor, propped high on straight arms with her spine arched and head tipped back.",
    "kneeling-back-bend": "Kneeling upright with her back arched and both hands reaching behind to her heels, throat exposed to the light.",
    "leg-extended-vertical": "Lying on her side with the top leg extended straight up toward the ceiling, one hand steadying the ankle.",
    "silk-drag": "Standing in profile drawing a length of fabric slowly across her body, the cloth trailing behind her in the air.",
    "fabric-overhead": "Both arms lifted overhead holding a sheer panel of fabric that falls open around her like a canopy.",
    "wind-caught-silhouette": "Standing side-on against the light with fabric lifting away from her body, her outline sharp inside it.",
    "hip-thrown-hard": "Weight dropped hard onto one hip with the opposite leg extended long and pointed, one arm sweeping overhead.",
    "sculptural-crouch": "Crouched low with knees wide and both hands planted between them, spine long and head lifted toward the lens.",
    "shoulder-stand-drape": "On her upper back with legs folded overhead, fabric spilling down toward her shoulders.",
    "table-top-recline": "Reclining backward across a low surface with her head hanging past the edge and hair falling free.",
    "hands-frame-face": "Both hands raised to frame her face from either side, elbows wide and symmetrical, gaze straight down the lens.",
    "twisted-seated-reach": "Seated with legs folded to one side, torso twisted hard the other way, one arm reaching across the floor.",
    "leg-hooked-high": "Standing beside a wall with one leg lifted and hooked against it, hips square to the camera.",
    "prone-legs-crossed-up": "Lying face down on her forearms with both lower legs raised and crossed at the ankles above her.",
    "kneel-lean-far-back": "Kneeling with her weight carried far back onto both hands behind her, hips lifted and chin raised.",
    "diagonal-floor-stretch": "Stretched diagonally across the frame on her side, body drawn into one long unbroken line from fingertips to toes.",
    "elbow-prop-arch": "On her side propped on one elbow with the waist dipped low and hips stacked high above it.",
    "overhead-clasp-lean": "Standing with both hands clasped high overhead and the whole body leaning into a long side bend.",
    "spiral-standing-turn": "Mid-turn with hips facing away and shoulders wound back toward the camera, one arm trailing.",
    "seated-legs-scissor": "Seated on the floor with legs scissored open in a wide V, leaning back on both straight arms.",
    "mirror-floor-arch": "Lying on her back beside a mirror with her spine arched, the reflection doubling the curve.",
    "hair-sweep-back-bend": "Bending backward from the waist with one hand sweeping her hair away from her face.",
    "one-knee-up-arch": "Seated with one knee drawn high and the spine arched away from it, head tipped back.",
    "stretch-cat-pose": "On hands and knees with her chest dropped low toward the floor and hips high, chin lifted forward.",
    "standing-side-extension": "Standing on one leg with the other extended straight out to the side, both arms opened wide for balance.",
    "wall-press-arch": "Back pressed flat to a wall with hips pushed forward and shoulders rolled back, one knee bent.",
    "reclined-throat-line": "Reclining on her elbows with her head dropped fully back, the line of her throat facing the light.",
    "floor-spiral-legs": "On her back with both legs spiralled over to one side and shoulders held flat to the floor.",
    "high-kneel-reach-up": "Up on both knees with one arm stretched straight overhead and the other trailing at her thigh.",
    "veil-across-face": "Standing still with a translucent fabric drawn across the lower half of her face, eyes above it toward the lens.",
    "arm-wrap-turn": "Turning away with one arm wrapped across her own waist and the opposite shoulder dipped low.",
    "supine-legs-vertical": "Flat on her back with both legs raised straight and pressed together, arms flat at her sides.",
    "hip-lift-bridge": "In a low bridge with hips pushed high, feet flat and both arms extended overhead on the floor.",
    "seated-back-arch-hands": "Seated with hands planted behind, chest driven forward and up, head fallen back between her shoulders.",
    "standing-fold-forward": "Folded forward from the hips with hands near the floor, head turned to find the camera sideways.",
    "leg-cross-standing-twist": "Standing with ankles crossed and the torso twisted hard toward the lens, hands loose at her sides.",
    "recline-fabric-pool": "Reclining on one hip with fabric pooled around her, one arm draped along the length of her body.",
    "shoulder-roll-back": "Standing with both shoulders rolled far back and down, chest open, arms hanging long behind the line of her body.",
    "kneel-side-stretch": "Kneeling with one leg extended straight to the side and the torso arced over it, one arm reaching along the leg.",
    "floor-elbow-arch-high": "Propped on both elbows with hips lifted high off the floor and the head dropped back.",
    "spiral-hair-lift": "Both hands buried in her hair lifting it clear of her neck, elbows high, torso twisted to one side.",
    "long-lunge-reach": "Sunk into a long low lunge with the back leg extended flat and both arms reaching forward past her knee.",
    "sit-lean-far-side": "Seated with legs folded and the whole torso leaned far over one hip onto a single supporting hand.",
    "prone-arch-look-back": "Lying on her front, chest raised on straight arms, head turned to look back over her own shoulder.",
    "standing-knee-cross": "Standing with one knee crossed tightly over the other and hips angled, one hand resting at the outer thigh.",
    "reach-to-ceiling-rise": "Rising onto the balls of both feet with both arms stretched their full length toward the ceiling.",
    "floor-frame-legs": "On her back with knees bent and feet flat, arms folded above her head to frame the shot.",
}

LUSTFUL = {
    "over-shoulder-smoulder": "Turned away from the camera with her head rotated back over one bare shoulder, eyes locked on the lens.",
    "lip-touch-glance": "Fingertips resting lightly at her lower lip, chin dipped, eyes lifted to the camera.",
    "strap-off-shoulder": "One hand easing a shoulder strap down her upper arm, head tilted the opposite way, gaze steady.",
    "hair-grasp-back": "One hand gathering her hair at the nape and pulling it back, chin lifted and throat exposed.",
    "reclined-invite": "Lying back on both elbows with knees drawn up and slightly apart, holding the camera's eye.",
    "hand-on-inner-thigh": "Seated with one hand resting high on her own thigh, knees angled toward the lens, gaze level.",
    "eyes-closed-head-back": "Head dropped back with eyes closed and lips just parted, shoulders loose.",
    "kneel-hands-slide-thighs": "Kneeling upright with both hands sliding slowly down the tops of her thighs, eyes on the camera.",
    "collarbone-trace": "One hand tracing along her own collarbone toward the shoulder, head turned slightly away.",
    "bite-lip-side-glance": "Lower lip caught between her teeth, face angled away with eyes cut back toward the lens.",
    "sheet-clutch": "Lying on her side clutching a sheet loosely to her chest, one leg drawn up, looking straight at the camera.",
    "back-to-camera-look": "Standing with her back fully to the camera and her head turned to find the lens over one shoulder.",
    "prone-ankles-crossed": "Lying on her front with ankles crossed in the air behind her, chin propped on both hands, smiling at the lens.",
    "reach-toward-lens": "Lying back with one arm extended slowly toward the camera, fingers relaxed, eyes half-lowered.",
    "hip-tilt-hand-waist": "Standing with one hip pushed out and a hand resting low on her own waist, weight on the opposite leg.",
    "seated-knees-apart-lean": "Seated on the edge of a chair leaning forward, forearms on her knees, gaze up into the lens.",
    "hair-over-one-eye": "Hair fallen forward across one side of her face, chin dipped, the visible eye fixed on the camera.",
    "shoulder-kiss-own": "Head turned down toward her own shoulder with lips almost touching it, eyes raised to the lens.",
    "lying-side-hand-hip": "On her side with one hand resting along the curve of her hip, top leg bent forward, direct gaze.",
    "arch-on-bed": "On her back across a bed with her spine arched and both arms stretched above her head.",
    "robe-slipping": "Standing with a robe fallen open and held loosely closed at the waist by one hand, looking over her shoulder.",
    "chin-lift-eyes-down": "Chin raised high with her eyes lowered toward the camera beneath it, mouth relaxed.",
    "seated-legs-crossed-lean-in": "Seated with legs crossed high at the thigh, leaning in toward the camera with both hands on the front knee.",
    "hands-behind-head-recline": "Reclining with both hands laced behind her head and elbows wide, body long and open.",
    "wall-lean-hip-out": "Leaning one shoulder against a wall with the near hip pushed out toward the camera, head tipped back against it.",
    "kneel-sit-back-arch": "Kneeling and sitting back on her heels with her chest lifted and both hands resting behind her.",
    "finger-hook-strap": "One finger hooked under a strap at her shoulder, held still, eyes steady on the lens.",
    "lying-back-head-tilt": "Flat on her back with her head tilted back toward the camera and hair spilling out around it.",
    "slow-turn-glance": "Caught mid-turn away from the lens with her eyes still holding it and one hand at her waist.",
    "seated-floor-lean-back": "Seated on the floor leaning back onto both hands with legs extended and ankles crossed, chin raised.",
    "hand-through-hair-up": "Both hands pushing up through her hair from the temples, elbows raised, gaze straight ahead.",
    "prone-look-up": "Lying on her front propped on both forearms, shoulders drawn in, looking up into the camera.",
    "thigh-cross-seated": "Seated with one thigh crossed tightly over the other and the top foot pointed, hands resting behind her.",
    "shoulder-forward-lean": "Leaning toward the lens with one shoulder rolled forward and the opposite arm crossing low.",
    "neck-exposed-side": "Head turned fully to one side with the neck long and exposed, eyes closed, shoulders dropped.",
    "sit-legs-tucked-glance": "Sitting with both legs tucked to one side and a hand on the floor, glancing back over her shoulder.",
    "stretch-waking": "Mid-stretch with both arms overhead and her back arched, eyes half open toward the camera.",
    "hands-on-headboard": "Kneeling upright with both hands raised to grip a headboard above her, chin lowered, eyes up.",
    "leg-drawn-up-side": "On her side with the top leg drawn up high toward her chest and one hand holding the shin.",
    "smoulder-direct": "Square to the camera, shoulders relaxed and chin slightly down, holding a long unbroken look into the lens.",
    "back-arch-seated-edge": "Perched on the edge of a surface with her spine arched and both hands gripping the edge beside her hips.",
    "fingers-at-jaw": "Fingertips resting under her jaw and tilting her own face toward the light, gaze angled to the lens.",
    "lying-legs-bent-up": "On her back with both knees bent and feet flat, one hand resting on her stomach, head turned to the camera.",
    "hip-swivel-back-view": "Standing with hips swivelled away and shoulders squared back toward the camera, one hand at the small of her back.",
    "kneel-forward-hands-floor": "On her knees leaning forward onto both hands, shoulders low, eyes lifted straight into the lens.",
    "shoulder-glance-hair-down": "Hair falling loose down her back, head turned so one eye finds the camera past her shoulder.",
    "seated-lean-knees-together": "Seated with knees pressed together and toes turned in, leaning forward with hands between them.",
    "recline-one-arm-overhead": "Reclining with one arm thrown above her head and the other resting along her waist, gaze on the lens.",
    "chin-on-shoulder-back": "Back to the camera with her chin dropped onto her own shoulder, eyes cut sideways to the lens.",
    "slow-sink-crouch": "Sinking into a slow crouch with knees together and both hands sliding down her thighs, eyes forward.",
}

# ------------------------------------------------------------------ cast (2+)
#
# NEVER open a sentence with the article "A". main.py's _validate_moments
# replaces \bA\b with a cast name, so "A single length of fabric" would reach
# the model as "@image1 single length of fabric". The validator rejects any entry
# naming A without also naming B for exactly this reason.
#
# INTERACTIONS entries are {"text": ..., "min_cast": 2}. A and B are the cast in
# the order the scene names them.

EXOTIC_CAST = {
    "mirrored-arches": "A and B stand side by side arching their spines in opposite directions, their bodies forming a single symmetrical shape.",
    "entwined-silhouette": "The two stand pressed close in profile against the light, their outlines reading as one continuous form.",
    "one-high-one-low": "A stands tall with arms raised while B is crouched low at her feet, the two occupying opposite halves of the frame.",
    "shared-fabric-drape": "One length of sheer fabric is draped across both of them, each holding an end and leaning away from the other.",
    "back-arch-support": "B leans backward into A's arms in a deep arch, A taking her weight from behind.",
    "counterbalance-lean": "A and B lean away from one another with hands clasped between them, held up by the opposing weight.",
    "floor-spiral-pair": "Both lie on the floor with heads close together and bodies spiralling outward in opposite directions.",
    "reaching-toward-each-other": "A and B stretch toward each other from opposite sides of the frame, fingertips not quite meeting.",
    "one-lifting-hair": "A stands behind B lifting her hair clear of her neck with both hands, B's chin raised.",
    "stacked-profiles": "The two stand in exact profile one behind the other, only the front figure's face fully visible.",
    "twin-crouch-mirror": "Both crouch low facing each other with knees wide and hands planted, mirroring the same shape.",
    "arms-arch-overhead": "A and B face each other and raise their arms overhead until their fingertips meet in an arch.",
    "seated-back-to-back-arch": "Seated back to back on the floor, both arching away from one another with heads tipped back.",
    "one-draped-over": "B is draped backward over A's supporting arm, her free arm trailing toward the floor.",
    "diagonal-lean-pair": "A and B lean in the same diagonal direction at the same angle, one behind the other.",
    "hands-on-shoulders-line": "A stands behind B with both hands on her shoulders, both faces turned the same way toward the light.",
    "kneeling-facing-arch": "Both kneel facing one another and arch backward simultaneously, hands reaching for their own heels.",
    "wrapped-fabric-turn": "The two turn slowly inside a shared wrap of fabric, wound together at the waist.",
    "lying-head-to-head": "Lying flat with the crowns of their heads touching and bodies extending in opposite directions.",
    "one-standing-one-reclined": "A stands over B, who is reclined at her feet with one arm reaching up along A's leg.",
    "shadow-and-light": "A stands fully in the light and B just behind her in shadow, their poses identical.",
    "twisted-embrace-away": "The two hold each other at the waist while twisting their upper bodies in opposite directions.",
    "linked-overhead-clasp": "Standing shoulder to shoulder with inside arms raised and hands clasped high above them.",
    "one-lifted-off-floor": "A lifts B slightly clear of the floor from behind, B's legs relaxed and pointed.",
    "seated-legs-interlaced": "Seated facing each other on the floor with legs interlaced and both leaning back on their hands.",
    "profile-and-full-face": "A is in exact profile and B is square to the camera directly behind her, the two heads overlapping.",
    "mirrored-hip-tilt": "Both stand with hips thrown toward each other and outside arms sweeping overhead.",
    "crouch-and-tower": "B crouches tight to the floor while A stands directly over her with legs apart.",
    "hair-fall-shared": "The two lean their heads together and let their hair fall forward until it mixes into one mass.",
    "arch-over-lap": "B lies back across A's lap in a deep arch with her head dropped past A's knee.",
    "opposing-spirals": "A and B stand close and spiral their torsos in opposite directions, hips still touching.",
    "one-behind-arms-through": "A stands behind B and threads both arms through under B's, the four arms reading as one set.",
    "floor-tangle-legs": "Both lie on the floor with legs overlapping and torsos angled away from each other.",
    "held-wrist-pull": "A holds B's wrist and leans back, B leaning the opposite way against the pull.",
    "sculpted-column": "The two press together back to front and stand perfectly still, forming a single vertical column.",
    "one-arched-one-straight": "A stands rigidly straight while B arches deeply beside her, the contrast doing the work.",
    "seated-lean-shoulders": "Seated side by side leaning their shoulders hard into one another, heads tipped apart.",
    "reaching-past-each-other": "A and B reach past one another in opposite directions, torsos crossing at the waist.",
    "kneel-and-stand-line": "A kneels and B stands directly behind, both arms extended along the same diagonal.",
    "twin-floor-arch": "Both on their backs side by side, hips lifted into simultaneous bridges.",
    "veil-between": "One sheer panel of fabric hangs between them, both faces pressed close to either side of it.",
    "one-turning-one-still": "A turns sharply with fabric flying while B stands motionless beside her.",
    "shoulder-blade-press": "Standing back to back pressed at the shoulder blades, both leaning their heads back until they touch.",
    "low-and-lower": "Both crouch, one slightly lower than the other, staggered in depth toward the camera.",
    "arms-crossed-between": "Facing one another with arms crossed and each holding the other's opposite hand.",
    "spiral-around-each-other": "The two circle one another mid-turn, bodies angled inward, faces toward the camera.",
    "one-supine-one-kneeling": "B lies supine while A kneels above her head, both arms extended down toward B's shoulders.",
    "matched-side-bends": "Standing a pace apart, both bending sideways toward each other with inside arms overhead.",
    "hands-on-each-waist": "Facing one another with each resting both hands on the other's waist, leaning back from the hips.",
    "silhouette-overlap": "Standing overlapped against a bright background so the two silhouettes read as one shape.",
}

LUSTFUL_CAST = {
    "foreheads-touching": "A and B stand very close with their foreheads resting together and eyes closed.",
    "hand-on-waist-behind": "A stands close behind B with one hand resting low on her waist, both looking toward the camera.",
    "whisper-at-ear": "A leans in to speak close at B's ear, B's eyes drifting toward the lens.",
    "back-to-chest-lean": "B leans back against A's chest with her head tipped onto A's shoulder, both relaxed.",
    "gaze-locked-close": "The two stand face to face a hand's width apart, holding each other's eyes and ignoring the camera.",
    "hand-in-hair": "A has one hand buried in B's hair at the back of her head, B's chin lifted.",
    "shoulder-strap-adjust": "A reaches across to lift a fallen strap back onto B's shoulder, both watching the movement.",
    "seated-lap-lean": "B sits across A's lap leaning back into her, one arm draped around A's neck.",
    "cheek-against-cheek": "The two press cheek to cheek facing the same direction, eyes on the lens.",
    "hand-at-jaw-turn": "A turns B's face gently toward her with a hand at the jaw, both in profile to the camera.",
    "lying-face-to-face": "Both lie on their sides facing one another, knees touching, one hand resting on the other's arm.",
    "arm-across-collarbone": "A stands behind B with one arm laid across B's collarbones, drawing her back.",
    "kneeling-close-pair": "Both kneel upright facing each other, thighs touching, hands resting on each other's hips.",
    "over-shoulder-both": "The two stand back to back and each turns her head to look over the same shoulder at the lens.",
    "hand-on-stomach-behind": "A stands behind B with a flat hand resting on her stomach, B leaning back into it.",
    "leaning-in-almost": "Faces angled toward one another and stopped just short of touching, both still.",
    "seated-legs-across": "B sits with her legs draped across A's lap, A resting a hand on B's knee.",
    "neck-glance-behind": "A stands behind and lowers her face toward B's neck while B looks straight into the camera.",
    "wrapped-from-behind": "A wraps both arms fully around B from behind, chins nearly level, both facing the lens.",
    "hands-clasped-high": "Standing face to face with hands clasped and raised between their chests, foreheads close.",
    "one-pulling-closer": "A takes B by the waist and draws her in a step, B's hand landing on A's shoulder.",
    "shared-mirror-look": "The two stand pressed together before a mirror, each watching the other's reflection.",
    "lying-one-over-other": "B lies back and A leans over her on one straight arm, both looking at the camera.",
    "hair-brushed-aside": "A sweeps B's hair back from her face with one hand, B's eyes closing.",
    "hip-to-hip-standing": "Standing hip to hip with outside hands on their own waists and heads tipped together.",
    "seated-close-knees-touch": "Seated facing one another with knees interlocked, leaning in with forearms on their own thighs.",
    "chin-lift-between": "A lifts B's chin with two fingers, B's gaze travelling up to meet hers.",
    "arm-around-waist-walk": "The two walk slowly side by side with A's arm low around B's waist, both glancing back.",
    "reclined-pair-tangle": "Both recline together with legs loosely tangled and one arm each behind their heads.",
    "shoulder-lean-eyes-shut": "B rests her head on A's shoulder with her eyes shut while A looks toward the lens.",
    "hands-on-each-face": "Each holds the other's face in both hands, foreheads touching, eyes closed.",
    "back-arch-into": "B arches backward into A's supporting arm while A leans over her, both in profile.",
    "close-dance-hold": "Held in a slow close dance position, bodies touching from chest to hip, faces turned to the camera.",
    "one-kneeling-looking-up": "A kneels before B and looks up at her, B's hand resting in A's hair.",
    "shared-glance-down": "Standing very close, both looking down at the small space between them.",
    "wrist-hold-close": "A holds B's wrist between them at chest height, the two standing almost touching.",
    "seated-behind-embrace": "A sits behind B on the floor with legs either side, arms wrapped around B's middle.",
    "cheek-turn-away": "A leans in close while B turns her cheek away, still smiling, eyes on the lens.",
    "lying-head-on-stomach": "B lies with her head resting on A's stomach, both looking up toward the camera.",
    "shoulder-bare-touch": "A rests her fingertips on B's bare shoulder, both watching the point of contact.",
    "leaning-wall-pair": "A leans one forearm on the wall above B, who is backed against it looking up.",
    "eyes-closed-both-close": "Standing very close with both sets of eyes closed and faces angled toward one another.",
    "hand-slide-hip": "A's hand rests at the curve of B's hip as they stand side on, both facing the lens.",
    "kneel-behind-lean-back": "B kneels and leans back against A who kneels behind her, A's hands on B's shoulders.",
    "close-profile-pair": "The two stand in tight profile facing each other, noses almost level, neither looking away.",
    "arm-draped-shoulders-close": "A drapes one arm heavily over B's shoulders and pulls her in until their hips meet.",
    "lying-side-by-side-look": "Lying side by side on their backs with heads turned toward each other.",
    "waist-hold-back-bend": "A holds B at the waist while B bends backward away from her, one arm falling loose.",
    "shared-breath-pause": "Stopped mid-motion a breath apart, both perfectly still, eyes on each other.",
    "one-behind-chin-shoulder": "A stands behind B and rests her chin on B's shoulder, both faces toward the camera.",
}


def emit_poses(groups: dict) -> str:
    out = ['"""Generated pose library — {cat: {id: text}}. Regenerate via '
           'scratchpad/gen_poses.py."""', "", "POSE_GROUPS = {"]
    for cat, items in groups.items():
        out.append(f"  {json.dumps(cat)}: {{")
        for k, v in items.items():
            out.append(f"    {json.dumps(k)}: {json.dumps(v)},")
        out[-1] = out[-1][:-1]           # drop the trailing comma
        out.append("  },")
    out[-1] = "  }"
    out.append("}")
    return "\n".join(out) + "\n"


def _strip_categories(src: str, cats) -> str:
    """Remove an existing top-level category block so a re-run replaces it.

    Without this the insert appends a second "Exotic" key to the same literal.
    Python binds the last one so every count still reads correctly, which is
    exactly the kind of silent doubling that hid in the first version of this
    script — the file grows on every run and nothing complains.
    """
    lines = src.splitlines(keepends=True)
    for cat in cats:
        head = f'    "{cat}": {{\n'
        if head not in lines:
            continue
        i = lines.index(head)
        j = i + 1
        while j < len(lines) and lines[j] != "    },\n":
            j += 1
        del lines[i:j + 1]
    return "".join(lines)


def append_interactions(src: str, new_cats: dict) -> str:
    """Insert new categories before the dict's closing brace.

    A surgical insert rather than a re-emit: the existing 250 entries are left
    byte-for-byte alone, so the diff shows only what was actually added and the
    file's own hand-tuned wrapping survives.

    (The first version re-emitted the whole dict, which reformatted 824 untouched
    lines. The version before THAT split on "INTERACTIONS = {" — which never
    matches, because the declaration is annotated — and silently appended a
    SECOND complete copy of the library that Python then bound over the first.)
    """
    src = _strip_categories(src, new_cats)   # so re-running replaces, not doubles
    close = src.rindex("\n}")            # the brace closing INTERACTIONS
    body = []
    for cat, items in new_cats.items():
        body.append(f"    {json.dumps(cat)}: {{")
        for k, v in items.items():
            body.append(f"        {json.dumps(k)}: {{\"text\": {json.dumps(v['text'])},")
            body.append(f"            \"min_cast\": {v['min_cast']}}},")
        body.append("    },")
    return src[:close + 1] + "\n".join(body) + "\n" + src[close + 1:]


if __name__ == "__main__":
    # --- single body
    groups = {c: g for c, g in poses_data.POSE_GROUPS.items()
              if c not in ("Exotic", "Lustful")}
    seen = {k for g in groups.values() for k in g}
    for cat, items in (("Exotic", EXOTIC), ("Lustful", LUSTFUL)):
        dupes = seen & set(items)
        if dupes:
            raise SystemExit(f"{cat}: id collision {sorted(dupes)}")
        assert len(items) == 50, f"{cat}: {len(items)} entries, want 50"
        groups[cat] = items
        seen |= set(items)
    (PROJ / "backend" / "poses_data.py").write_text(emit_poses(groups))
    print(f"poses_data.py: {sum(len(g) for g in groups.values())} poses "
          f"in {len(groups)} categories")

    # --- cast
    inter = {c: g for c, g in interactions_data.INTERACTIONS.items()
             if c not in ("Exotic", "Lustful")}
    seen_i = {k for g in inter.values() for k in g}
    for cat, items in (("Exotic", EXOTIC_CAST), ("Lustful", LUSTFUL_CAST)):
        dupes = seen_i & set(items)
        if dupes:
            raise SystemExit(f"{cat}: id collision {sorted(dupes)}")
        assert len(items) == 50, f"{cat}: {len(items)} entries, want 50"
        inter[cat] = {k: {"text": v, "min_cast": 2} for k, v in items.items()}
        seen_i |= set(items)
    add = {c: inter[c] for c in ("Exotic", "Lustful")}
    src = (PROJ / "backend" / "interactions_data.py").read_text()
    (PROJ / "backend" / "interactions_data.py").write_text(append_interactions(src, add))
    print(f"interactions_data.py: {sum(len(g) for g in inter.values())} entries "
          f"in {len(inter)} categories")
