# Artifact bookkeeping worked examples

Companion checks for the [plan](artifact-ledger-plan.md) and
[event contract](artifact-ledger-contract.md). These are synthetic design examples,
not existing song artifacts or executable fixtures. Implementation should translate
them into tests and retain the expected outcomes below.

Names such as `xml-a` and references such as `XML-A@r1` are readable aliases for
UUID identities. Real directories carry the plan's unique suffixes and must pass
its path-length checks. `@r1` identifies an exact revision, not a filename. Trees
omit some supporting artifacts to stay readable; native projects, exported MIDI,
research, prompts and persisted checks remain separate artifacts when required.

## 1. Several attempts at every step

```text
data_root/
├── songs/
│   └── song-a/
│       ├── source-a/
│       │   ├── source.pdf
│       │   ├── xml-a/
│       │   │   ├── score.musicxml
│       │   │   ├── midi-a/
│       │   │   │   ├── arrangement.mid
│       │   │   │   ├── render-a/
│       │   │   │   │   ├── full.wav
│       │   │   │   │   └── backing.wav
│       │   │   │   └── render-b/
│       │   │   │       ├── full.wav
│       │   │   │       └── backing.wav
│       │   │   └── midi-b/
│       │   │       └── arrangement.mid
│       │   └── xml-b/
│       │       └── score.musicxml
│       └── source-b/
│           └── source.pdf
├── shared/
│   └── character-a/
│       └── reference.png
├── ledger/
│   └── <event-id>.json
├── history/
│   └── <artifact-id>/<revision-id>/<owned-files>
├── work/
│   └── <run-id>/{inputs,outputs,scratch}/
└── catalogue/
    └── <host-id>/
```

Make `XML-A@r1` from `SOURCE-A@r1`, then try another transcription `XML-B@r1`.
Make `MIDI-A@r1` and `MIDI-B@r1` from `XML-A@r1`; render MIDI-A twice with different
settings. Full/backing files form one render bundle when created together.

**Check:** every fresh attempt has a different run/artifact/revision identity;
all alternatives remain browsable. Two attempts producing identical bytes still
have distinct provenance. Failed attempts retain run evidence without publishing
incomplete artifact bundles. Apply the same branching check at each subsequent
visual stage, not just at XML/MIDI/render stages.

## 2. Explicit revision versus another version

Starting from example 1:

| Action | Expected result |
| --- | --- |
| Explicitly correct XML-A, naming current base `XML-A@r1` | Create `XML-A@r2`; replace only XML-A's owned visible files. Both revisions remain in history. |
| Inspect existing MIDI-A/MIDI-B | They still depend on `XML-A@r1`. Their files and directories are untouched. |
| Arrange the corrected XML | A new MIDI artifact pins `XML-A@r2`; previous arrangements remain available. |
| Try an alternative based on old `XML-A@r1` | Create XML-C with `branched_from=XML-A@r1`; do not revise over XML-A@r2. Record actual consumed inputs separately. |
| Submit a revision prepared from r1 after r2 is already known | Refuse stale-base publication; never silently replace r2. |

**Check:** the visible parent directory cannot tell you which revision a descendant
used. Historical lookup resolves from preserved bytes and exact ledger references,
not the current `score.musicxml` file.

## 3. Multi-input video with alternative takes

A storyboard can use the source sheet as its primary storage input while also
consuming reviewed XML and a chosen audio render. This keeps the visual branch
shallow; every named primary input must be an actual declared dependency.

```text
source-a/
├── source.pdf
├── xml-a/…
├── story-a/
│   ├── storyboard.json
│   ├── image-a/
│   │   ├── keyframe.png
│   │   ├── take-a/
│   │   │   └── clip.mp4
│   │   └── take-b/
│   │       └── clip.mp4
│   ├── image-b/
│   │   └── keyframe.png
│   ├── film-a/
│   │   └── film.mp4
│   └── film-b/
│       └── film.mp4
└── story-b/
    └── storyboard.json
```

| Artifact | Primary storage input | Other exact inputs to record |
| --- | --- | --- |
| STORY-A@r1 | SOURCE-A@r1 | XML-A@r2, RENDER-A@r1 timing/audio |
| IMAGE-A@r1 | STORY-A@r1 | CHARACTER-A@r1, registered prompt/settings |
| TAKE-A@r1 and TAKE-B@r1 | IMAGE-A@r1 | Exact Flow-kit, prompt and continuity references used for each take |
| FILM-A@r1 | STORY-A@r1 | RENDER-A@r1, TAKE-A@r1, other selected clips and timeline |
| FILM-B@r1 | STORY-A@r1 | RENDER-B@r1, TAKE-B@r1, other selected clips and its own timeline |

**Check:** querying FILM-B's inputs finds its audio in the music branch and shared
character ancestry outside the song. Alternative storyboards, images, takes and
films remain siblings at their respective stages. Replacing a Flow kit preserves
its old files and the exact kit revision associated with earlier takes.

## 4. Selection is not deletion or regeneration

Select `RENDER-A@r1` at `(song:SONG-A, render, backing)` and `TAKE-B@r1` at
`(artifact:IMAGE-A, clip, chosen-take)`. Later change the audio selection to RENDER-B.

**Check:** RENDER-A and TAKE-A remain available. An already-produced FILM-A still
points to RENDER-A and its original takes; selection does not rewrite that film.
A new assembly pins its explicitly resolved choices at prepare. No selection and
several candidates means ambiguity, not an instruction to use the newest file.
A passing review alone does not change a selection.

## 5. Publication recovery versus another experiment

| Interruption/action | Expected result |
| --- | --- |
| Render wrote full.wav but backing.wav is missing | No completion event or partial render artifact; remain pending or record failure. |
| History saved, completion event not yet published | Resume from the saved intent/event bytes with the same IDs; no rerender. |
| Completion recorded, browsing update interrupted | Repair the view only. Existing files with intended hashes count as already repaired. |
| Unexpected local edit at a browsing destination | Stop replacement and report it; preserve the edit and history. |
| User asks for another render with identical settings | New run and artifact identities, even if output hashes match. |
| User retries production after a terminal failure | New run; the failed run remains in history. |

**Check:** a recovered publication appears once; a deliberate second experiment
appears twice. Failed output bytes do not masquerade as completed deliverables.

## 6. Collaboration, resources and existing files

| Situation | Expected result |
| --- | --- |
| Two offline collaborators revise XML-A from r1 | Both valid revisions survive synchronization; report competing heads, never choose by timestamp. |
| Collaborators independently change the same render selection | Show conflict until explicit resolution; existing films stay pinned. |
| Completion arrives before its history files | Show registered but pending/unavailable output; do not supply missing bytes to a tool. |
| A new host has the resource descriptor but lacks its matching model/sample bytes | Report unavailable resources; do not substitute a newer installation. |
| Register an existing source in the new layout | Preserve the original; copy its bytes into managed history/view and mark unknown provenance honestly. |
| Import identical bytes again as a distinct acquisition | New attempt with its own origin evidence; byte equality is not run identity. |
| Move a subtree within its existing parent/root | Preserve identities, descendants and historical dependencies; reject collisions, unexpected files and unsupported path lengths. |

**Check:** shuffled event/file arrival converges to the same known state, with
explicit conflicts and incomplete synchronization. Rebuilding the catalogue never
creates missing history, chooses a preferred take or deletes unknown files.
