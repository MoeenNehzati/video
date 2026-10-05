# Research and brief contract

research.json: song_id, retrieved_date, lyric_source (local path), lyric_summary, background, evidence array. Each evidence entry has id, kind (local_score, archive, recording_metadata, empirical_study, or creative_hypothesis), source, finding, limitations. Do not reproduce full external lyrics.

arrangement_brief.json required fields:
- song_id: approved folder stem
- source_xml and source_sha256
- baseline_folder and baseline_midi_sha256
- output_root: explicit directory under configured paths.data_root
- audience: {age_min, age_max, context}
- vocals: user_supplied
- invariants: nonempty list of musical/source constraints
- variants: list of {id, label, axis, rationale, evidence_ids, baseline_percussion, events, participation_windows}

baseline_percussion is preserve or replace. events are [GM drum pitch, beat from zero, duration in quarter notes, velocity]. This first adapter supports percussion-only experiments while retaining every pitched baseline event; a future pitched/meter/structure operation needs an explicitly implemented and verified adapter extension, not an invented plan operation. participation_windows are [start beat, end beat] for optional user clapping; no pre-recorded claps are added inside those windows by default.

Beat units are quarter notes even for compound meters. Keep source timing, including pickup/rests. Plans must name the baseline; do not silently choose a different version. Preserve foreground melody in previews; backing-only exports remove precisely the Original melody track without changing duration/tempo or other tracks.

The compiler validates hashes, evidence references, IDs and musical event bounds. The adapter validates note-level invariants, builds native projects, and executes supported events. A successful compiler run alone does not mean any audio was generated.

Paths in the brief and baseline parameters may be absolute within `paths.data_root`
or relative to that root. Baseline `parameters.json` must name its own `filename`,
`stem`, source XML/MIDI paths and hashes, meter/bars/tempo/chords, style/variation,
ensemble/room, counter_library, and existing percussion_events. The baseline also
needs native reload verification, `tracks.tsv`, `input.properties`, and its melody,
chord and supporting-part TSVs. Trio/chamber ensembles also need bass.tsv;
chamber needs strings.tsv. These are approved data inputs, not bundled templates.

Execution revalidates the compiled plan, research hash and baseline before writing.
Outputs preserve existing pitched notes/controllers and add or replace only the
specified percussion note events. Participation text follows the supplied windows;
no song-specific cue pattern is inferred. Every variant must contain exactly one
`Original melody` track so backing removal is unambiguous.
