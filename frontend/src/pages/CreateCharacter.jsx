import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, Home, Loader2, Sparkles, Upload, X } from "lucide-react";
import { api } from "@/api/throughline";
import { Field, inputClass } from "@/components/ui/field";
import { ChipRow, Chip } from "@/components/ui/chip";
import { RangeField } from "@/components/ui/range";
import BodyBuilder from "@/components/studio/BodyBuilder";
import { Button } from "@/components/ui/modal";
import { toast } from "@/components/ui/use-toast";
import { cn } from "@/lib/utils";

// CREATING HER, one question at a time.
//
// This was a modal with 24 controls in two columns, whose own comment still said
// "sixteen". Everything was on screen at once because "a control you have to go
// looking for may as well not exist" — true, but the answer to that is an order,
// not a wall. Five steps, each about one thing, and the only required field is on
// the first one: a name alone is a complete character, because Claude fills in
// whatever is left blank.
//
// It is a ROUTE, not a modal, for a reason that bit in the old version: a failed
// create wrote its error into a banner that lived *behind* the modal, so the user
// saw the form sit there having apparently done nothing. A page can show its own
// error.

const FACE_SHAPES = ["oval", "round", "square", "heart", "diamond", "oblong"];
const BODY_TYPES = ["slim", "athletic", "curvy", "voluptuous", "full-figured"];
// HOME_CORNERS in backend/main.py. Shown so the cost of filling in the home field
// is visible before it is paid, not after.
const HOME_CORNER_COUNT = 10;

// EVERY CHIP AXIS, in one list, in one shape.
//
// `face_shape` and `build` used to be their own useState while the other twelve
// lived in a `picks` object — two mechanisms for one kind of value. That split is
// why the old "Body & age" badge needed a hardcoded `+ 1` to look right. Here
// they are all just keys, so counting is honest and the wire format has a single
// source.
const FACE_AXES = ["face_shape", "cheekbones", "jawline", "chin", "eyes", "brows", "nose", "lips"];
const SKIN_AXES = ["skin_tone", "skin_undertone", "hair_colour", "hair_length", "hair_texture"];
const BODY_AXES = ["build"];
const PICK_KEYS = [...FACE_AXES, ...SKIN_AXES, ...BODY_AXES];

const STEPS = [
  { id: "who", label: "Who she is" },
  { id: "face", label: "Her face" },
  { id: "body", label: "Her body" },
  { id: "home", label: "Her home" },
  { id: "review", label: "Review" },
];

