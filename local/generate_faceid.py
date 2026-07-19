"""Local SDXL + IP-Adapter-FaceID — identity from the ArcFace embedding.

The plus-face worker conditions on soft CLIP features and scored 0.478 (a
different woman). FaceID conditions on the 512-d ArcFace embedding directly —
the SAME vector the gate computes with buffalo_l. So the thing driving
generation and the thing judging it are the same measurement, which is the
strongest identity signal available to a local pipeline.

    .venv-gen\\Scripts\\python.exe local/generate_faceid.py <job.json>

## Why this is fiddlier than plus-face

FaceID is not a plain image adapter. Three pieces must line up:
  1. insightface extracts the 512-d normed embedding from the reference.
  2. The FaceID adapter projects that embedding (no CLIP image encoder).
  3. A companion LoRA adjusts the UNet for the FaceID projection — without it
     identity is markedly weaker. Both ship in h94/IP-Adapter-FaceID.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import torch

# Blackwell (sm_120): cuDNN has no conv engine for some SDXL shapes on this
# torch build. Native kernels are slower but universal. See generate_local.py.
torch.backends.cudnn.enabled = False

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from diffusers import AutoencoderKL, StableDiffusionXLPipeline  # noqa: E402
from insightface.app import FaceAnalysis  # noqa: E402
from PIL import Image  # noqa: E402

MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
VAE = "madebyollin/sdxl-vae-fp16-fix"
FACEID_REPO = "h94/IP-Adapter-FaceID"
FACEID_WEIGHT = "ip-adapter-faceid_sdxl.bin"
FACEID_LORA = "ip-adapter-faceid_sdxl_lora.safetensors"

NEG = ("cartoon, anime, illustration, 3d render, cgi, painting, doll, plastic "
       "skin, airbrushed, smooth skin, deformed, extra fingers, blurry, "
       "watermark, text, logo, oversaturated")

_pipe = None
_app = None


def face_embed(path: str) -> torch.Tensor:
    """The 512-d ArcFace embedding, formatted the way diffusers wants for
    FaceID: [uncond, cond] stacked, uncond = zeros."""
    global _app
    if _app is None:
        _app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _app.prepare(ctx_id=0, det_size=(640, 640))
    img = cv2.imread(path)
    faces = _app.get(img)
    if not faces:
        raise RuntimeError(f"no face in reference {path}")
    f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
    emb = torch.from_numpy(f.normed_embedding).unsqueeze(0)          # [1, 512]
    emb = emb.unsqueeze(0)                                            # [1, 1, 512]
    neg = torch.zeros_like(emb)
    return torch.cat([neg, emb]).to("cuda", dtype=torch.float16)     # [2, 1, 512]


def pipe() -> StableDiffusionXLPipeline:
    global _pipe
    if _pipe is not None:
        return _pipe
    vae = AutoencoderKL.from_pretrained(VAE, torch_dtype=torch.float16)
    p = StableDiffusionXLPipeline.from_pretrained(
        MODEL, vae=vae, torch_dtype=torch.float16, variant="fp16",
        use_safetensors=True)
    # image_encoder_folder=None: FaceID takes an embedding, not an image, so
    # there is no CLIP image encoder to load.
    p.load_ip_adapter(FACEID_REPO, subfolder=None, weight_name=FACEID_WEIGHT,
                      image_encoder_folder=None)
    p.load_lora_weights(FACEID_REPO, weight_name=FACEID_LORA)
    p.enable_model_cpu_offload()
    _pipe = p
    return p


def generate(job: dict) -> dict:
    embeds = face_embed(job["face"])
    p = pipe()
    p.set_ip_adapter_scale(float(job.get("ip_scale", 0.8)))
    g = None
    if job.get("seed") is not None:
        g = torch.Generator(device="cuda").manual_seed(int(job["seed"]))

    t0 = time.time()
    img = p(
        prompt=job["prompt"],
        negative_prompt=NEG,
        ip_adapter_image_embeds=[embeds],
        width=int(job.get("width", 1024)),
        height=int(job.get("height", 1536)),
        num_inference_steps=int(job.get("steps", 30)),
        guidance_scale=float(job.get("cfg", 5.0)),
        generator=g,
    ).images[0]

    out = Path(job["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return {"out": str(out), "seconds": round(time.time() - t0, 1),
            "size": list(img.size)}


def main() -> int:
    job = json.loads(Path(sys.argv[1]).read_text())
    print("RESULT " + json.dumps(generate(job)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
