"""The three vendors, as classes, and every model they can render.

Deliberately THIN. The HTTP work in providers.py is correct and hard-won — the
kie poll budget, poyo's reference hosting, fal's reclaim-on-timeout — so these
wrap it rather than reimplement it. What changes is the SHAPE: a provider is now
a thing with a declared capability set, not a function in a dict plus an `if`
branch buried in generate().

Adding a vendor: one class, one register_provider call.
Adding a model:   one ModelSpec row.
Neither touches generate.py, main.py, or any call site.
"""
from __future__ import annotations

from pathlib import Path

from . import providers
from .registry import REGISTRY, Mode, ModelSpec, Provider, Purpose

_ALL = frozenset(Purpose)
_EDIT_T2I = frozenset({Mode.EDIT, Mode.TEXT2IMG})
# The seedream endpoints say what they are in their own names:
# "seedream/5-pro-IMAGE-TO-IMAGE", "seedream/4.5-EDIT". They cannot render from
# a prompt alone. Declaring otherwise cost three failed attempts on a real
# text2img call before it fell through to nano — the registry recovered, but it
# should not have had to. A capability is only useful if it is true.
_EDIT_ONLY = frozenset({Mode.EDIT})


class KieProvider(Provider):
    name, label, key_env = "kie", "kie.ai", "KIE_API_KEY"
    usd, seconds = 0.12, 220
    note = "same picture as fal for 40% of the price; 24 credits per 4K edit"

    def render(self, *, spec, prompt, refs, aspect, resolution, system="",
               seed=None, progress=None, safety_tolerance=None, extra=None):
        # system is deliberately dropped: kie takes no system field, which is
        # why capture_clause puts the doctrine inside the prompt itself.
        return providers.kie_generate(
            prompt=prompt, refs=list(refs), aspect=aspect,
            resolution=resolution, progress=progress,
            model=spec.key, seed=seed)

    def credits(self, force: bool = False):
        try:
            return providers.kie_credits(force=force)
        except Exception:                                   # noqa: BLE001
            return None


class PoyoProvider(Provider):
    name, label, key_env = "poyo", "poyo.ai", "POYO_API_KEY"
    usd, seconds = 0.175, 265
    note = ("35 credits per 4K edit — its advertised $0.070 was not what the "
            "API charged; needs a kie key to host references")

    def render(self, *, spec, prompt, refs, aspect, resolution, system="",
               seed=None, progress=None, safety_tolerance=None, extra=None):
        return providers.poyo_generate(
            prompt=prompt, refs=list(refs), aspect=aspect,
            resolution=resolution, progress=progress,
            model=spec.key, seed=seed)


class FalProvider(Provider):
    """fal, including the moderation retry and reclaim-on-timeout.

    This was ~90 lines inline in generate(), which is why "try the next
    provider" could never include fal — it was not the same kind of thing as
    the others. The behaviour is unchanged; only its home is.
    """
    name, label, key_env = "fal", "fal.ai", "FAL_KEY"
    usd, seconds = 0.30, 66
    note = "dearest and 3x faster; the fallback everything else falls to"

    def render(self, *, spec, prompt, refs, aspect, resolution, system="",
               seed=None, progress=None, safety_tolerance=None, extra=None):
        import fal_client
        from .config import GPT_IMAGE_SIZE
        from .generate import (CLIENT_TIMEOUT, CONTENT_RETRIES, START_TIMEOUT,
                               _reclaim, upload)

        urls = [upload(p) for p in refs] if refs else []

        # Arguments are PER MODEL. fal ignores foreign fields rather than
        # rejecting them, which is worse than an error: send nano-banana's
        # aspect_ratio to gpt-image-2 and you get a default-sized image while
        # believing you asked for 4K, and the face-pixel count silently drops
        # under the gate's floor.
        if spec.key.startswith("gpt-image"):
            args = {"prompt": f"{system}\n\n{prompt}" if system else prompt,
                    "image_size": GPT_IMAGE_SIZE}
        else:
            args = {"prompt": prompt, "aspect_ratio": aspect,
                    "resolution": resolution, "num_images": 1,
                    "output_format": "png"}
            if system:
                args["system_prompt"] = system
            # fal's documented moderation dial (1 strictest .. 6 least). Opt-in
            # per request, never a raised global default.
            if safety_tolerance:
                args["safety_tolerance"] = str(safety_tolerance)
        if urls:
            args["image_urls"] = urls
        if seed is not None and spec.seed_key:
            args[spec.seed_key] = seed
        if extra:
            args |= extra

        last = None
        for attempt in range(CONTENT_RETRIES):
            try:
                r = fal_client.subscribe(
                    spec.remote, arguments=args, with_logs=False,
                    start_timeout=START_TIMEOUT, client_timeout=CLIENT_TIMEOUT)
                r["model"] = spec.key
                r["seed"] = seed if spec.seed_key else None
                return r
            except Exception as exc:                        # noqa: BLE001
                last = exc
                if providers.is_content_refusal(exc):
                    if progress is not None:
                        progress["retry"] = attempt + 1
                        progress["stage"] = "moderation retry"
                    continue
                # A TIMEOUT is impatience, not failure: the request is still
                # running on fal and will still be billed, so go and fetch it
                # rather than raising and losing a paid generation.
                if "timed out" in str(exc).lower():
                    got = _reclaim(exc, spec.remote, progress)
                    if got is not None:
                        got["model"] = spec.key
                        got["seed"] = seed if spec.seed_key else None
                        return got
                raise
        raise providers.ProviderError(f"fal/{spec.key}: {last}")


