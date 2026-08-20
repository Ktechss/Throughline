"""Add a Pool & Water category — 100 poses.

Two things make this category different from every other one in the library,
and both are deliberate.

**Wetness is part of the pose.** Everywhere else the pose describes only where
the body is, because hair and skin are constants carried by the bio parts. In
water they are not constants: hair goes dark and flat and clings, skin holds
droplets and sheen, fabric darkens and sticks. Left unsaid, the model renders a
dry woman standing in a pool, which is the tell that ruins the shot. So each
entry states the water state it implies.

**Some of these cannot be gated, by design.** A dive, an underwater shot, a
back-to-camera climb out — the face is turned away, submerged, or behind a sheet
of water. `gate.check` will abstain or find no face at all, and that is the
correct outcome rather than a failure: the picture is about the moment, not
about proving identity. The generator reports the count so nobody is surprised
by a wall of abstains later.

Run:  ./.venv/bin/python scripts/gen_pool_poses.py
"""
import json
import re
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))
from backend import poses_data                                  # noqa: E402

CATEGORY = "Pool & Water"

POOL = {
    # --- entering the water
    "pool-dive-standing": "Standing at the pool edge with arms stretched overhead and knees bent, still dry, caught in the instant before she pushes off into the water.",
    "pool-dive-racing-start": "Crouched on the edge in a racing start, fingers curled over the lip, weight forward and eyes down at the water.",
    "pool-dive-swan": "Mid-air in a swan dive with both arms spread wide and back arched, body still dry, the water rushing up beneath her.",
    "pool-dive-mid-air": "Caught mid-dive head-down with arms locked together ahead of her and legs straight behind, a breath from the surface.",
    "pool-dive-entry-splash": "The moment of entry — her legs still above the surface, a white column of spray thrown up around her.",
    "pool-shallow-dive": "Flattened into a shallow racing dive just under the surface, arms extended, a trail of bubbles behind her shoulders.",
    "pool-jump-knees-up": "Jumping into the water feet first with both knees pulled up to her chest and arms wrapped around them, hair lifting, the surface rushing up.",
    "pool-cannonball": "Tucked into a tight cannonball in mid-air above the water, face buried toward her knees.",
    "pool-jump-arms-wide": "Leaping off the edge toward the water with both arms flung wide and head back, laughing, still dry in mid-air.",
    "pool-step-in-ladder": "Backing down the pool ladder one rung at a time, hands on the rails, legs already wet to the thigh.",
    "pool-toe-test": "Standing at the edge dipping one pointed toe into the surface, arms out slightly for balance, the rest of her dry.",
    "pool-sit-edge-slide-in": "Sitting on the edge with both hands beside her hips, sliding forward to drop into the water, legs already submerged.",
    "pool-walk-down-steps": "Walking down the wide pool steps with one hand on the rail, water rising past her knees and darkening her swimsuit.",
    "pool-run-and-leap": "Caught mid-stride running along the deck and launching toward the water, hair streaming behind her.",
    "pool-backward-fall": "Falling backwards into the water with arms crossed over her chest and eyes closed, a breath before the surface takes her.",

    # --- coming out
    "pool-ladder-climb-out": "Climbing the pool ladder with both hands on the rails, water sheeting off her, hair dark and flat against her back.",
    "pool-haul-out-edge": "Hauling herself out on the pool edge, arms locked straight and shoulders raised, water running from her elbows.",
    "pool-rise-from-water": "Rising up out of the water to her waist, head tipped back and both hands sliding her soaked hair off her face.",
    "pool-steps-walk-up": "Walking up the pool steps out of the water, one hand on the rail, wet hair clinging to her shoulders.",
    "pool-emerging-hair-back": "Breaking the surface and pushing her drenched hair straight back with both hands, eyes still closed, water streaming down her face.",
    "pool-edge-push-up": "Palms flat on the pool edge pushing herself upward, arms tensed, water pouring off her shoulders.",
    "pool-climbing-out-back": "Climbing out with her back to the camera, water running down her spine, hair a dark rope between her shoulder blades.",
    "pool-standing-in-shallow": "Standing waist deep in the shallow end, arms trailing on the surface, skin beaded with water.",
    "pool-wading-out": "Wading toward the steps through waist-deep water, one hand skimming the surface, wet fabric clinging.",
    "pool-exit-wrap-towel": "Just out of the water on the deck, pulling a towel around her shoulders, hair dripping onto the tiles.",
    "pool-exit-look-back": "Walking away from the pool along the wet deck and glancing back over one shoulder, footprints behind her.",
    "pool-exit-drip": "Standing on the deck fresh out of the pool, arms loose at her sides, water running from her fingertips and hair.",

    # --- in the water
    "pool-float-back": "Floating on her back with arms out and ears under the surface, only her face, chest and toes breaking the water.",
    "pool-float-starfish": "Spread into a starfish float on her back, limbs wide, hair fanned out around her head on the surface.",
    "pool-tread-water": "Treading water in the deep end with only her head and shoulders above the surface, hair slicked back.",
    "pool-underwater-swim": "Underwater mid-stroke, body stretched long and hair streaming behind her, sunlight rippling across her back.",
    "pool-underwater-look-up": "Underwater and looking up toward the surface, bubbles rising past her face, light fracturing above.",
    "pool-breaststroke": "Mid-breaststroke with her head just clear of the water, arms sweeping outward and a small bow wave at her chin.",
    "pool-backstroke": "Mid-backstroke with one arm reaching back over her shoulder, face up, water breaking around her ears.",
    "pool-freestyle-breath": "Turning her head to breathe mid-freestyle, one arm out of the water, a trough of water at her cheek.",
    "pool-hold-edge-legs-out": "Holding the pool edge with both hands and letting her legs float out straight behind her on the surface.",
    "pool-lean-on-edge": "Leaning both forearms on the pool edge from in the water, chin near her hands, shoulders wet and glistening.",
    "pool-submerged-shoulders": "Submerged to the shoulders and looking toward the camera, hair floating loose on the surface around her.",
    "pool-half-submerged": "Half in and half out at the waterline, the surface cutting across her ribs, skin wet above it.",
    "pool-walking-in-water": "Walking through chest-deep water with both arms lifted clear of the surface, wake spreading behind her.",
    "pool-spin-in-water": "Spinning in waist-deep water with one arm sweeping a curve of spray off the surface, hair flying wet.",
    "pool-underwater-hair-float": "Suspended underwater upright with her hair drifting up around her head and her eyes closed.",
    "pool-dive-under": "Duck-diving under the surface, hips at the top of the arc and legs following, a swirl of bubbles behind.",
    "pool-surface-break": "Breaking the surface face first with her mouth open for air, water flying off her hair in an arc.",
    "pool-float-ring": "Sitting inside an inflatable ring in the water, arms draped over its sides, legs dangling below.",
    "pool-noodle-lean": "Leaning back over a foam noodle in deep water, arms spread along it, feet drifting up in front.",
    "pool-back-to-wall": "Resting her back against the pool wall in deep water with elbows hooked on the edge behind her.",

    # --- wet emergence and hair
    "pool-hair-flip-back": "Whipping her head back to throw her soaked hair out of her face, a sheet of water arcing off it.",
    "pool-wring-hair": "Standing in shallow water wringing her hair out over one shoulder with both hands, water twisting out of it.",
    "pool-slick-hair-back": "Running both hands from her forehead back through slicked wet hair, elbows wide, chin lifted.",
    "pool-wipe-eyes": "Wiping the water from her eyes with the heels of both hands, face tipped down, hair plastered to her temples.",
    "pool-arch-back-water": "Arched backward from the waist in waist-deep water, hair trailing on the surface behind her, throat to the sky.",
    "pool-shake-head": "Shaking her head sharply to fling water from her hair, droplets suspended in the air around her.",
    "pool-hair-over-shoulder": "Pulling her heavy wet hair forward over one shoulder, water squeezing out between her fingers.",
    "pool-water-run-face": "Standing still with water still running down her face and neck, eyes half open, breathing.",
    "pool-blink-water": "Blinking water from her lashes just after surfacing, mouth slightly open, cheeks wet and flushed.",
    "pool-hands-through-wet-hair": "Both hands buried in her wet hair lifting it off her neck, elbows raised, water tracking down her arms.",
    "pool-tilt-head-drip": "Head tilted to one side letting water run out of her hair down her shoulder, eyes toward the camera.",
    "pool-spray-arc": "Sweeping one arm across the surface to throw a wide arc of spray, laughing, half turned away.",

    # --- the edge
    "pool-sit-edge-legs-in": "Sitting on the pool edge with both legs in the water to the knee, hands flat beside her hips.",
    "pool-sit-edge-lean-back": "Sitting on the edge leaning back on both straight arms, legs in the water, face tipped up to the sun.",
    "pool-sit-edge-side": "Sitting side-on to the edge with legs angled into the water and torso twisted toward the camera.",
    "pool-kneel-edge": "Kneeling on the wet tiles at the pool edge, one hand trailing in the water, hair damp at the ends.",
    "pool-lie-edge-front": "Lying on her front along the pool edge with her chin on stacked hands and one arm hanging into the water.",
    "pool-lie-edge-back": "Lying on her back along the pool edge with knees bent and one foot dipped in the water, arms overhead.",
    "pool-sit-steps": "Sitting on the submerged pool steps with the water at her waist, leaning back on her hands.",
    "pool-perch-corner": "Perched in the corner of the pool edge with legs drawn up and arms around her shins, feet just wet.",
    "pool-legs-kick-edge": "Sitting on the edge kicking both legs lazily through the water, hands braced behind her, spray at her ankles.",
    "pool-sit-edge-look-down": "Sitting on the edge looking down into the water at her own reflection, hair falling forward.",
    "pool-elbows-on-edge": "In the water with both elbows hooked on the pool edge and chin resting on her folded arms.",
    "pool-sit-ledge-cross-ankles": "Sitting on a submerged ledge with ankles crossed and hands resting on the ledge either side of her.",
    "pool-edge-lean-forward": "Sitting on the edge leaning forward with forearms on her thighs, water dripping from her hair onto the tiles.",
    "pool-sit-edge-hands-behind": "Sitting on the edge with hands clasped behind her and shoulders drawn back, legs straight into the water.",
    "pool-shallow-sit": "Sitting directly in the shallowest water so it runs around her hips, legs out in front, palms on the floor.",

    # --- lounger and deck
    "pool-lounger-recline": "Reclining back on a poolside lounger with one knee raised, skin still wet and the towel bunched beneath her.",
    "pool-lounger-front": "Lying face down on a lounger propped on her forearms, wet hair falling to one side, feet crossed in the air.",
    "pool-lounger-sit-up": "Sitting upright on the edge of a lounger with feet on the deck, elbows on her knees, hair dripping.",
    "pool-lounger-legs-crossed": "Lying back on a poolside lounger with ankles crossed and one arm behind her head, sunglasses on, swimsuit still damp from the water.",
    "pool-deck-stand-drip": "Standing on the pool deck with weight on one hip, water still running off her, tiles dark around her feet.",
    "pool-deck-walk": "Walking barefoot along the wet pool deck, one hand skimming a rail, wet footprints trailing behind.",
    "pool-towel-wrap": "Standing on the deck with a towel wrapped and held at her chest, hair pushed back and dripping.",
    "pool-sunbed-arch": "Arched back on a sunbed with both arms stretched overhead and one knee bent, wet hair drying against the cushion in the sun.",
    "pool-deck-stretch": "Standing on the wet pool deck stretching both arms high overhead and rising onto her toes, water drying on her skin.",
    "pool-lounger-side": "Lying on her side along a poolside lounger propped on one elbow, the other hand on her hip, hair still wet from the water.",
    "pool-deck-sit-knees": "Sitting on the deck with knees drawn up and arms around them, chin on her knees, hair wet down her back.",
    "pool-lounger-hat": "Reclining on a lounger with a wide sun hat tipped low over her face and one hand on her stomach, skin drying after the water.",
    "pool-deck-look-back": "Standing at the far end of the deck with her back to the camera, turning to look over one wet shoulder.",

    # --- floats and play
    "pool-float-lilo": "Lying stretched out on an inflatable lilo drifting in the middle of the pool, one hand trailing in the water.",
    "pool-inflatable-ring-sit": "Sitting up inside a large inflatable ring floating on the water, both arms hooked over it, legs kicking beneath the surface.",
    "pool-handstand": "Upside down in a handstand under the water, legs straight up out of the surface, hair fanned below.",
    "pool-splash-hands": "Slapping both palms flat on the surface to throw water toward the camera, face screwed up laughing.",
    "pool-kick-splash": "Lying on her front holding the edge and kicking hard, a wall of white water thrown up behind her feet.",
    "pool-jump-hug-knees": "Frozen mid-jump above the water hugging her knees tight to her chest, eyes closed, hair up around her.",
    "pool-float-drift": "Drifting on her back with eyes closed and arms wide, completely still, the surface glassy around her.",
    "pool-lean-inflatable": "Leaning her upper body over an inflatable float in the water, arms folded on it, chin resting on her forearms.",
    "pool-underwater-flip": "Mid-somersault underwater, body curled and hair swirling, bubbles spiralling around her.",
    "pool-somersault": "Tucked into a forward somersault at the surface, only her back and heels showing above the water.",
    "pool-push-off-wall": "Feet planted on the pool wall underwater, knees bent, about to push off into a glide.",
    "pool-glide": "Gliding just under the surface with arms locked ahead and body streamlined, momentum carrying her forward.",
    "pool-float-arms-out": "Floating upright in deep water with both arms stretched out along the surface, head back, eyes closed.",
}

