"""The realism doctrine must actually reach the model.

Every case here is a bug that shipped 607 times before it was noticed, which is
what makes this file worth more than the comments it defends. `prompt.py` argued
for its camera and skin rules at length, marked them `critical=True` so the UI
warns before you switch them off, and never once put them in a prompt —
`compose_tagged` pulled only the `body` and `grooming` sections out of the part
tree. Measured across the whole run history on 2026-08-24:

    "sensor noise"                 0 runs      (camera.body)
    "no bokeh"                     0 runs      (constraints.main)
    "never a professional camera"  0 runs      (camera.body)
    "not a model on a shoot"       0 runs      (subject.energy)
    flaws set                      0 runs
    camera_holder set              7 runs

    "85mm"                        51 runs      <- what filled the vacuum
    "shallow depth"               40 runs

A comment records a lesson. These enforce one.

Nothing here calls a provider, loads ONNX or touches the gate — pure functions
over the composer and the inference, so they run in a second.
"""
from __future__ import annotations

from backend import prompt as promptlib
from backend.main import _infer_capture, _is_selfie_pose


def _parts():
    """The default part tree, so this does not depend on a character's edits."""
    return promptlib.default_parts()


# ── the doctrine reaches the prompt ──────────────────────────────────────────

def test_capture_clause_carries_the_camera_and_the_constraints():
    text = promptlib.capture_clause(_parts())
    for phrase in ("sensor noise", "no bokeh", "never a professional camera",
                   "not a model on a shoot", "peach fuzz"):
        assert phrase.lower() in text.lower(), f"{phrase!r} missing from capture_clause"


def test_compose_tagged_ships_the_capture_clause():
    cap = promptlib.capture_clause(_parts())
    text, _ = promptlib.compose_tagged("in a cafe", capture_text=cap)
    assert "no bokeh" in text
    assert "never a professional camera" in text.lower()


def test_capture_clause_respects_disabled_parts():
    """The checkboxes stay real — a disabled part must not ship anyway."""
    parts = [p for p in _parts() if p.id != "camera.body"]
    assert "24mm" not in promptlib.capture_clause(parts)


def test_capture_clause_drops_identity_parts():
    """skin.tone describes her and is identity=True; a reference carries that.

    Same rule compose() applies, for the same measured reason: describing her
    scored 0.531 against 0.860 for a terse lock.
    """
    text = promptlib.capture_clause(_parts())
    tone = next(p for p in _parts() if p.id == "skin.tone")
    assert tone.identity, "precondition: skin.tone is an identity part"
    assert tone.text not in text


def test_flaws_land_after_the_realism_line():
    """A contradiction is resolved by whichever the model read last.

    "crisp focus on the eyes" and "mild motion blur" cannot both hold, and the
    flaw is the one that was asked for.
    """
    text, _ = promptlib.compose_tagged("in a bar", flaws="snapshot")
    assert text.index("motion blur") > text.index("Crisp focus on the eyes")


# ── the knobs are reached at all ─────────────────────────────────────────────

def test_wake_up_brief_infers_every_axis():
    """Run 15e2298957: the brief asked for a selfie and an imperfect one, and
    every selfie rule in the pipeline sat the shot out because no pose was
    picked."""
    brief = ("she just woke up yawning she still in her bed took her phone and "
             "captured imperfect selfie to post it to instagram.")
    holder, flaws, optics, groom, notes = _infer_capture(brief, None, "", "")
    assert holder == "selfie"
    assert flaws == "subtle"
    assert optics == "phone-front"
    assert groom == "just-woken"
    assert notes, "an inference must say that it happened"


def test_explicit_values_always_win():
    brief = "imperfect selfie"
    holder, flaws, optics, groom, _ = _infer_capture(
        brief, None, "friend", "snapshot", "portrait", "end-of-day")
    assert (holder, flaws, optics, groom) == (
        "friend", "snapshot", "portrait", "end-of-day")


def test_a_studio_brief_keeps_its_professional_optics():
    """The phone default must not overrule a brief that asked for a studio."""
    _, _, optics, _, _ = _infer_capture(
        "photo shoot in the studio, dark and light room effect", None, "", "")
    assert optics == "", "a studio brief must not be forced onto phone optics"


def test_editorial_register_also_stands_down():
    _, _, optics, _, _ = _infer_capture(
        "on a rooftop at dusk", None, "", "", shot_type="editorial")
    assert optics == ""


# ── every selfie category is a selfie ────────────────────────────────────────

