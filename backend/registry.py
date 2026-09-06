"""WHO renders WHAT — one place, so the Settings order actually governs.

WHY THIS EXISTS. The owner set a provider precedence in Settings and it was
ignored, because the codebase spoke two vocabularies that never met:

    fal      "fal-ai/gpt-image-2"    provider AND model fused into one string
    kie      "seedream-5-pro"        model only, looked up in a spec dict

`generate()` consulted the Settings chain only when the caller passed no
endpoint — and seven call sites in main.py passed one. Each of those silently
opted out of the user's configuration. Character creation died on exactly that:
the master-face step hardcoded `fal-ai/gpt-image-2`, the FAL_KEY was a
placeholder, and kie sat unused with 890 credits and first place in Settings.

Adding a model meant editing a spec table and possibly call sites; adding a
provider meant editing three files. So:

    * A CALL SITE NAMES A PURPOSE, never a provider and never an endpoint.
      `Purpose.FACE_SEED`, not "fal-ai/gpt-image-2".
    * A MODEL IS ONE ROW in MODELS. Provider, what it can do, what it accepts,
      what it costs.
    * A PROVIDER IS ONE CLASS implementing Provider.
    * THE ORDER IS READ IN ONE PLACE — Registry.candidates(). A hardcoded
      endpoint is not expressible any more, so this cannot rot back.

WHAT A PURPOSE IS. Not "which model" — that is the registry's job — but what
the image is FOR, because that is the only thing a call site actually knows and
it is what determines the real constraints:

    SHOT        her, from references. The daily path.
    FACE_SEED   the master-face candidates. gpt-image-2 measured 0.813 against
                nano-banana's 0.678 on exactly this frontal studio close-up, and
                this one image compounds forever, so quality outranks price
                here and nowhere else.
    TURNAROUND  a garment or body sheet. Not a photo of her; never gated.
    ROOM        a corner of her home. No people, so no references.
    SCENE       several characters in one frame.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Purpose(str, Enum):
    SHOT = "shot"
    FACE_SEED = "face_seed"
    TURNAROUND = "turnaround"
    ROOM = "room"
    SCENE = "scene"


# Every purpose needs one of these two shapes. Kept separate from Purpose
# because a provider declares what it CAN do, and a purpose declares what it
# NEEDS — the registry matches them.
class Mode(str, Enum):
    EDIT = "edit"           # references in, image out
    TEXT2IMG = "text2img"   # prompt only


# What each purpose asks for. `refs_expected` is a default: SHOT with no
# references is still a SHOT, and the registry picks the text2img variant.
# `prefer` names models this purpose wants FIRST, best first, ahead of price.
#
# Everything else falls back to cheapest-that-can-do-it, which is right when
# the measured quality spread between providers (0.016) is inside this
# project's own seed-to-seed variance. FACE_SEED is the exception, and the
# codebase already argues why in two places: the master face is "the one image
# that compounds forever", and gpt-image-2 measured 0.813 against nano-banana's
# 0.678 on exactly that frontal studio close-up.
#
# Without this, faces rendered on nano-banana-2 because it is $0.09 against
# nano-banana-pro's $0.12 — three cents, on the single image every later shot
# is scored against. Owner observed the quality difference before the code
# admitted it.
PURPOSE_NEEDS: dict[Purpose, dict] = {
    Purpose.SHOT:       {"mode": Mode.EDIT,     "gated": True},
    Purpose.FACE_SEED:  {"mode": Mode.TEXT2IMG, "gated": False,
                         "prefer": ("gpt-image-2", "gpt-image-2-edit",
                                    "nano-banana-pro", "fal-nano-banana-pro")},
    Purpose.TURNAROUND: {"mode": Mode.EDIT,     "gated": False},
    Purpose.ROOM:       {"mode": Mode.TEXT2IMG, "gated": False},
    Purpose.SCENE:      {"mode": Mode.EDIT,     "gated": True},
}


@dataclass(frozen=True)
class ModelSpec:
    """One renderable model on one provider. The whole row.

    `key` is ours and stable; `remote` is whatever that provider calls it. The
    two were previously the same string for fal and different for kie, which is
    most of why the vocabularies never met.
    """
    key: str
    provider: str
    remote: str
    label: str
    modes: frozenset            # Mode.EDIT / Mode.TEXT2IMG
    purposes: frozenset         # which Purposes this model is allowed to serve
    usd_4k: float
    max_refs: int = 8
    aspects: frozenset | None = None        # None = accepts anything
    res_map: dict = field(default_factory=dict)
    res_key: str = "resolution"
    refs_key: str = "image_urls"
    extra: dict = field(default_factory=dict)
    # The API field a seed goes in, IF the provider takes one. None means this
    # model cannot be seeded — and a run must then record seed=None rather than
    # the seed that was asked for. See generate(); the resellers take no seed,
    # and the ledger used to claim otherwise on every seeded request.
    seed_key: str | None = None
    ceiling: str | None = None
    note: str = ""

    def can(self, purpose: Purpose, mode: Mode) -> bool:
        return purpose in self.purposes and mode in self.modes


class Provider(ABC):
    """One vendor. Subclass, register, done — no other file changes.

    fal used to be an inline `if` branch inside generate() while kie and poyo
    were functions in a dict, which is why "try the next provider" could not be
    written once.
    """
    name: str
    label: str
    key_env: str
    usd: float
    seconds: int
    note: str = ""

    def available(self) -> bool:
        """Key present AND not an obvious placeholder.

        The placeholder check is not fussiness: `.env` ships with
        FAL_KEY=your-fal-key, and treating that as a usable credential is how a
        build failed with 'Authentication is required' while a paid, configured,
        first-in-Settings provider went untried.
        """
        v = (os.environ.get(self.key_env) or "").strip()
        return bool(v) and not v.lower().startswith(("your-", "changeme", "xxx"))

    @abstractmethod
    def render(self, *, spec: ModelSpec, prompt: str, refs: list[Path],
               aspect: str, resolution: str, system: str = "",
               seed: int | None = None, progress: dict | None = None,
               safety_tolerance=None, extra: dict | None = None) -> dict:
        """Return fal's response shape: {"images": [{"url": ...}], ...}.

        Also returns "model" (what actually rendered) and "seed" (what was
        actually used, or None) so the ledger records fact, not intent.
        """

    def credits(self, force: bool = False):
        """Remaining balance, or None if this provider does not report one."""
        return None


class Registry:
    """The single place that answers "who should render this, and in what order".

    Every consumer goes through `candidates()`. That is the whole design: the
    Settings precedence is applied here and nowhere else, so no call site can
    route around it by naming an endpoint.
    """

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}
        self._models: dict[str, ModelSpec] = {}

    def register_provider(self, p: Provider) -> None:
        self._providers[p.name] = p

    def register_model(self, m: ModelSpec) -> None:
        self._models[m.key] = m

    @property
    def providers(self) -> dict[str, Provider]:
        return dict(self._providers)

    @property
    def models(self) -> dict[str, ModelSpec]:
        return dict(self._models)

    def model(self, key: str | None) -> ModelSpec | None:
        return self._models.get(key) if key else None

    def candidates(self, purpose: Purpose, *, has_refs: bool,
                   model: str | None = None,
                   order: list[str] | None = None) -> list[tuple[Provider, ModelSpec]]:
        """Every (provider, model) that can serve this purpose, best first.

        Ordering is the user's Settings precedence, full stop. Within one
        provider, an explicitly requested model wins; otherwise the cheapest
        model that can do the job, because the measured quality spread between
        them (0.016) is inside this project's own seed-to-seed variance.

        Returns [] when nothing can serve it — the caller must say so rather
        than fall through to a default that ignores the request.
        """
        need = PURPOSE_NEEDS[purpose]
        mode = need["mode"] if not has_refs else Mode.EDIT
        if has_refs:
            mode = Mode.EDIT
        elif need["mode"] is Mode.EDIT:
            # A purpose that normally edits, invoked with no references, still
            # has to render something.
            mode = Mode.TEXT2IMG

        order = order or list(self._providers)
        rank = {n: i for i, n in enumerate(order)}

        out: list[tuple[Provider, ModelSpec]] = []
        for spec in self._models.values():
            prov = self._providers.get(spec.provider)
            if prov is None or not prov.available():
                continue
            if spec.provider not in rank:          # disabled in Settings
                continue
            if not spec.can(purpose, mode):
                continue
            out.append((prov, spec))

        prefer = need.get("prefer") or ()

        def sort_key(pair):
            prov, spec = pair
            # Provider order is the user's Settings and always wins. Within a
            # provider: the purpose's preference, then an explicitly requested
            # model, then price.
            pref = prefer.index(spec.key) if spec.key in prefer else len(prefer)
            asked = model and spec.key == model
            return (rank[spec.provider], pref, 0 if asked else 1, spec.usd_4k)

        return sorted(out, key=sort_key)


REGISTRY = Registry()
