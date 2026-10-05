# Notation and evidence

Preserve source clef, key signature, meter and its common/cut-time symbol, all notes/rests and written durations, beams, dots, tuplets, accidentals, ties versus slurs, repeat barlines/endings, dynamics and performance instructions, chord spelling and exact onset, lyric syllabification/melismas, system/page breaks where meaningful, title/credits and all continuation lyrics. Record any intentional layout change, especially text-only continuation pages consolidated under the music. Do not invent implied accompaniment or harmonies after “osv.”; retain the instruction.

## Reading staff geometry

The bundled helper uses a 1600-pixel-wide preview. A six-number system seed is [left_x,right_x,top_line_y_left,top_line_y_right,spacing_left,spacing_right]. Stronger curvature accepts {"anchors":[[x,top_y],...],"spacing":number}. Each staff line is fitted independently using local ridge samples and a robust cubic fit. Inspect overlays even if fit gates pass. Preserve original-resolution coordinates through the documented scale. Evaluate all five lines at each notehead x and interpolate half-spaces locally; extrapolate ledger lines with the adjacent local spacing. For treble clef the bottom line is E4. Other clefs need their actual bottom-line pitch: never silently apply treble defaults.

Record manually observed centers or independently image-detected centers, their coordinate frame, computed staff position, residual and resulting natural pitch. Never compute y from a candidate pitch then report its agreement as image verification. Dots, stems, ledger lines, slurs and text can mislead simple dark-pixel searches. Geometry alone does not identify accidentals, note duration or lyric alignment.

## Review and ambiguity

Create an event ledger with measure, onset as a rational quarter-note value, pitch spelling/octave, duration, written type/dots, accidentals, beams/ties/slurs, lyric text/syllabic/extenders, and harmony onset/quality/bass. Compare source bars and system counts. Balance measures using exact fractions. Document pickups and irregular source measures individually; do not pad with invented rests or force an assumed complementary ending.

Check musical plausibility as a flag: non-chord tones, minor raised sevenths and unusual cadences are often correct. External editions can corroborate an interpretation but cannot override the supplied source. Research ambiguous chord symbols and preserve their printed form separately from semantic interpretation; unresolved semantics must stay visible in the review and playback notes.

Independent review needs the original and readable crops plus the proposed XML/render. Review all events, text and boundaries. Record corrections and the final score hash. Only then freeze a canonical snapshot. Owner review, separate source review, structural checks, rendered review and audio integrity are distinct statuses. Changing score content invalidates affected review conclusions until rechecked.

## Rendering and audio

Inspect all output pages. Confirm every prose stanza is present and legible, not merely in XML. Check chord suffixes, accidental glyphs, canon entries, endings, layout and lyric collisions. Roundtrip through the renderer and compare musical objects with musicdiff or equivalent. If directions split into multiple objects, independently compare their ordered text by measure before excluding that representation difference. Do not indiscriminately ignore missing directions, articulations or repeats.

For playback, distinguish printed tempo from an editorial preview tempo. Melody-only audio supports pitch/rhythm review; block-chord accompaniment is an explicitly editorial audition. Preserve repeat playback semantics. Compare raw MIDI note-on/off events against intended XML playback, accounting for tie merging and repeat expansion. Parsing MIDI back into notation can split sustained notes at inferred barlines and create false mismatches. Check for silence, clipping and missing events; these checks do not mean anyone listened to the audio.
