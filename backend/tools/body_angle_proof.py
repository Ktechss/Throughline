"""3-angle body-reference proof + A/B.

Hypothesis (the owner's idea): the single frontal body reference attached as
@image2 on no-wardrobe shots forces the model to mentally rotate the body for
profile / three-quarter shots, costing body fidelity and wardrobe drape. If we
instead attach a body reference AT THE SHOT'S ANGLE, the body anchor agrees with
the request and drift drops. This is a SELECTION (still just face + body, two
slots) — not an added reference — so it dodges the slot-cost penalty.

Body has no gate (person re-ID keys on clothing), so this proof measures the two
numbers we honestly can:
  1. Each generated body-angle ref: does the FACE survive (similarity vs gallery)
     and did the body actually turn (yaw)? A ref that drifts identity or didn't
     rotate is rejected here, not shipped.
  2. A/B shot: same brief, same seed, only @image2 differs (frontal body vs
     angle-matched body). We compare final-shot face similarity — the claim to
     verify is that the angle-matched body does NOT cost identity. The body /
     drape improvement itself is eyeball-only (no body gate exists), so both
     images are saved side by side for that one human judgement.

Run:  .venv-win\\Scripts\\python.exe -m backend.tools.body_angle_proof
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .. import config  # noqa: F401 — side effect: loads .env
from .. import gate
from .. import generate
from .. import prompt as promptlib
from ..config import IMAGES, REFS, STATE

OUT = config.DATA / "body_angle_proof"
OUT.mkdir(exist_ok=True)

BIO = json.loads((STATE / "bio.json").read_text())
FACE = REFS / BIO["reference"]
FRONTAL_BODY = REFS / BIO["body_reference"]
THRESH = gate.load_threshold()

# target angles: front / three-quarter / profile. The face gallery spans these
# same buckets. |yaw| targets are approximate — nano obeys the turn loosely, so
# we MEASURE the achieved yaw rather than assume it.
ANGLES = [
    ("front", 0, "She stands straight facing the camera, squared to the lens."),
    ("threequarter", 30,
     "Her body is turned about thirty degrees to her left into a three-quarter "
     "stance, shoulders angled away from the camera, head following the body."),
    ("profile", 70,
     "She stands in near-full profile, her body turned about seventy degrees to "
     "her left so her side faces the camera, head in profile."),
]

_PARTS = [promptlib.Part(**d) for d in json.loads((STATE / "parts.json").read_text())]
BUILD = promptlib.build_clause(_PARTS)


def _body_prompt(turn: str) -> str:
    return (
        "Full-body studio photograph of @image1 on a plain white seamless "
        f"background, lit flat and even. {turn} Arms relaxed at her sides, "
        "neutral expression, wearing simple fitted plain activewear (a fitted "
        "tank top and leggings) so her figure and proportions are clearly "
        f"visible. {BUILD} Her face and identity exactly match @image1. "
        "Photorealistic, real skin texture, natural anatomy.")


def _score(img: Path) -> dict:
    """Face similarity + yaw for a generated image."""
    try:
        v = gate.check(img).dict()
        return {"similarity": v.get("similarity"), "yaw": v.get("yaw"),
                "face_px": v.get("face_px"), "status": v.get("status")}
    except Exception as e:  # noqa: BLE001
        return {"similarity": None, "yaw": None, "face_px": None,
                "status": f"no_face:{str(e)[:40]}"}


def step_a() -> dict[str, Path]:
    """Generate a body ref per angle; keep the ones whose face survives."""
    print("\n=== STEP A — generate 3 angle body refs ===")
    print(f"gallery threshold = {THRESH:.3f}\n")
    kept: dict[str, Path] = {}
    for name, target_yaw, turn in ANGLES:
        row = generate.generate(
            prompt=_body_prompt(turn), system="", refs=[FACE], aspect="3:4",
            session=generate.new_session(f"body-angle {name}"),
            fallback_endpoint=generate.SCENE_EDIT,
            meta={"body_angle_proof": name, "target_yaw": target_yaw})
        src = IMAGES / row["file"]
        s = _score(src)
        ok = (s["similarity"] is not None and s["similarity"] >= THRESH)
        dst = OUT / f"bodyref_{name}.png"
        shutil.copy2(src, dst)
        flag = "KEEP" if ok else "REJECT (face drift/no face)"
        print(f"  {name:13s} target|yaw|~{target_yaw:<3d} -> "
              f"sim={s['similarity']} yaw={s['yaw']} face_px={s['face_px']} "
              f"[{flag}]  {dst.name}")
        if ok:
            kept[name] = dst
    return kept


def _shot_prompt(brief: str) -> str:
    text, _ = promptlib.compose_tagged(brief, has_wardrobe=False,
                                       build_text=BUILD, shot_type="candid")
    return text


def ab_pair(label: str, brief: str, angle_body: Path, seed: int) -> None:
    """Same brief + same seed; only @image2 (body ref) changes."""
    print(f"\n--- A/B [{label}] seed={seed} ---")
    print(f"    brief: {brief}")
    prompt = _shot_prompt(brief)
    for arm, body in (("control_frontalbody", FRONTAL_BODY),
                      ("treat_anglebody", angle_body)):
        row = generate.generate(
            prompt=prompt, system="", refs=[FACE, body], aspect="9:16",
            seed=seed, session=generate.new_session(f"ab {label} {arm}"),
            fallback_endpoint=generate.SCENE_EDIT, resolution="2K",
            meta={"body_angle_ab": label, "arm": arm, "body": body.name})
        src = IMAGES / row["file"]
        s = _score(src)
        dst = OUT / f"ab_{label}_{arm}.png"
        shutil.copy2(src, dst)
        print(f"    {arm:22s} body=@{body.name:20s} -> "
              f"sim={s['similarity']} yaw={s['yaw']} face_px={s['face_px']}  {dst.name}")


def main() -> None:
    print(f"face  = {FACE.name}")
    print(f"body  = {FRONTAL_BODY.name} (the current single frontal ref)")
    print(f"out   = {OUT}")
    kept = step_a()

    print("\n=== STEP B — A/B: frontal body vs angle-matched body ===")
    if "profile" in kept:
        ab_pair("profile",
                "Full-body profile fashion shot of her standing on a city "
                "street at dusk, turned to her side, natural stride.",
                kept["profile"], seed=707707)
    else:
        print("  (skipped profile A/B — profile body ref failed step A)")
    if "threequarter" in kept:
        ab_pair("threequarter",
                "Full-body three-quarter fashion shot of her on a city "
                "street at dusk, body angled away from the camera.",
                kept["threequarter"], seed=313313)
    else:
        print("  (skipped 3/4 A/B — three-quarter body ref failed step A)")

    print(f"\nDONE. All images in: {OUT}")
    print("Compare ab_*_control_frontalbody vs ab_*_treat_anglebody:")
    print(" - similarity must NOT drop on the treat arm (identity safety), and")
    print(" - eyeball body proportions + how the clothing sits at that angle.")


if __name__ == "__main__":
    main()