# Poses where the face is turned away, submerged, or behind water. gate.check
# will abstain or find nothing, and that is correct — these are moments, not
# identity checks.
_UNGATEABLE = re.compile(
    r"underwater|back to the camera|face buried|eyes closed|face down|"
    r"upside down|somersault|duck-div|mid-dive head-down|spine|back and heels",
    re.I)


def emit(groups: dict) -> str:
    out = ['"""Generated pose library — {cat: {id: text}}. Regenerate via '
           'scratchpad/gen_poses.py."""', "", "POSE_GROUPS = {"]
    for cat, items in groups.items():
        out.append(f"  {json.dumps(cat)}: {{")
        for k, v in items.items():
            out.append(f"    {json.dumps(k)}: {json.dumps(v)},")
        out[-1] = out[-1][:-1]
        out.append("  },")
    out[-1] = "  }"
    out.append("}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    groups = {c: g for c, g in poses_data.POSE_GROUPS.items() if c != CATEGORY}
    seen = {k for g in groups.values() for k in g}

    dupes = seen & set(POOL)
    if dupes:
        raise SystemExit(f"id collision with the existing library: {sorted(dupes)}")
    if len(POOL) != 100:
        raise SystemExit(f"{len(POOL)} poses, want 100")

    # Wetness must actually be stated — a dry woman in a pool is the failure
    # this category exists to avoid.
    dry = [k for k, v in POOL.items()
           if not re.search(r"wet|water|soaked|drip|damp|spray|splash|submerg|"
                            r"surface|bubbl|drench|underwater", v, re.I)]
    if dry:
        raise SystemExit(f"these never mention water: {dry}")

    groups[CATEGORY] = POOL
    (PROJ / "backend" / "poses_data.py").write_text(emit(groups))

    ungateable = sorted(k for k, v in POOL.items() if _UNGATEABLE.search(v))
    total = sum(len(g) for g in groups.values())
    print(f"{CATEGORY}: {len(POOL)} poses added — {total} in the library, "
          f"{len(groups)} categories")
    print(f"expected to abstain or find no face: {len(ungateable)} of {len(POOL)}")
    for k in ungateable:
        print(f"   {k}")