def test_all_three_selfie_groups_are_selfies():
    """This tested "Selfie (Handheld)" alone, so the 50 car and 25 mirror poses
    got the 600-char outfit cap meant for a photograph someone else took."""
    for group in ("Selfie (Handheld)", "Selfie (Mirror)", "Selfie (Car)"):
        pose_id = next(iter(promptlib.POSE_GROUPS[group]))
        assert _is_selfie_pose(pose_id), f"{group} not recognised as a selfie"


def test_a_brief_alone_can_make_it_a_selfie():
    assert _is_selfie_pose(None, "taking a selfie on the balcony")
    assert _is_selfie_pose(None, "selfi in a car")      # the typo people type
    assert not _is_selfie_pose(None, "walking through the market")


# ── the vocabulary is well-formed ────────────────────────────────────────────

def test_new_vocabularies_have_an_empty_default():
    """"" must exist and emit nothing, or an unset picker changes the prompt."""
    for table in (promptlib.OPTICS, promptlib.EXPOSURE, promptlib.GROOMING_STATE):
        assert "" in table
        assert table[""]["text"] == ""


def test_grooming_state_that_costs_similarity_says_so():
    """just-woken moves the landmarks ArcFace reads. A low score there is the
    intended outcome, and the row has to know that before it is read as drift."""
    assert promptlib.GROOMING_STATE["just-woken"]["expected_low"] is True


def test_no_appended_clause_says_bare():
    """"bare" beside a lingerie description and a bed reads to a content checker
    as undress, not as no-makeup — fal refused a whole generation over it."""
    for table in (promptlib.OPTICS, promptlib.EXPOSURE, promptlib.GROOMING_STATE):
        for k, v in table.items():
            assert "bare" not in v["text"].lower(), f"{k} uses a moderation trigger"


# ── the phone doctrine must not contradict a studio register ─────────────────

def test_editorial_keeps_real_skin_but_drops_the_phone():
    """One string held two claims. Real skin belongs in every prompt — a studio
    photograph of a person still has pores. "Shot on a phone" does not, and it
    shipped on editorial anyway because there was no seam to cut."""
    txt, _ = promptlib.compose_tagged("on a rooftop", shot_type="editorial", phone=False)
    assert "visible skin pores" in txt
    assert "Shot on a phone" not in txt


def test_candid_still_says_shot_on_a_phone():
    txt, _ = promptlib.compose_tagged("in a cafe", shot_type="candid", phone=True)
    assert "Shot on a phone" in txt


def test_one_predicate_gates_every_register_decision():
    """capture_clause, promptlib.SYSTEM and the phone tail were gated in three
    different places with three different opinions. They read one tuple now."""
    from backend.main import PHONE_REGISTERS
    assert set(PHONE_REGISTERS) == {"candid", "street", "pov"}
    for pro in ("editorial", "luxury", "commercial"):
        assert pro not in PHONE_REGISTERS


# ── nobody else in frame ─────────────────────────────────────────────────────

def test_crowd_is_suppressed_by_default_on_a_solo_brief():
    """26 of 613 runs were scored out of a crowd — one out of eighteen faces —
    because the shot path had no crowd clause while the scene path did."""
    from backend.main import _wants_people
    assert not _wants_people("she just woke up yawning in her bed", False)
    assert not _wants_people("photo shoot in the studio", False)


def test_a_brief_that_asks_for_people_gets_them():
    from backend.main import _wants_people
    for brief in ("selfi night resto bar people around her the crowd is huge",
                  "she is at a local tea shop with her friend",
                  "at a birthday party laughing"):
        assert _wants_people(brief, False), brief


def test_word_boundaries_are_real():
    """Written through a non-raw string once, which turned every \\b into a
    literal backspace and made the pattern match nothing. Substrings must not."""
    from backend.main import _wants_people
    assert not _wants_people("regrouping the steamy coupled team", False)


def test_explicit_allow_crowd_wins():
    from backend.main import _wants_people
    assert _wants_people("she just woke up", True)


def test_crowd_shows_in_diagnosis_even_when_kept():
    """confounds only fires on rejection, so a KEPT shot picked out of four
    faces carried an empty diagnosis. 7 runs did exactly that."""
    from backend import gate

    class _F:
        yaw = pitch = roll = 0.0
        width = 500
        pose_class = "frontal"
        tilted = False

    kept = gate.Verdict(0.70, "front", 0.58, _F(), source_yaw=0.0, faces_in_frame=4)
    assert kept.status == "kept"
    assert kept.crowd is True
    assert "crowd" in kept.diagnosis
    assert kept.dict()["crowd"] is True

    alone = gate.Verdict(0.70, "front", 0.58, _F(), source_yaw=0.0, faces_in_frame=1)
    assert alone.crowd is False
    assert alone.diagnosis == ""


