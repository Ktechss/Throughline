import React, { useMemo } from "react";

// A FIGURE DRAWN FROM THE SAME NUMBERS THAT WRITE HER BIO.
//
// Why a drawn silhouette rather than photographs:
//
//   * LICENCE — but not the way this comment first claimed. SMPL/SMPL-X/STAR
//     really are out (non-commercial, and their terms forbid distributing the
//     model even inside a private repo). MakeHuman v1.3.0 assets, however, ARE
//     usable: CC0 per its LICENSE.md section C, and its base mesh is
//     Homunculus08, modelled from scratch in 2013 — no scanned person in it,
//     which matters more here than the licence does. So a mesh was available
//     and was rejected on the merits below, not for want of one.
//     (On the likeness rule generally: the hook is CC0 section 4(c), where the
//     affirmer disclaims responsibility for clearing OTHER people's rights —
//     not, as previously written here, that CC0 omits publicity rights.
//     Section 1(iii) does purport to waive them; a waiver simply cannot reach
//     rights the affirmer never owned.)
//   * LEGIBILITY AT 92px, which is the whole argument and was measured. These
//     ladders are deliberate CARICATURE: bust spans 11.5 -> 21.5 half-units, a
//     near-2x swing no real body performs. An anatomically correct mesh driven
//     by real measure targets moves one notch by 1-3 PIXELS at this size,
//     against ~4 here — and the swing cannot be restored without pushing the
//     targets past +/-1, which tears normals and forfeits the correctness that
//     was the reason to use a mesh at all. Exaggeration is the feature.
//   * CONTINUITY. Six axes at five rungs is 15,625 combinations. A library of
//     stock figures snaps to the nearest of N; this moves WITH the slider, so
//     "thighs one notch thicker" is visible as exactly that.
//   * NO DEPTH DATUM EXISTS. Every axis here is a width, a length, or one
//     indentation ratio, and build_clause's vocabulary has no projection in it.
//     A side view or a rotatable mesh would have to INVENT depth the pipeline
//     never sends — and nothing in this repo could see that it was invented.
//   * HONESTY. It is unmistakably a diagram. A photoreal preview would imply
//     the pipeline reproduces it, and this project MEASURED that it does not —
//     text regresses toward slim, which is the whole reason these controls
//     exist. A schematic promises proportions, which is what is being set.
//   * It cannot be a likeness of anyone, which CLAUDE.md requires absolutely.
//
// GEOMETRY NOTE — the thing that was wrong the first time. Waist cannot be an
// absolute width. "Straight" means NOT INDENTED RELATIVE TO bust and hips, not
// "wide": with an absolute ladder, a slim build got waist 15 against bust 12
// and hips 14, so the narrowest build rendered as a barrel. Waist is therefore
// a RATIO of the narrower of bust/hips, which makes the hourglass read
// correctly at every build instead of only in the middle of the range.

const CX = 50;
const VB = { w: 100, h: 220 };

// 7.5 HEADS, because that is what body.frame says next to it.
//
// Drawn at r=9.6 this figure was 10.2 heads tall — past even the 8.5 that
// prompt.py's body.frame note calls out as "the fashion-illustration
// proportion", which "reads as uncanny". So the diagram was contradicting the
// sentence printed beside it, and flattering the figure while doing it.
// FLOOR - HEAD_TOP over 7.5, halved.
const FLOOR = 206;
const HEAD_R = 13.1;
const HEAD_CY = 4 + HEAD_R;

const at = (arr, i, dflt) => arr[Math.max(0, Math.min(arr.length - 1, i ?? dflt))];

// Half-widths in viewBox units. Index matches BODY_AXES on the server, so a
// rung the backend can emit is a rung this can draw — one ladder, not two.
const SHOULDER = [15.5, 18.5, 22];              // narrow | in line | broad
const BUST     = [11.5, 13.5, 16.5, 19, 21.5];  // small -> heavy
const HIPS     = [13.5, 16, 18.5, 21.5, 24];    // narrow -> very wide
const THIGH    = [7.5, 8.8, 10.2, 11.8, 13.4];  // slim -> very full
// Waist as a FRACTION of min(bust, hips). See the geometry note above.
const WAIST_R  = [0.94, 0.86, 0.74, 0.64, 0.55];
// Leg length moves the HIP LINE against a fixed total height — that is what
// "leg-to-torso ratio" means. Lengthening the legs alone would just grow her.
const HIP_Y    = [110, 105, 100, 95, 89];

function smooth(points, close = false) {
  if (points.length < 2) return "";
  const p = close ? [...points, points[0]] : points;
  let d = `M ${p[0][0].toFixed(2)} ${p[0][1].toFixed(2)}`;
  for (let i = 0; i < p.length - 1; i++) {
    const p0 = p[i - 1] || p[i];
    const p1 = p[i];
    const p2 = p[i + 1];
    const p3 = p[i + 2] || p2;
    d += ` C ${(p1[0] + (p2[0] - p0[0]) / 6).toFixed(2)} ${(p1[1] + (p2[1] - p0[1]) / 6).toFixed(2)},`
      +  ` ${(p2[0] - (p3[0] - p1[0]) / 6).toFixed(2)} ${(p2[1] - (p3[1] - p1[1]) / 6).toFixed(2)},`
      +  ` ${p2[0].toFixed(2)} ${p2[1].toFixed(2)}`;
  }
  return d + (close ? " Z" : "");
}

