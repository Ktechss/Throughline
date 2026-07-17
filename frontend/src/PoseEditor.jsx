import { useCallback, useEffect, useRef, useState } from 'react'

// Mirrors backend/skeleton.py. OpenPose COCO-18 colours are a convention, not a
// palette choice — ControlNet keys off them, so don't "improve" them.
const LIMBS = [
  ['neck', 'r_shoulder', '#ff0000'], ['neck', 'l_shoulder', '#ff5500'],
  ['r_shoulder', 'r_elbow', '#ffaa00'], ['r_elbow', 'r_wrist', '#ffff00'],
  ['l_shoulder', 'l_elbow', '#aaff00'], ['l_elbow', 'l_wrist', '#55ff00'],
  ['neck', 'r_hip', '#00ff00'], ['r_hip', 'r_knee', '#00ff55'],
  ['r_knee', 'r_ankle', '#00ffaa'], ['neck', 'l_hip', '#00ffff'],
  ['l_hip', 'l_knee', '#00aaff'], ['l_knee', 'l_ankle', '#0055ff'],
  ['neck', 'nose', '#0000ff'], ['nose', 'r_eye', '#5500ff'],
  ['r_eye', 'r_ear', '#aa00ff'], ['nose', 'l_eye', '#ff00ff'],
  ['l_eye', 'l_ear', '#ff00aa'],
]

const GROUPS = {
  head: ['nose', 'neck', 'r_eye', 'l_eye', 'r_ear', 'l_ear'],
  arms: ['r_shoulder', 'r_elbow', 'r_wrist', 'l_shoulder', 'l_elbow', 'l_wrist'],
  legs: ['r_hip', 'r_knee', 'r_ankle', 'l_hip', 'l_knee', 'l_ankle'],
}

const W = 360, H = 480

export default function PoseEditor({ pose, onChange }) {
  const svg = useRef(null)
  const [drag, setDrag] = useState(null)
  const [sel, setSel] = useState(null)

  const joints = pose?.joints || {}

  const toLocal = useCallback((e) => {
    const r = svg.current.getBoundingClientRect()
    return {
      x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
    }
  }, [])

  useEffect(() => {
    if (!drag) return
    const move = (e) => {
      const { x, y } = toLocal(e)
      onChange({ ...pose, joints: { ...pose.joints, [drag]: { ...pose.joints[drag], x, y } } })
    }
    const up = () => setDrag(null)
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
  }, [drag, pose, onChange, toLocal])

  const toggleVis = (name) => {
    const j = joints[name]
    // Hidden, not deleted: an occluded wrist is real information ("hand behind
    // her back"). Removing the point instead reads as "no arm".
    onChange({ ...pose, joints: { ...joints, [name]: { ...j, visible: !j.visible } } })
  }

  const nudge = (name, dx, dy) => {
    const j = joints[name]
    onChange({
      ...pose,
      joints: {
        ...joints,
        [name]: { ...j, x: Math.min(1, Math.max(0, j.x + dx)), y: Math.min(1, Math.max(0, j.y + dy)) },
      },
    })
  }

  return (
    <div className="pose-editor">
      <svg
        ref={svg} className="rig" viewBox={`0 0 ${W} ${H}`}
        style={{ width: W, height: H }}
        onPointerDown={() => setSel(null)}
      >
        <rect x="0" y="0" width={W} height={H} fill="#0a0a0c" />
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={f * W} y1="0" x2={f * W} y2={H} stroke="#1c1c22" strokeWidth="1" />
        ))}
        <line x1="0" y1={H / 2} x2={W} y2={H / 2} stroke="#1c1c22" strokeWidth="1" />

        {LIMBS.map(([a, b, c]) => {
          const ja = joints[a], jb = joints[b]
          if (!ja || !jb || !ja.visible || !jb.visible) return null
          return (
            <line key={`${a}-${b}`} x1={ja.x * W} y1={ja.y * H} x2={jb.x * W} y2={jb.y * H}
              stroke={c} strokeWidth="5" strokeLinecap="round" opacity="0.85" />
          )
        })}

        {Object.entries(joints).map(([name, j]) => (
          <g key={name}>
            <circle
              cx={j.x * W} cy={j.y * H} r={sel === name ? 9 : 6}
              fill={j.visible ? '#fff' : 'transparent'}
              stroke={sel === name ? '#4ea1ff' : '#888'}
              strokeWidth={j.visible ? 2 : 1.5}
              strokeDasharray={j.visible ? '' : '3 2'}
              style={{ cursor: 'grab' }}
              onPointerDown={(e) => { e.stopPropagation(); setSel(name); setDrag(name) }}
            />
          </g>
        ))}
      </svg>

      <div className="joint-list">
        <div className="hint">
          Drag a joint. The rendered figure is what the model sees — this rig{' '}
          <em>is</em> the reference image, not a preview of one.
        </div>
        {Object.entries(GROUPS).map(([g, names]) => (
          <div key={g} className="joint-group">
            <h4>{g}</h4>
            {names.filter((n) => joints[n]).map((n) => (
              <div key={n} className={`joint-row ${sel === n ? 'sel' : ''}`} onClick={() => setSel(n)}>
                <span className="jn">{n}</span>
                <span className="jc">
                  {joints[n].x.toFixed(2)}, {joints[n].y.toFixed(2)}
                </span>
                <span className="jbtns">
                  <button onClick={(e) => { e.stopPropagation(); nudge(n, -0.01, 0) }}>←</button>
                  <button onClick={(e) => { e.stopPropagation(); nudge(n, 0.01, 0) }}>→</button>
                  <button onClick={(e) => { e.stopPropagation(); nudge(n, 0, -0.01) }}>↑</button>
                  <button onClick={(e) => { e.stopPropagation(); nudge(n, 0, 0.01) }}>↓</button>
                  <button
                    className={joints[n].visible ? '' : 'off'}
                    title="Hidden joints stay in the pose but aren't drawn — use for occlusion"
                    onClick={(e) => { e.stopPropagation(); toggleVis(n) }}
                  >{joints[n].visible ? '👁' : '⊘'}</button>
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