for _p in (KieProvider(), PoyoProvider(), FalProvider()):
    REGISTRY.register_provider(_p)


# --------------------------------------------------------------------- models
#
# One row per renderable model. Everything that used to be a scattered constant
# (config.EDIT, config.TEXT2IMG, config.SCENE_EDIT, the GPT_IMAGE set) or a
# nested dict (providers.KIE_MODELS) is here, in one shape, comparable.
#
# `purposes` is where the routing rules actually live. gpt-image-2 carries
# FACE_SEED and nothing else: it measured 0.813 against nano-banana's 0.678 on
# exactly that frontal studio close-up, and the master face compounds forever —
# but it is the dearest route and has no aspect control, so it must not quietly
# become the default for daily shots.

_NANO_ASPECTS = frozenset({"1:1", "3:4", "4:3", "9:16", "16:9", "2:3", "3:2",
                           "4:5", "5:4", "21:9"})
_SEEDREAM_ASPECTS = frozenset({"1:1", "3:4", "4:3", "9:16", "16:9", "2:3", "3:2"})
_PASSTHROUGH = {"1K": "1K", "2K": "2K", "4K": "4K"}

_MODELS = [
    # ---- kie ------------------------------------------------------------
    ModelSpec(key="nano-banana-pro", provider="kie", remote="nano-banana-pro",
              label="Nano Banana Pro", modes=_EDIT_T2I, purposes=_ALL,
              usd_4k=0.12, max_refs=8, aspects=_NANO_ASPECTS,
              res_map=_PASSTHROUGH, res_key="resolution", refs_key="image_input",
              extra={"output_format": "png"}),
    ModelSpec(key="nano-banana-2", provider="kie", remote="nano-banana-2",
              label="Nano Banana 2", modes=_EDIT_T2I, purposes=_ALL,
              usd_4k=0.09, max_refs=14, aspects=_NANO_ASPECTS,
              res_map=_PASSTHROUGH, res_key="resolution", refs_key="image_input",
              extra={"output_format": "png"}),
    ModelSpec(key="seedream-4.5", provider="kie", remote="seedream/4.5-edit",
              label="Seedream 4.5", modes=_EDIT_ONLY, purposes=_ALL,
              usd_4k=0.0325, max_refs=14, aspects=_SEEDREAM_ASPECTS,
              res_map={"1K": "basic", "2K": "basic", "4K": "high"},
              res_key="quality"),
    ModelSpec(key="seedream-5-pro", provider="kie",
              remote="seedream/5-pro-image-to-image", label="Seedream 5 Pro",
              modes=_EDIT_ONLY, purposes=_ALL, usd_4k=0.075, max_refs=10,
              aspects=_SEEDREAM_ASPECTS,
              # No 4K tier exists: basic=1K, high=2K. 4K maps to the ceiling
              # rather than to an error.
              res_map={"1K": "basic", "2K": "high", "4K": "high"},
              res_key="quality", ceiling="2K"),
    ModelSpec(key="seedream-5-lite", provider="kie",
              remote="seedream/5-lite-image-to-image", label="Seedream 5 Lite",
              modes=_EDIT_ONLY, purposes=_ALL, usd_4k=0.0275, max_refs=14,
              aspects=_SEEDREAM_ASPECTS,
              res_map={"1K": "basic", "2K": "basic", "4K": "ultra"},
              res_key="quality"),

    # ---- poyo -----------------------------------------------------------
    ModelSpec(key="poyo-nano-banana-pro", provider="poyo",
              remote="nano-banana-pro", label="Nano Banana Pro (poyo)",
              modes=_EDIT_T2I, purposes=_ALL, usd_4k=0.175, max_refs=8,
              aspects=_NANO_ASPECTS, res_map=_PASSTHROUGH),

    # ---- fal ------------------------------------------------------------
    ModelSpec(key="fal-nano-banana-pro", provider="fal",
              remote="fal-ai/nano-banana-pro/edit", label="Nano Banana Pro (fal)",
              modes=frozenset({Mode.EDIT}), purposes=_ALL, usd_4k=0.30,
              max_refs=8, aspects=_NANO_ASPECTS, res_map=_PASSTHROUGH,
              seed_key="seed"),
    ModelSpec(key="fal-nano-banana-pro-t2i", provider="fal",
              remote="fal-ai/nano-banana-pro", label="Nano Banana Pro (fal, t2i)",
              modes=frozenset({Mode.TEXT2IMG}), purposes=_ALL, usd_4k=0.30,
              aspects=_NANO_ASPECTS, res_map=_PASSTHROUGH, seed_key="seed"),
    # FACE_SEED only, and on purpose. Measured 0.813 vs nano's 0.678 on the
    # frontal studio close-up the master face actually is; it has no aspect
    # control and is the dearest route, so it must never become the daily
    # default by accident.
    ModelSpec(key="gpt-image-2", provider="fal", remote="fal-ai/gpt-image-2",
              label="GPT-Image-2", modes=frozenset({Mode.TEXT2IMG}),
              purposes=frozenset({Purpose.FACE_SEED}), usd_4k=0.30,
              seed_key="seed",
              note="best measured master face; no aspect control"),
    ModelSpec(key="gpt-image-2-edit", provider="fal",
              remote="openai/gpt-image-2/edit", label="GPT-Image-2 (edit)",
              modes=frozenset({Mode.EDIT}),
              purposes=frozenset({Purpose.FACE_SEED}), usd_4k=0.30,
              seed_key="seed"),
]

for _m in _MODELS:
    REGISTRY.register_model(_m)
