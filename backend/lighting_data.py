"""Light, hour, weather and season — the four things that decide how a photo looks
before anyone in it does anything.

These are SCENE axes, not identity axes. Nothing here describes a person; every
entry describes the air, the sun or the room. Same rule as the rest of this
package: her face, skin, hair and build come from her references, and putting a
word about her in a scene prompt costs the measured 0.86 -> 0.53.

They are also the axes most likely to be left empty, and that is fine. An empty
value emits nothing at all rather than a default, because "soft neutral lighting"
appended to every prompt is how a year of photographs ends up looking like one
afternoon. The place, the hour and the weather already imply light most of the
time; these exist for when you want to say it.

WARNING, learned the hard way on the master face: light instructions COMPETE.
"Soft diffused window light" and "flat and even, no colour cast" in the same
prompt produced a passport photo, because the model split the difference and the
flatter one won. Pick one voice. The composer offers these as single-select for
that reason, and LIGHTING and TIME_OF_DAY are written so they compose rather than
contradict — one says the quality, the other says the hour.
"""

# --------------------------------------------------------------------------
# LIGHTING — the QUALITY of the light, independent of the hour.
# --------------------------------------------------------------------------
LIGHTING: dict[str, dict[str, dict]] = {

    "Daylight": {
        "soft-window": {
            "label": "Soft window light",
            "text": "Lit by soft diffused daylight from a window to one side, "
                    "gentle falloff across the face and a soft shadow on the "
                    "opposite side."},
        "open-shade": {
            "label": "Open shade",
            "text": "In open shade out of direct sun — even, cool, shadowless "
                    "light with the brightness of the open sky above."},
        "overcast-flat": {
            "label": "Overcast, flat",
            "text": "Flat overcast light, the whole sky acting as one soft "
                    "source, no visible shadow direction."},
        "hard-sun": {
            "label": "Hard midday sun",
            "text": "Direct hard sunlight overhead, crisp edged shadows, bright "
                    "highlights and deep contrast."},
        "dappled": {
            "label": "Dappled through leaves",
            "text": "Sunlight broken by leaves overhead, scattered bright patches "
                    "moving across everything below."},
        "backlit-rim": {
            "label": "Backlit / rim light",
            "text": "Lit from behind so the edges catch a bright rim and the "
                    "front is in soft fill, with light haze in the air."},
        "golden-hour": {
            "label": "Golden hour",
            "text": "Low warm sun near the horizon, long shadows, a golden cast "
                    "across every surface it touches."},
    },

    "Indoor": {
        "warm-lamp": {
            "label": "Warm lamps",
            "text": "Lit by warm domestic lamps, pools of light with the rest of "
                    "the room falling away into shadow."},
        "overhead-fluoro": {
            "label": "Overhead strip light",
            "text": "Lit from overhead strip lighting, slightly green-cool and "
                    "unflattering, shadows dropping straight down."},
        "screen-glow": {
            "label": "Screen glow",
            "text": "Lit mainly from below by a phone or laptop screen, cool and "
                    "close, everything beyond it dark."},
        "candle-warm": {
            "label": "Candles / very low",
            "text": "Lit by a few small warm flames, very low light, deep shadow "
                    "everywhere the flames do not reach."},
        "mixed-domestic": {
            "label": "Mixed domestic",
            "text": "A mixture of daylight through a window and warm room lamps, "
                    "the two colour temperatures visibly disagreeing."},
        "bright-retail": {
            "label": "Bright retail",
            "text": "The bright, even, slightly clinical light of a shop or mall "
                    "interior, lit from every direction at once."},
    },

    "Night": {
        "streetlight-sodium": {
            "label": "Streetlight",
            "text": "Lit by street lamps overhead, warm orange pools with dark "
                    "gaps between them."},
        "neon-signage": {
            "label": "Neon / signage",
            "text": "Lit by coloured shopfront signage, saturated pinks and blues "
                    "landing unevenly across everything."},
        "car-headlights": {
            "label": "Headlights",
            "text": "Caught in passing headlights, hard white light from one side "
                    "sweeping across and gone."},
        "on-camera-flash": {
            "label": "On-camera flash",
            "text": "Lit by a harsh direct on-camera flash: bright flat faces, a "
                    "hard shadow thrown onto the wall behind, black background."},
        "string-lights": {
            "label": "String lights",
            "text": "Lit by small warm string lights strung overhead, dim and "
                    "scattered with visible points of light behind."},
        "phone-torch": {
            "label": "Phone torch",
            "text": "Lit by a single phone torch held close, hard and directional "
                    "with everything past a metre falling to black."},
    },
}


