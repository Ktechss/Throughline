"""Train a FLUX LoRA on the reference set, then test it through the same gate.

    .venv-win\\Scripts\\python.exe scripts\\train_lora.py

Registers its outputs as a session so the results sit beside the bakeoff in the
review grid rather than in a script's stdout — the previous bakeoff's reasoning
was lost exactly that way.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import fal_client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import generate                                # noqa: E402
from backend.config import STATE                            # noqa: E402

ZIP = Path("data/lora-set.zip")
TRIGGER = "eve1sdx"
LORA_JSON = STATE / "lora.json"

TRAINER = "fal-ai/flux-lora-fast-training"
INFER = "fal-ai/flux-lora"

# The trigger carries her face; the prompt carries everything else. Naming her
# features here would defeat the point of having trained a trigger at all.
PROMPTS = [
    ("closeup", f"A candid iPhone photo of {TRIGGER}, tight head and shoulders "
                f"portrait, her face filling most of the frame, facing the camera, "
                f"plain white studio background, soft even light, photorealistic, "
                f"real skin texture with visible pores, no retouching"),
    ("fullbody", f"A candid iPhone photo of {TRIGGER}, full body head to toe, "
                 f"standing, facing the camera, plain white studio background, "
                 f"soft even light, photorealistic, real skin texture, no retouching"),
]


def train() -> str:
    if LORA_JSON.exists():
        url = json.loads(LORA_JSON.read_text())["lora_url"]
        print(f"reusing trained LoRA: {url[:70]}...")
        return url

    print(f"uploading {ZIP.name} ({ZIP.stat().st_size/1e6:.1f} MB)...")
    data_url = fal_client.upload_file(str(ZIP))
    print(f"training {TRAINER}  trigger='{TRIGGER}'  (several minutes)")
    t0 = time.time()
    r = fal_client.subscribe(TRAINER, arguments={
        "images_data_url": data_url,
        "trigger_word": TRIGGER,
        # Masking isolates the subject so the trainer doesn't spend capacity on
        # the backgrounds — which we have also named in the captions. Belt and
        # braces against the constant-absorption trap.
        "create_masks": True,
        "steps": 1000,
    }, with_logs=False)
    url = r["diffusers_lora_file"]["url"]
    LORA_JSON.write_text(json.dumps(
        {"lora_url": url, "trigger": TRIGGER, "steps": 1000,
         "trained": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "images": 52, "seconds": round(time.time() - t0)}, indent=2) + "\n")
    print(f"  trained in {time.time()-t0:.0f}s -> {url[:70]}...")
    return url


def main() -> int:
    url = train()
    session = generate.new_session("FLUX LoRA @1000 steps — 52 reference images")

    for name, prompt in PROMPTS:
        try:
            row = generate.generate(
                prompt=prompt, refs=[], aspect="3:4", session=session,
                endpoint=INFER,
                extra={"loras": [{"path": url, "scale": 1.0}],
                       "image_size": {"width": 1024, "height": 1408},
                       "num_inference_steps": 28, "guidance_scale": 3.5},
                meta={"note": f"lora: {name}"},
            )
        except Exception as exc:                            # noqa: BLE001
            print(f"  {name:<10} FAILED {str(exc)[:110]}")
            continue
        v = row["verdict"]
        if "similarity" in v:
            print(f"  {name:<10} {v['similarity']:.3f} vs {v['matched']:<10} "
                  f"yaw {v['yaw']:+6.1f} (delta {v['pose_delta']:>4.1f})  "
                  f"{v['face_px']:>3}px  {v['status'].upper()}")
        else:
            print(f"  {name:<10} {v}")
        print(f"             data/images/{row['file']}")

    print("\n  baselines:  ideogram 0.750   pulid 0.713   nano-banana 0.678")
    print("  her own frontals agree at 0.797  <- ceiling")
    return 0


if __name__ == "__main__":
    sys.exit(main())