# ── one implementation, both paths ───────────────────────────────────────────

def test_late_clauses_order_puts_grooming_after_the_rest():
    """grooming_state contradicts carry_clause's "nails clean and even" and
    hair.base's "soft waves". It only wins by arriving after them."""
    out = promptlib.late_clauses(optics="phone-front", exposure="blown-window",
                                 grooming_state="just-woken", wet=True,
                                 suppress_crowd=True)
    joined = " ".join(out)
    assert joined.index("woken up") > joined.index("Depth of field is DEEP")
    assert joined.index("woken up") > joined.index("blown to featureless white")


def test_late_clauses_drops_empties():
    assert promptlib.late_clauses() == []
    assert len(promptlib.late_clauses(optics="phone-deep")) == 1


def test_wet_clause_is_written_out_for_both_counts():
    """Spliced pronouns produced "Every person in frame — her hair"; a clause
    that reads as broken English is one the model half-applies."""
    solo, cast = promptlib.wet_clause(1), promptlib.wet_clause(2)
    assert solo.startswith("Her hair")
    assert cast.startswith("Everyone in this photograph")
    assert "— her hair" not in cast


def test_distinct_clause_is_one_wording():
    """Existed three separate times for one measured failure (check_cast's
    `blended`). Works from reference tags or from names."""
    assert promptlib.distinct_clause([]) == ""
    assert promptlib.distinct_clause(["@image1"]) == ""
    tags = promptlib.distinct_clause(["@image1", "@image2"])
    names = promptlib.distinct_clause(["Kiara", "Sonam"])
    assert "2 DIFFERENT women" in tags and "@image1 and @image2" in tags
    assert "Kiara and Sonam" in names
    assert promptlib.distinct_clause(["a", "b", "c"]).startswith("There are 3")


def test_no_crowd_counts_the_subjects():
    assert "Exactly one person is" in promptlib.no_crowd_clause(1)
    assert "Exactly 2 people are" in promptlib.no_crowd_clause(2)


def test_the_tail_lives_in_one_place():
    """The point of the exercise: the scene path was missing all of this because
    it was written on the shot path. If either path grows its own copy, the
    literals come back to main.py and this fails."""
    import pathlib
    src = pathlib.Path("backend/main.py").read_text()
    for gone in ("_WET_HAIR = (", "_NO_CROWD = ("):
        assert gone not in src, f"{gone} is back in main.py — use promptlib"


# ── the three opt-ins ────────────────────────────────────────────────────────

def test_shot_accepts_all_three_opt_ins():
    """Each was made per-request by a commit that argued the case, then given
    nothing to opt in with. safety_tolerance was never even added to ShotReq,
    despite 11b4f1a saying it "does apply to shots"."""
    from backend.main import ShotReq
    r = ShotReq(brief="x", safety_tolerance="6", ref_budget=True, use_timeline=True)
    assert r.safety_tolerance == "6"
    assert r.ref_budget is True
    assert r.use_timeline is True


def test_the_opt_ins_still_default_off():
    """Off is the right default for all three — the commits argued that and were
    right. The bug was never having a way to turn them on."""
    from backend.main import ShotReq
    r = ShotReq(brief="x")
    assert r.safety_tolerance is None
    assert r.ref_budget is False
    assert r.use_timeline is False


def test_scene_accepts_the_tail_axes():
    from backend.main import SceneReq
    r = SceneReq(prompt="@kiara at a cafe", optics="phone-deep",
                 exposure="low-light", grooming_state="end-of-day")
    assert (r.optics, r.exposure, r.grooming_state) == (
        "phone-deep", "low-light", "end-of-day")


# ── the prompt budget ────────────────────────────────────────────────────────

def test_prompt_cap_is_below_the_known_good_length():
    """4,867 and 4,895 generated on 2026-08-24; 5,367 was refused by kie with
    "The text length cannot exceed the maximum limit". The cap sits under the
    known-good figure because finding the true ceiling costs a billed
    generation per probe."""
    from backend.config import PROMPT_CAP
    assert PROMPT_CAP < 4867, "cap must sit below a length measured to work"
    assert PROMPT_CAP > 3000, "cap so low that ordinary prompts would be cut"
