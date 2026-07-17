"""Local SDXL generation — $0 per image, on the 8GB RTX 5070.

Runs in its own venv (.venv-gen: torch + diffusers + insightface) and is driven
as a SUBPROCESS by the backend, exactly the way fal is driven over HTTP. The web
backend never imports torch — the heavy stack stays isolated here.

    .venv-gen\\Scripts\\python.exe local/generate_local.py <job.json>

job.json: {"prompt": str, "face": path, "out": path,
           "width": 1024, "height": 1536, "steps": 30,
           "ip_scale": 0.7, "seed": int|null}

## Why IP-Adapter, and why this face model

Identity comes from a reference IMAGE, not the prompt — the same rule the whole
project runs on. IP-Adapter conditions SDXL on a face image; the "plus-face"
variant is the strongest identity option that loads through native diffusers
without custom pipeline glue.

## The 8GB reality

SDXL is ~6.9GB in fp16 and will not fit alongside the VAE, both text encoders
and the IP-Adapter on an 8GB card. `enable_model_cpu_offload()` streams each
sub-model to the GPU only while it runs and parks the rest in system RAM. That
is what makes this fit at all; it costs wall-clock time, not quality.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import torch

# Blackwell (sm_120) + torch 2.11/cu128: cuDNN's heuristic cannot find an engine
# for some SDXL conv configs — "GET was unable to find an engine to execute this
# computation" at conv2d. Falling back to PyTorch's native conv kernels is slower
# but universal, and we are CPU-offloading anyway, so correctness wins. Revisit
# when a cuDNN build with Blackwell conv heuristics lands.
torch.backends.cudnn.enabled = False

from diffusers import AutoencoderKL, StableDiffusionXLPipeline  # noqa: E402
from PIL import Image  # noqa: E402
from transformers import CLIPVisionModelWithProjection  # noqa: E402

MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
# SDXL's stock VAE overflows in fp16 (black/NaN tiles). The community fp16-fix
# VAE is the standard consumer-GPU replacement and decodes cleanly in fp16.
VAE = "madebyollin/sdxl-vae-fp16-fix"
IP_REPO = "h94/IP-Adapter"
IP_SUB = "sdxl_models"
IP_WEIGHT = "ip-adapter-plus-face_sdxl_vit-h.safetensors"
# The plus-face_vit-h weights expect a ViT-H image encoder (1280-dim). Left to
# auto-detect, diffusers loads the SDXL default bigG encoder (1664-dim) and the
# projection matmul fails: "514x1664 and 1280x1280". Load the matching encoder
# explicitly — the weight name and the encoder must agree.
IP_ENCODER_SUB = "models/image_encoder"

NEG = ("cartoon, anime, illustration, 3d render, cgi, painting, doll, plastic "
       "skin, airbrushed, smooth skin, deformed, extra fingers, blurry, "
       "watermark, text, logo, oversaturated")

_pipe = None


def pipe() -> StableDiffusionXLPipeline:
    global _pipe
    if _pipe is not None:
        return _pipe
    encoder = CLIPVisionModelWithProjection.from_pretrained(
        IP_REPO, subfolder=IP_ENCODER_SUB, torch_dtype=torch.float16)
    vae = AutoencoderKL.from_pretrained(VAE, torch_dtype=torch.float16)
    p = StableDiffusionXLPipeline.from_pretrained(
        MODEL, image_encoder=encoder, vae=vae, torch_dtype=torch.float16,
        variant="fp16", use_safetensors=True)
    p.load_ip_adapter(IP_REPO, subfolder=IP_SUB, weight_name=IP_WEIGHT)
    # The line that makes 8GB work. Do NOT replace with .to("cuda") — that loads
    # the whole pipeline onto the card at once and OOMs on SDXL here.
    p.enable_model_cpu_offload()
    # NB: no enable_vae_tiling(). Its odd tile shapes hit a cuDNN "unable to find
    # an engine" error on this Blackwell card; a full 1024x1536 decode fits in
    # VRAM anyway with offload, so tiling bought nothing but the crash.
    _pipe = p
    return p


def generate(job: dict) -> dict:
    face = Image.open(job["face"]).convert("RGB")
    g = None
    if job.get("seed") is not None:
        g = torch.Generator(device="cuda").manual_seed(int(job["seed"]))

    p = pipe()
    p.set_ip_adapter_scale(float(job.get("ip_scale", 0.7)))
    t0 = time.time()
    img = p(
        prompt=job["prompt"],
        negative_prompt=NEG,
        ip_adapter_image=face,
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
    result = generate(job)
    # Last line of stdout is the JSON result; the subprocess caller parses it.
    print("RESULT " + json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