export default function CreateCharacter() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [opts, setOpts] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [look, setLook] = useState(null);
  const [age, setAge] = useState(null);
  const [height, setHeight] = useState(168);
  const [weight, setWeight] = useState(58);
  const [faces, setFaces] = useState(4);
  // "inspiration" = hair/mood only, she is a different person (N generations).
  // "identity"    = the upload IS her face (0 generations).
  const [refMode, setRefMode] = useState("inspiration");
  const [bodyFrom, setBodyFrom] = useState("");
  const [homeStyle, setHomeStyle] = useState("");
  const [homeSurroundings, setHomeSurroundings] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [picks, setPicks] = useState({});
  // Only the axes the user actually MOVED. Absent means "take the preset's
  // value", which is what lets a preset stay authoritative underneath an edit
  // instead of being flattened to a default nobody chose.
  const [bodyAxes, setBodyAxes] = useState({});

  const objectUrl = useRef(null);
  useEffect(() => () => { if (objectUrl.current) URL.revokeObjectURL(objectUrl.current); }, []);

  // Vocabularies come from the backend so there is one copy of them; an option
  // the server cannot map must not be offered here.
  useEffect(() => {
    api.get("/api/characters/options")
      .then(setOpts)
      .catch((e) => setErr(`Could not load the option lists: ${e}`));
  }, []);

  const set = (k) => (v) => setPicks((p) => ({ ...p, [k]: v }));
  const nSet = (keys) => keys.filter((k) => picks[k]).length;
  const pickerOpts = (k) =>
    (k === "face_shape" ? (opts?.face_shapes || FACE_SHAPES)
      : k === "build" ? (opts?.builds || BODY_TYPES)
      : k === "skin_tone" ? opts?.skin_tones
      : k === "skin_undertone" ? opts?.skin_undertones
      : opts?.pickers?.[k]) || [];

  const pickFile = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = URL.createObjectURL(f);
    setFile(f);
    setPreview(objectUrl.current);
  };
  const clearFile = () => {
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = null;
    setFile(null);
    setPreview(null);
  };

  const ownFace = !!file && refMode === "identity";
  const genCount = (ownFace ? 0 : faces) + (homeStyle.trim() ? HOME_CORNER_COUNT : 0);
  const canSubmit = !!name.trim() && !busy;

  // The wire format is the OLD one, field for field. The backend reads a blank
  // string as "Claude decides" rather than as a value, so every key is always
  // sent and never omitted.
  const submit = async () => {
    if (!canSubmit) return;
    setErr(null);
    setBusy("Starting…");
    try {
      const fd = new FormData();
      fd.append("name", name.trim());
      fd.append("description", description || "");
      fd.append("face_shape", picks.face_shape || "");
      fd.append("build", picks.build || "");
      fd.append("height_cm", height || "");
      fd.append("weight_kg", weight || "");
      fd.append("faces", String(faces ?? 4));
      fd.append("look", look || "");
      fd.append("age", age || "");
      for (const k of PICK_KEYS) {
        if (k === "face_shape" || k === "build") continue;   // sent above
        fd.append(k, picks[k] || "");
      }
      fd.append("body_axes", JSON.stringify(bodyAxes || {}));
      fd.append("body_from", bodyFrom || "");
      fd.append("home_style", homeStyle || "");
      fd.append("home_surroundings", homeSurroundings || "");
      fd.append("reference_mode", file ? (refMode || "inspiration") : "none");
      if (file) fd.append("reference", file);

      const r = await fetch("/api/characters/guided", { method: "POST", body: fd });
      if (!r.ok) throw new Error((await r.text()).slice(0, 300));
      await r.json();
      // She builds in the background: the row exists already, so the roster shows
      // her filling herself in while you carry on.
      toast.ok(`Building ${name.trim()}`, "She'll appear on the roster as she builds.");
      navigate("/");
    } catch (e) {
      setErr(String(e));
      setBusy(null);
    }
  };

  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));
  const id = STEPS[step].id;

  return (
    <div className="min-h-screen px-5 md:px-8 py-7 max-w-[820px] mx-auto pb-28">
      <div className="mb-6">
        <button onClick={() => navigate("/")}
          className="inline-flex items-center gap-1.5 text-[12px] text-zinc-500 hover:text-zinc-300 mb-3">
          <ArrowLeft className="h-3.5 w-3.5" /> Characters
        </button>
        <h1 className="text-[19px] font-semibold tracking-tight">New character</h1>
        <p className="text-[12px] text-zinc-500 mt-0.5">
          Claude writes her bio, then generates faces for you to choose from.
          Anything you leave blank, he decides.
        </p>
      </div>

      {/* Stepper. Steps behind you are clickable; ahead of you they are not,
          because only the first one can be wrong. */}
      <div className="flex items-center gap-1 mb-6 overflow-x-auto no-scrollbar">
        {STEPS.map((s, i) => (
          <button key={s.id} onClick={() => i <= step && setStep(i)} disabled={i > step}
            className={cn("shrink-0 flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[12px] transition-colors",
              i === step ? "bg-white/[0.07] text-zinc-100"
                : i < step ? "text-zinc-400 hover:text-zinc-100"
                : "text-zinc-600 cursor-default")}>
            <span className={cn("grid h-4 w-4 place-items-center rounded-full text-[11px] font-semibold",
              i < step ? "bg-emerald-500 text-black"
                : i === step ? "bg-white text-black" : "bg-white/10 text-zinc-500")}>
              {i + 1}
            </span>
            {s.label}
          </button>
        ))}
      </div>

      {err && (
        <div className="mb-4 rounded-xl bg-rose-500/10 ring-1 ring-rose-500/30 px-3 py-2 text-[12px] text-rose-300">
          {err}
        </div>
      )}

      <div className="space-y-5">
        {/* ------------------------------------------------------- 1 who */}
        {id === "who" && (
          <>
            <Field label="Name" required>
              <input value={name} onChange={(e) => setName(e.target.value)} autoFocus
                onKeyDown={(e) => { if (e.key === "Enter" && name.trim()) next(); }}
                className={inputClass} placeholder="e.g. Aelira Vance" />
            </Field>
            <Field label="Description"
              hint="Left blank, Claude invents a coherent person.">
              <textarea value={description} onChange={(e) => setDescription(e.target.value)}
                rows={3} className={cn(inputClass, "resize-none")} placeholder="Who is she?" />
            </Field>
            {/* The register every other field is chosen under. It writes no part:
                an "attractiveness" field would put an adjective into every shot
                prompt, which is what makes an image model fall back on its
                generic beauty template. */}
            <Field label="Look"
              hint="How flattering her proportions should be. Steers the whole bio.">
              {/* The default was previously shown as a selected chip you could
                  not distinguish from your own choice — the Auto chip now says
                  which it is, and names the default it will use. */}
              <ChipRow label="Look" options={opts?.looks || []}
                value={look} onChange={setLook}
                autoLabel={opts?.default_look ? `Auto — ${opts.default_look}` : "Auto"} />
            </Field>
            <RangeField label="Age" nullable value={age} onChange={setAge}
              min={18} max={60} placeholder={26} unit="" />
          </>
        )}

        {/* ------------------------------------------------------ 2 face */}
        {id === "face" && (
          <>
            <Field label="Your own image" hint="Optional.">
              {preview ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <img src={preview} alt="reference"
                      className="h-20 w-16 rounded-md object-cover ring-1 ring-white/15" />
                    <button onClick={clearFile}
                      className="text-[12px] text-zinc-400 hover:text-rose-300 flex items-center gap-1">
                      <X className="h-3.5 w-3.5" /> remove
                    </button>
                  </div>
                  {/* The two modes are not variations of one another — one spends
                      generations inventing a different person, the other spends
                      nothing and makes this picture her. */}
                  <div className="grid grid-cols-2 gap-1.5">
                    {[
                      { id: "identity", title: "This is her face", cost: "free",
                        blurb: "Used exactly as uploaded. No faces generated." },
                      { id: "inspiration", title: "Inspiration only",
                        cost: `${faces} generation${faces > 1 ? "s" : ""}`,
                        blurb: "Hair, mood and lighting only. She will be a different person." },
                    ].map((m) => (
                      <button key={m.id} onClick={() => setRefMode(m.id)}
                        className={cn("rounded-lg px-2.5 py-2 text-left ring-1 transition-colors",
                          refMode === m.id ? "bg-white/[0.07] ring-white/40"
                                           : "ring-line hover:ring-white/25")}>
                        <span className="flex items-baseline justify-between gap-1">
                          <span className="text-[11px] font-medium text-zinc-200">{m.title}</span>
                          <span className={cn("text-[11px]", m.cost === "free" ? "text-emerald-300" : "text-zinc-500")}>{m.cost}</span>
                        </span>
                        <span className="block text-[11px] text-zinc-500 leading-snug mt-0.5">{m.blurb}</span>
                      </button>
                    ))}
                  </div>
                  {refMode === "identity" ? (
                    <div className="rounded-lg ring-1 ring-amber-400/25 bg-amber-400/5 px-3 py-2 space-y-1.5">
                      <p className="text-[10px] text-amber-200/90 leading-relaxed">
                        <strong className="font-medium">She must be fictional.</strong> This image is used as
                        her face exactly as uploaded — nothing rewrites it. Do not upload a photograph of a
                        real person.
                      </p>
                      <p className="text-[10px] text-zinc-400 leading-relaxed">
                        <strong className="font-medium text-zinc-300">Calibrate her next.</strong> One upload
                        is a single angle; calibration generates her at twelve head angles and builds the
                        gallery every later shot is scored against — that is where consistency comes from.
                      </p>
                    </div>
                  ) : (
                    <p className="text-[10px] text-zinc-600 leading-relaxed">
                      Her face comes from the pickers below, not from this image — the upload only steers
                      hair, mood and lighting.
                    </p>
                  )}
                </div>
              ) : (
                <label className="rounded-lg border border-dashed border-white/15 px-4 py-6 flex flex-col items-center gap-2 text-center hover:border-white/30 cursor-pointer">
                  <Upload className="h-5 w-5 text-zinc-500" />
                  <p className="text-[11px] text-zinc-500">Upload a face image</p>
                  <p className="text-[10px] text-zinc-600">
                    Use it as her face and generate nothing, or as style inspiration only.
                    You choose after uploading.
                  </p>
                  <input type="file" accept="image/*" hidden onChange={pickFile} />
                </label>
              )}
            </Field>

            {/* Hidden entirely when the upload IS her: there is nothing to
                generate, and a dial offering to spend on it would be a lie. */}
            {!ownFace && (
              <Field label="Faces to generate"
                hint="You pick one as her master face; the rest are discarded.">
                <div className="flex gap-1.5">
                  {Array.from({ length: opts?.max_faces || 4 }, (_, i) => i + 1).map((n) => (
                    <button key={n} onClick={() => setFaces(n)}
                      className={cn("flex-1 rounded-lg py-1.5 text-[12px] ring-1 transition-colors",
                        faces === n ? "bg-white text-black ring-white"
                                    : "ring-line text-zinc-400 hover:text-white")}>{n}</button>
                  ))}
                </div>
              </Field>
            )}

            {/* The skull first — it is what makes a face recognisable, and what a
                drifted generation loses before it loses eye colour. */}
            <div className="pt-1 space-y-4">
              <div className="text-[11px] text-zinc-500">
                {nSet(FACE_AXES)} of {FACE_AXES.length} set — Claude decides the rest.
              </div>
              {FACE_AXES.map((k) => (
                <Field key={k} label={LABELS[k]}>
                  <ChipRow options={pickerOpts(k)} value={picks[k] ?? null} onChange={set(k)} />
                </Field>
              ))}
            </div>
          </>
        )}

        {/* ------------------------------------------------------ 3 body */}
        {id === "body" && (
          <>
            <Field label="Body type">
              <BodyBuilder
                builds={opts?.builds || []}
                axesSpec={opts?.body_axes}
                presets={opts?.build_axis_defaults}
                build={picks.build ?? null}
                onBuild={(b) => set("build")(picks.build === b ? null : b)}
                axes={bodyAxes}
                onAxes={setBodyAxes}
              />
            </Field>

            {/* Copy a figure that already exists instead of building one later. A
                body reference is a full-length photograph and it contains a FACE,
                so the server crops the head off — what transfers is the
                proportions, never the identity. Free. */}
            {(opts?.bodies_available || []).length > 0 && (
              <Field label="Copy her figure from"
                hint={bodyFrom
                  ? "Copied with the head cropped off — proportions only, no face. Free."
                  : "Leave as nobody and build one later from Bio → Advanced body, or skip it."}>
                <div className="flex flex-wrap gap-1.5">
                  <Chip selected={!bodyFrom} onClick={() => setBodyFrom("")}>nobody</Chip>
                  {(opts.bodies_available || []).map((b) => (
                    <Chip key={b.id} selected={bodyFrom === b.id}
                      onClick={() => setBodyFrom(bodyFrom === b.id ? "" : b.id)}>{b.name}</Chip>
                  ))}
                </div>
              </Field>
            )}

            <RangeField label="Height" value={height} onChange={setHeight}
              min={148} max={190} unit=" cm"
              format={(v) => `${v} cm · ${Math.floor(v / 30.48)}′${Math.round((v / 2.54) % 12)}″`} />

            {/* body.height is a COMPOUND part — "168cm (5'6\"), 58kg" — and
                creation used to write only the height half, so every character
                born here had her weight silently deleted. It needs a control
                for the same reason it needs writing: it is half of a sentence
                that reaches the model. */}
            <RangeField label="Weight" value={weight} onChange={setWeight}
              min={40} max={120} unit=" kg"
              format={(v) => `${v} kg · ${Math.round(v * 2.205)} lb`} />

            <div className="pt-1 space-y-4">
              <div className="text-[11px] text-zinc-500">
                Skin &amp; hair — {nSet(SKIN_AXES)} of {SKIN_AXES.length} set.
              </div>
              {SKIN_AXES.map((k) => (
                <Field key={k} label={LABELS[k]}>
                  <ChipRow options={pickerOpts(k)} value={picks[k] ?? null} onChange={set(k)} />
                </Field>
              ))}
            </div>
          </>
        )}

        {/* ------------------------------------------------------ 4 home */}
        {id === "home" && (
          <>
            <div className="flex items-center gap-1.5 text-[12px] font-medium text-zinc-300">
              <Home className="h-3.5 w-3.5" /> Her home
            </div>
            <p className="text-[11px] text-zinc-500 leading-relaxed -mt-2">
              The third defining piece, alongside her bio and her body. Filled in, all{" "}
              {HOME_CORNER_COUNT} corners generate now from one style — her flat becomes a real
              place, so "her kitchen" means one specific kitchen from the first shot. Left blank
              it is skipped entirely and you build it later from the Home tab.
            </p>
            <Field label="Style and materials">
              <textarea value={homeStyle} onChange={(e) => setHomeStyle(e.target.value)} rows={2}
                className={cn(inputClass, "resize-none")}
                placeholder="e.g. a modern Bangalore flat, 12th floor, tile and marble floors, warm materials" />
            </Field>
            <Field label="What's visible outside">
              <input value={homeSurroundings} onChange={(e) => setHomeSurroundings(e.target.value)}
                className={inputClass} placeholder="balcony / terrace / living room only" />
            </Field>
            {homeStyle.trim() && (
              <p className="text-[11px] text-amber-300/80">
                +{HOME_CORNER_COUNT} generations on submit — this takes a few minutes.
              </p>
            )}
          </>
        )}

        {/* ---------------------------------------------------- 5 review */}
        {id === "review" && (
          <div className="space-y-3">
            <Row label="Name" value={name.trim() || <Missing>required</Missing>} />
            <Row label="Description" value={description || <Claude />} />
            <Row label="Look" value={look || opts?.default_look || <Claude />} />
            <Row label="Age" value={age || <Claude />} />
            <Row label="Face"
              value={ownFace ? "your upload, used as-is"
                : `${faces} generated${nSet(FACE_AXES) ? ` · ${nSet(FACE_AXES)} of ${FACE_AXES.length} axes set` : ""}`} />
            <Row label="Body"
              value={[picks.build, `${height} cm`, bodyFrom && `figure from ${bodyFrom}`]
                .filter(Boolean).join(" · ")} />
            <Row label="Skin & hair"
              value={nSet(SKIN_AXES) ? `${nSet(SKIN_AXES)} of ${SKIN_AXES.length} set` : <Claude />} />
            <Row label="Home"
              value={homeStyle.trim() ? `${HOME_CORNER_COUNT} corners will generate` : "skipped"} />
          </div>
        )}
      </div>

      {/* The cost follows you, on every step, because it is the thing that
          changes as you fill the form in. */}
      <div className="fixed bottom-0 inset-x-0 md:left-60 border-t border-white/10 bg-[#0d0d0f]/95 backdrop-blur px-5 md:px-8 py-3">
        <div className="max-w-[820px] mx-auto flex items-center gap-3">
          <p className="hidden sm:flex flex-1 items-start gap-2 text-[11px] text-zinc-500 leading-relaxed">
            <Sparkles className="h-3.5 w-3.5 text-amber-300 shrink-0 mt-0.5" />
            <span>
              bio → {ownFace ? "her face (uploaded)" : `${faces} face${faces > 1 ? "s" : ""}`}
              {homeStyle.trim() ? ` → ${HOME_CORNER_COUNT} home corners` : ""}.{" "}
              <span className={genCount === 0 ? "text-emerald-300" : ""}>
                {genCount === 0 ? "No generations — free." : `${genCount} generation${genCount > 1 ? "s" : ""}.`}
              </span>
            </span>
          </p>
          <div className="flex-1 sm:flex-none" />
          {step > 0 && (
            <Button variant="outline" onClick={back} disabled={!!busy}>
              <ArrowLeft className="h-3.5 w-3.5" /> Back
            </Button>
          )}
          {step < STEPS.length - 1 ? (
            <Button variant="primary" onClick={next} disabled={step === 0 && !name.trim()}>
              Next <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          ) : (
            <Button variant="primary" onClick={submit} disabled={!canSubmit}>
              {busy ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> {busy}</> : "Create character"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

const LABELS = {
  face_shape: "Face shape", cheekbones: "Cheekbones", jawline: "Jawline", chin: "Chin",
  eyes: "Eyes", brows: "Brows", nose: "Nose", lips: "Lips",
  skin_tone: "Skin tone", skin_undertone: "Undertone", hair_colour: "Hair colour",
  hair_length: "Hair length", hair_texture: "Hair texture", build: "Body type",
};

const Claude = () => <span className="text-zinc-600">Claude decides</span>;
const Missing = ({ children }) => <span className="text-rose-400">{children}</span>;

function Row({ label, value }) {
  return (
    <div className="flex items-baseline gap-4 rounded-lg bg-surface px-3 py-2">
      <span className="w-28 shrink-0 text-[11px] text-zinc-500">{label}</span>
      <span className="text-[12px] text-zinc-200">{value || <Claude />}</span>
    </div>
  );
}
