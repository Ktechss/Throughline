"""Editable pose skeleton, rendered to an image the model can look at.

## Why this exists

Text pose control does not work on nano-banana. Asked for a profile it returned
yaw -1.3 degrees; asked for a look-down, -0.6. Three of four probes came back
frontal (see FINDINGS.md). So "she is standing in three-quarter profile" is a
sentence the model is free to ignore, and it does.

A picture of a pose is harder to ignore than a sentence about one.

## What this is NOT (yet)

This renders the **OpenPose 18-point** layout on black — the exact convention
ControlNet expects. That is deliberate: today the figure is passed to
nano-banana as an ordinary reference image and the model is *asked* to match it,
which is suggestion, not conditioning. If this proves too weak, the same renderer
feeds a real ControlNet endpoint with no changes here.

⚠ Passing the pose costs a reference slot, and references are not free: three
face crops scored 0.547 against one crop's 0.811. So the pose image may buy pose
at the price of identity. That trade is UNMEASURED. Measure it before trusting
it, and measure it by reading back the **yaw**, never the similarity — a model
that ignores the pose returns a frontal image, and frontal images score high.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

# OpenPose COCO-18 order. Index IS the identity of the joint — never reorder.
NAMES = [
    "nose", "neck",
    "r_shoulder", "r_elbow", "r_wrist",
    "l_shoulder", "l_elbow", "l_wrist",
    "r_hip", "r_knee", "r_ankle",
    "l_hip", "l_knee", "l_ankle",
    "r_eye", "l_eye", "r_ear", "l_ear",
]
INDEX = {n: i for i, n in enumerate(NAMES)}

# (a, b, colour) — OpenPose's canonical limb colours. ControlNet keys off these,
# so they are not decoration; don't "tidy" them into a nicer palette.
LIMBS: list[tuple[str, str, tuple[int, int, int]]] = [
    ("neck", "r_shoulder", (255, 0, 0)),
    ("neck", "l_shoulder", (255, 85, 0)),
    ("r_shoulder", "r_elbow", (255, 170, 0)),
    ("r_elbow", "r_wrist", (255, 255, 0)),
    ("l_shoulder", "l_elbow", (170, 255, 0)),
    ("l_elbow", "l_wrist", (85, 255, 0)),
    ("neck", "r_hip", (0, 255, 0)),
    ("r_hip", "r_knee", (0, 255, 85)),
    ("r_knee", "r_ankle", (0, 255, 170)),
    ("neck", "l_hip", (0, 255, 255)),
    ("l_hip", "l_knee", (0, 170, 255)),
    ("l_knee", "l_ankle", (0, 85, 255)),
    ("neck", "nose", (0, 0, 255)),
    ("nose", "r_eye", (85, 0, 255)),
    ("r_eye", "r_ear", (170, 0, 255)),
    ("nose", "l_eye", (255, 0, 255)),
    ("l_eye", "l_ear", (255, 0, 170)),
]

JOINT_COLOURS = [
    (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0),
    (85, 255, 0), (0, 255, 0), (0, 255, 85), (0, 255, 170), (0, 255, 255),
    (0, 170, 255), (0, 85, 255), (0, 0, 255), (85, 0, 255), (170, 0, 255),
    (255, 0, 255), (255, 0, 170), (255, 0, 85),
]


@dataclass
class Joint:
    """Normalised 0..1 so a pose is resolution-independent.

    `visible=False` keeps the joint in the list but drops it from the render —
    an occluded wrist is real information ("hand behind her back"), and deleting
    the point would instead read as "no arm".
    """
    x: float
    y: float
    visible: bool = True


@dataclass
class Pose:
    name: str = "untitled"
    joints: dict[str, Joint] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"name": self.name,
                "joints": {k: {"x": v.x, "y": v.y, "visible": v.visible}
                           for k, v in self.joints.items()}}

    @classmethod
    def from_json(cls, d: dict) -> Pose:
        return cls(name=d.get("name", "untitled"),
                   joints={k: Joint(**v) for k, v in d.get("joints", {}).items()})


def default_pose(name: str = "standing") -> Pose:
    """A neutral standing figure, facing the camera.

    Proportions are roughly 7.5 heads, which is a real adult rather than the
    8.5-head fashion-plate the generators drift toward on their own.
    """
    j = {
        "nose": (0.500, 0.090), "neck": (0.500, 0.160),
        "r_shoulder": (0.430, 0.175), "r_elbow": (0.405, 0.290), "r_wrist": (0.395, 0.400),
        "l_shoulder": (0.570, 0.175), "l_elbow": (0.595, 0.290), "l_wrist": (0.605, 0.400),
        "r_hip": (0.462, 0.440), "r_knee": (0.455, 0.640), "r_ankle": (0.450, 0.850),
        "l_hip": (0.538, 0.440), "l_knee": (0.545, 0.640), "l_ankle": (0.550, 0.850),
        "r_eye": (0.482, 0.078), "l_eye": (0.518, 0.078),
        "r_ear": (0.462, 0.085), "l_ear": (0.538, 0.085),
    }
    return Pose(name=name, joints={k: Joint(x, y) for k, (x, y) in j.items()})


def render(pose: Pose, width: int = 768, height: int = 1024,
           thickness: int = 8, radius: int = 5) -> Image.Image:
    """Draw the figure on black, OpenPose style.

    Black background is not aesthetic — ControlNet's OpenPose preprocessor emits
    black, and nano-banana reads the high-contrast figure more cleanly than it
    reads lines on white.
    """
    im = Image.new("RGB", (width, height), (0, 0, 0))
    d = ImageDraw.Draw(im)

    def px(j: Joint) -> tuple[float, float]:
        return (j.x * width, j.y * height)

    for a, b, colour in LIMBS:
        ja, jb = pose.joints.get(a), pose.joints.get(b)
        if not ja or not jb or not ja.visible or not jb.visible:
            continue
        d.line([px(ja), px(jb)], fill=colour, width=thickness)

    for name, j in pose.joints.items():
        if not j.visible or name not in INDEX:
            continue
        x, y = px(j)
        c = JOINT_COLOURS[INDEX[name] % len(JOINT_COLOURS)]
        d.ellipse([x - radius, y - radius, x + radius, y + radius], fill=c)
    return im


def render_bytes(pose: Pose, **kw) -> bytes:
    buf = BytesIO()
    render(pose, **kw).save(buf, format="PNG")
    return buf.getvalue()


def save(pose: Pose, dest: Path, **kw) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    render(pose, **kw).save(dest)
    return dest


def describe(pose: Pose) -> str:
    """A coarse text fallback that rides ALONGSIDE the image, never instead of it.

    Deliberately vague — "turned to her left", not "-34 degrees". The geometry is
    the image's job. This exists only so the prompt isn't silent about the pose,
    and because a wrong precise number is worse than an honest vague one.
    """
    n, ls, rs = pose.joints.get("nose"), pose.joints.get("l_shoulder"), pose.joints.get("r_shoulder")
    if not (n and ls and rs):
        return "as shown in the pose reference image"
    span = abs(ls.x - rs.x)
    if span < 0.05:
        return "in profile, as shown in the pose reference image"
    centre = (ls.x + rs.x) / 2
    off = (n.x - centre) / span
    if abs(off) < 0.12:
        facing = "facing the camera"
    elif off > 0:
        facing = "turned slightly to her left"
    else:
        facing = "turned slightly to her right"
    return f"{facing}, as shown in the pose reference image"
