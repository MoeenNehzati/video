# External JJazzLab and rendering setup

The repository retains only the adapter code used by
[song-arrangement-research](../../.agents/skills/song-arrangement-research/SKILL.md).
Install Java/JJazzLab Toolkit, rhythm resources, FluidSynth, sample banks and FFmpeg
outside the checkout. The original collaborator bundle retains its toolkit build
files, resource licenses and historical experiments; they are not runtime payloads
in this repo.

Configure the exact installations through local TOML following
[configuration](../../docs/configuration.md). Use Java/Javac 25+ compatible with
the selected toolkit; the executor compiles `ChildExperiment.java` from retained
source into a temporary directory. It does not rely on old compiled classes.
The native FluidSynth library is selected explicitly for each platform and loaded
only when rendering begins.

`resources.soundfont_manifest` points to a JSON object mapping each bank key to
`{"path": "bank.sf2", "credits": "source and license attribution"}`. Paths may be
absolute or relative to that external manifest. Required route keys are
`generaluser`, `nylon`, `steel`, `bass`, `clarinet`, `drums`, `salamander`, plus any
`counter_library` selected by the arrangement. Preserve full source/license
records alongside the banks; `resources.soundfont_credits` names the publication
credits file. Do not substitute different samples without explicit selection and
listening review.

The supplied bundle references an absent `audit_existing_midi.py`. Configure
`resources.midi_audit` only after recovering a proven helper that supplies the
expected `read_midi` and `triples` contract. Execution/rendering stop before outputs
when it is unavailable. Synthetic test helpers do not replace that production
verifier. Initial baseline creation is also outside the retained automatic route.

Follow the skill's explicit input/output commands. Actual toolkit compatibility,
sample coverage, melody/accompaniment preservation, aligned backing, shared gain
and listening quality require validation with the selected external resources.