// SEPARATE SHAPES, FILL ONLY, NO STROKE.
//
// Two earlier attempts and why they failed, so nobody re-tries them:
//
//   * torso + two legs, each stroked: where they overlapped at the crotch the
//     two outlines drew a lens-shaped seam straight through the figure.
//   * one continuous path traced down the outside of a leg and back up its
//     inside: the outline reverses direction 180 degrees at the ankle, and
//     Catmull-Rom overshoots hard at a reversal, so the legs came out as bent
//     sticks with a hook at the hip.
//
// The seam only existed because of the STROKE. Overlapping fills of the same
// paint have no join to show, so the union just reads as one body — no
// traversal order to get wrong, no reversal for the spline to trip on.
function leg(side, { hip, thigh, crotchY, ankleY }) {
  const s = side;
  const topCx = CX + s * hip * 0.44;
  const ankCx = CX + s * hip * 0.28;
  const pts = [0, 0.42, 0.72, 1].map((t) => ({
    y: crotchY + (ankleY - crotchY) * t,
    cx: topCx + (ankCx - topCx) * t,
    w: thigh * (1 - t) + thigh * 0.30 * t,
  }));
  return smooth([
    ...pts.map((p) => [p.cx + s * p.w, p.y]),
    ...[...pts].reverse().map((p) => [p.cx - s * p.w, p.y]),
  ], true);
}

export function BodySilhouette({ axes = {}, className, showGuides = false }) {
  const g = useMemo(() => {
    const sh = at(SHOULDER, axes.shoulders, 1);
    const bu = at(BUST, axes.bust, 2);
    const hi = at(HIPS, axes.hips, 2);
    const th = at(THIGH, axes.thighs, 2);
    const hipY = at(HIP_Y, axes.legs, 3);
    const wa = Math.min(bu, hi) * at(WAIST_R, axes.waist, 2);

    const shoulderY = 44, bustY = 60, waistY = 80;
    const crotchY = hipY + 16;
    const ankleY = 202;

    // Torso runs PAST the crotch so the leg tops are buried inside it rather
    // than butting against its edge.
    const half = [[4.2, 32], [5.0, 38], [sh, shoulderY], [bu, bustY],
                  [wa, waistY], [hi, hipY], [hi * 0.92, crotchY + 6]];
    const torso = smooth([
      ...half.map(([w, y]) => [CX + w, y]),
      ...[...half].reverse().map(([w, y]) => [CX - w, y]),
    ], true);

    // Arms carry no axis, but without them the torso reads as a dress.
    const armAt = (s) => smooth([
      [CX + s * (sh - 1.0), shoulderY + 2],
      [CX + s * (sh + 1.8), bustY + 6],
      [CX + s * (hi + 1.2), waistY + 14],
      [CX + s * (hi + 1.0), hipY + 10],
    ]);

    return {
      torso,
      legs: [leg(1, { hip: hi, thigh: th, crotchY, ankleY }),
             leg(-1, { hip: hi, thigh: th, crotchY, ankleY })],
      arms: [armAt(1), armAt(-1)],
      guides: { bustY, waistY, hipY },
    };
  }, [axes]);

  return (
    <svg viewBox={`0 0 ${VB.w} ${VB.h}`} className={className}
      role="img" aria-label="Body proportion diagram"
      preserveAspectRatio="xMidYMid meet">
      <defs>
        {/* userSpaceOnUse so the ramp spans the WHOLE figure. The default
            (objectBoundingBox) restarts the gradient inside every shape, so
            the legs would begin again at pink halfway down the body.
            Stops are fully OPAQUE and the group carries the opacity instead:
            translucent fills compound where the torso, legs and arms overlap,
            which drew bright bands across the hips and dark ones down the
            arms — the same seam problem in a different disguise. */}
        <linearGradient id="bodyFill" gradientUnits="userSpaceOnUse"
          x1="0" y1="8" x2="0" y2="206">
          <stop offset="0%" stopColor="rgb(244 114 182)" />
          <stop offset="100%" stopColor="rgb(129 140 248)" />
        </linearGradient>
      </defs>

      {/* Guides turn it into a measuring instrument: you can see WHERE the
          waist sits, not merely that it is narrower than something. */}
      {showGuides && (
        <g stroke="currentColor" strokeWidth="0.4" opacity="0.18" strokeDasharray="2 3">
          <line x1="10" y1={g.guides.bustY} x2="90" y2={g.guides.bustY} />
          <line x1="10" y1={g.guides.waistY} x2="90" y2={g.guides.waistY} />
          <line x1="10" y1={g.guides.hipY} x2="90" y2={g.guides.hipY} />
        </g>
      )}

      {/* One group, one paint, no strokes — see the note above the leg helper.
          The arms are stroked because a line IS the shape there, and they sit
          under the torso so their shoulder ends are hidden. */}
      <g fill="url(#bodyFill)" opacity="0.30">
        {g.arms.map((d, i) => (
          <path key={`a${i}`} d={d} fill="none" stroke="url(#bodyFill)"
            strokeWidth="5" strokeLinecap="round" />
        ))}
        {g.legs.map((d, i) => <path key={`l${i}`} d={d} />)}
        <path d={g.torso} />
        <circle cx={CX} cy={HEAD_CY} r={HEAD_R} />
      </g>
    </svg>
  );
}

export default BodySilhouette;
