# Bookkeeping execution inventory

Production skills integrate through their `SKILL.md` Bookkeeping blocks. Their
scripts are ordinary domain programs. Bookkeeping interprets the declarations,
binds immutable inputs/resources and invokes captured commands using the
[generic execution interface](../.agents/skills/artifact-bookkeeping/references/usage.md#ordinary-commands-through-bookkeeping).
This document records supported routes and restrictions. The derived source
inventory is generated at `_build/skill-entrypoints.json` by the repository tests;
it is ignored by Git and never required for execution. Regenerate it from the
repo root with:

```text
env/bin/python tests/test_ledger_entrypoints.py EntrypointInventoryTests
```

On Windows use `env/Scripts/python.exe`. The report lists source hashes, ownership,
functions, call expressions and CLI argument definitions. It does not certify
runtime coverage or replace the restrictions below.

| Skill | Enabled ordinary operations and declarations |
| --- | --- |
| score-to-musicxml | Score/schema inspection; persisted verification reports; geometry overlays; bounded PDF page rendering. Pin images, seeds, expectations, schema and renderer resources. |
| download-scores | Catalogue/discovery, selected URL acquisition, text extraction, explicit score conversion. Keep discovery, raw acquisition, extraction and conversion as separate bounded stages. |
| song-arrangement-research | Brief compilation, JJazzLab execution, FluidSynth/sample rendering, local delivery bundle, browser checking. Expand baseline/project/plan/report references; pin native tools, auditor, samples, templates and Python packages. |
| analyze_music | Analysis from exact score and tempo settings; pin music21 and its closure. |
| syllabify_lyrics | Lyrics JSON from text and language; no score consumed. Swedish text retention does not establish reliable Swedish syllabification. |
| plan_vocals | Events from selected score, analysis and lyrics; verify analysis provenance names that exact score. |
| synthesize_vocal_with_diffsinger | Nishiren synthesis from reviewed events, pronunciation lexicon and configured model/backend resources. Missing prerequisites stop production; no placeholder output. |
| barnsang-video | Flow instruction formatting and real clip/audio assembly. Expand all images/clips; distinguish soundtrack, film and timeline dependencies. |
| refine_vocal_with_rvc | Manual/external handoff only; no selected local RVC backend/model is provided. |

The image generation/edit scripts remain unavailable and fail before file access
or remote calls. Refactoring does not enable them. Local response-format tests
are not provider qualification. Native resource closures remain mandatory even
when an ordinary script can run standalone from local configuration.

Bookkeeping owns input resolution, snapshot preparation, argument/configuration
binding, execution receipts, complete output publication and recovery. Reusable
domain helpers remain with their skill. Root `scripts/` contains only shared
configuration/path support and the test runner. No production helper imports the
bookkeeping implementation, requires ledger flags or registers an adapter.

Every managed operation has explicit output contracts and output-specific input
edges. New attempts use fresh identities; explicit revision names its current
base. Agent-written storyboards, prompts, research and external handoffs use the
same preparation and receipt boundary. Read-only discovery/inspection writes no
ledger event; inspected evidence becomes an exact input if later used to produce
an artifact. A registered review does not select a result.

Tests cover domain algorithms independently of bookkeeping, generic managed
invocation, indirect paths, code/package capture, resource closure, output
contracts and recovery. Run `env/bin/python scripts/run_tests.py`. Practical
fresh-agent acceptance, native platform support, live providers and human creative
approval remain separate gates; unavailable prerequisites are BLOCKED, never PASS.