# --------------------------------------------------------------------------
# TIME OF DAY — the HOUR. Composes with LIGHTING rather than repeating it.
# --------------------------------------------------------------------------
TIME_OF_DAY: dict[str, dict] = {
    "dawn": {"label": "Dawn",
             "text": "Just before and after sunrise: thin cool light, the sky "
                     "still pale, almost nobody about."},
    "early-morning": {"label": "Early morning",
                      "text": "Early morning, light still low and slanting, the "
                              "day not properly started."},
    "mid-morning": {"label": "Mid-morning",
                    "text": "Mid-morning, bright and ordinary, full daylight "
                            "without the harshness of noon."},
    "midday": {"label": "Midday",
               "text": "The middle of the day, sun high, light at its hardest "
                       "and most direct."},
    "afternoon": {"label": "Afternoon",
                  "text": "Afternoon, the light warm and settled, shadows "
                          "beginning to lengthen."},
    "golden": {"label": "Golden hour",
               "text": "The hour before sunset, the sun low and gold, long soft "
                       "shadows running across everything."},
    "dusk": {"label": "Dusk / blue hour",
             "text": "After sunset before true dark: a deep blue sky with lights "
                     "beginning to come on and compete with it."},
    "evening": {"label": "Evening",
                "text": "Evening, properly dark outside, everything lit by "
                        "whatever is on."},
    "late-night": {"label": "Late night",
                   "text": "Late at night, streets and rooms mostly empty, only "
                           "a few lights on."},
}


# --------------------------------------------------------------------------
# WEATHER — what the air is doing. Visible, never a mood word.
# --------------------------------------------------------------------------
WEATHER: dict[str, dict] = {
    "clear": {"label": "Clear",
              "text": "Clear weather, an open sky, sharp light and clean air."},
    "hazy": {"label": "Hazy",
             "text": "Hazy air softening the distance, the sun a bright patch "
                     "rather than a disc."},
    "overcast": {"label": "Overcast",
                 "text": "Fully overcast, a white sky, no shadow direction "
                         "anywhere."},
    "light-rain": {"label": "Light rain",
                   "text": "Light rain falling, dark wet ground reflecting the "
                           "light, damp shoulders and hair."},
    "heavy-rain": {"label": "Heavy rain / monsoon",
                   "text": "Heavy monsoon rain coming down hard, water running "
                           "everywhere, spray off every surface."},
    "just-rained": {"label": "Just rained",
                    "text": "Just after rain: everything wet and reflective, the "
                            "sky clearing, puddles holding the light."},
    "fog": {"label": "Fog / smog",
            "text": "Thick fog or winter smog cutting visibility down, "
                    "everything past a short distance dissolving into grey."},
    "windy": {"label": "Windy",
              "text": "Noticeably windy: loose fabric and hair pushed sideways, "
                      "things in the background moving."},
    "dusty": {"label": "Dusty / heat haze",
              "text": "Dry and dusty, heat shimmer over the ground, a fine haze "
                      "of dust catching the light."},
}


# --------------------------------------------------------------------------
# SEASON — for a character whose year is the point.
# --------------------------------------------------------------------------
# Written for a North Indian year, because that is where these characters live.
# The text says what is VISIBLE in the frame — what people are wearing, what the
# light is doing, what is growing — never a calendar month, which a camera cannot
# photograph.
SEASON: dict[str, dict] = {
    "winter": {"label": "Winter",
               "text": "Deep winter: everyone in layers, shawls and jackets, low "
                       "weak sun and grey air."},
    "late-winter": {"label": "Late winter",
                    "text": "Late winter warming up: light jackets still on in "
                            "the morning, off by the afternoon."},
    "spring": {"label": "Spring",
               "text": "Spring: clear bright light, flowering trees, everything "
                       "in single light layers."},
    "summer": {"label": "Summer",
               "text": "High summer: brutal light, everything bleached and hot, "
                       "the thinnest possible clothes, shade sought out."},
    "pre-monsoon": {"label": "Pre-monsoon",
                    "text": "Pre-monsoon: heavy still air, a bruised sky "
                            "building, everything waiting for it to break."},
    "monsoon": {"label": "Monsoon",
                "text": "Monsoon: wet everything, umbrellas, water standing in "
                        "the roads, green pushing out of every gap."},
    "post-monsoon": {"label": "Post-monsoon",
                     "text": "Post-monsoon: washed clean air, unusually clear "
                             "light, deep green still everywhere."},
    "autumn": {"label": "Autumn / festive",
               "text": "Autumn into the festive season: cooling evenings, lights "
                       "and decoration going up, crowds out late."},
}
