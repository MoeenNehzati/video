# Non-Python requirements and installation

This is a dependency reference, not a list to install in full. Python packages and
environment setup are listed separately in
[requirements-python.txt](requirements-python.txt) and [README.md](README.md).

## Check before installing

1. Identify the selected skill and operation. Require a current skill/script usage
   for each dependency; skip everything else, including unused optional workflows.
2. Read `config.local.toml` first. Check its paths, then look on `PATH` (Python's
   `shutil.which` works across platforms), in OS application/package records and
   known external resource directories. An absent TOML entry does **not** mean the
   software is absent. Inspect installed application bundles when no CLI is on PATH.
3. Probe the discovered installation's version and the required capability. Reuse
   it if compatible; do not reinstall or upgrade merely because a newer version
   exists. Only install a missing requirement, or replace an incompatible one after
   identifying the failed requirement. Keep software and resources outside the repo.
4. Record verified paths and versions in local TOML using the keys below, preserving
   other settings. Rerun `bin.read_config` and the selected operation's smoke check.
   Refresh the version record whenever the installation or configured path changes.

| Selected operation | Dependencies to check | Version/identity check |
| --- | --- | --- |
| Score engraving/conversion | MuseScore | Configured command plus `--version` |
| Optional scanned-PDF OMR | Audiveris and its OCR data | Command plus `-version`; data release/hash |
| Arrangement execution | Java JDK, JJazzLab Toolkit, rhythms, MIDI auditor | Java/compiler `-version`; resource release/hash |
| Arrangement audio rendering | FluidSynth library, approved soundfonts, MIDI auditor, FFmpeg | Native `fluid_version_str()`; bank/helper hashes; FFmpeg `-version` |
| Listening-page verification | Chromium-family browser | Command plus `--version` |
| Video assembly | FFmpeg and FFprobe | Each command plus `-version` |
| Optional vocal synthesis | Nishiren voicebank and ONNX Runtime | Bank release/manifest hash; Python package version |
| Optional voice refinement | Chosen RVC/SVC tool and models | Tool release/commit; model/index hashes |
| Image/Flow generation | Selected service/account access | Record actual model/revision in the run, not an installation version |

Nishiren is used only by the retained `synthesize-vocal-with-diffsinger` skill.
**Skip Nishiren, ONNX Runtime and RVC during default setup.** Their absence does not
block transcription, arrangement or video work. Enable them only when that optional
operation is requested. Analysis, syllabification and vocal planning need no
additional non-Python installation.

## Connecting an installation to the skills

After installing or finding a compatible dependency, verify it and **immediately
record its actual path in `config.local.toml`**, preserving existing settings.
The TOML keys below are exact names used by this project. Configuration records
locations and verified versions; it does not install software.

- `[tools.NAME].command` is an argument list: executable path followed by any fixed
  arguments. Scripts append the operation's input/output arguments and run it without
  a shell. Prefer the verified absolute executable path; a name on `PATH` also works.
- `[resources]` values are absolute paths to external files/directories. Scripts
  validate their existence, then load the resource. Use Windows forward slashes or
  TOML literal strings for Windows paths; `~` and `$VARIABLE` are not expanded.
- `paths.data_root` identifies project artifacts, not installed software. It must
  already exist and be separate from this checkout.
- Record the observed version in `tools.NAME.version`, alongside its command.
  Record each configured resource's release in `resource_versions.NAME`, matching
  its key in `[resources]`. For unversioned files use `sha256:<digest>`; for a
  directory use a release/commit or the hash of a manifest covering its contents.
  Never substitute a desired version, directory name or unknown value for evidence.
  These version fields are setup records: the reader preserves them, but current
  scripts do not enforce version pins or refresh them automatically.
- `bin.read_config` merges shared defaults with local TOML; automated scripts use
  it through `bin.project_runtime`. Run the repo Python with `-m bin.read_config`
  after changing settings. Then perform the relevant check below: path validation
  alone does not establish a working installation.

The examples are placeholders. Merge only the required entries into local TOML;
never copy machine paths into shared `config.toml` or commit local configuration.
See [the complete TOML example](../config.local.example.toml) and
[configuration conventions](../docs/configuration.md).

For example (replace placeholders with observed values):

```toml
[tools.ffmpeg]
command = ["/absolute/path/to/ffmpeg"]
version = "<reported version including build suffix>"
[resources]
fluidsynth_library = "/absolute/path/to/native/fluidsynth-library"
[resource_versions]
fluidsynth_library = "<version returned by this library>"
```

Bundled runtimes/OCR engines can have different versions from system tools; record
those in `tools.NAME.bundled_versions` (a string-valued table), and OCR data in
`tools.audiveris.ocr_data_version`. Reuse an application's bundled runtime when
sufficient; a separate system JDK is needed only by the Java arrangement adapter.
The sections below explain installation **only when the checks above require it**.

## MuseScore: engraving and score conversion

Install [MuseScore Studio](https://musescore.org/en/download) or a compatible OS
package. The transcription workflow uses it for engraving and roundtrip review;
`download_scores.py` invokes it for MusicXML/MIDI/PDF conversion.

```toml
[tools.musescore]
command = ["/absolute/path/to/MuseScore"]
```

Configure headless flags supported by the installed version in this list. For
example, tested MuseScore 3 on Linux uses the prefix
`["/absolute/path/to/mscore3", "-platform", "offscreen", "--no-synthesizer", "--no-midi"]`.
These flags disable live audio/MIDI devices, not MIDI file export. Verify PDF and
MIDI export from a small MusicXML score before batch conversion.

## Audiveris: optional PDF-to-MusicXML recognition

Install [Audiveris using its platform instructions](https://audiveris.github.io/audiveris/_pages/tutorials/install/binaries/),
including the runtime required by that distribution. Configure the launcher:

```toml
[tools.audiveris]
command = ["/absolute/path/to/Audiveris"]
```

The acquisition helper appends `-batch -export -output <directory> <pdf>`.
For printed text/lyrics, install the appropriate OCR languages through Audiveris's
language settings; its documentation describes downloading compatible models.
Music-note recognition can succeed while text recognition is unavailable.

OCR languages and their data directory are configured in **Audiveris**, not via a
repository TOML resource key. A supported `TESSDATA_PREFIX` process environment
variable may override its data location. The helper inherits the environment;
there is currently no `tools.audiveris.env` or `resources.tessdata` setting.
Verify the installed engine/model compatibility, including legacy OCR support when
required, with a page containing both notes and text.

## FFmpeg and FFprobe: audio encoding and video assembly

Install a compatible build containing both programs using the
[FFmpeg platform download/package links](https://www.ffmpeg.org/download.html).
It must support `libx264`, `aac`, `libmp3lame`, PCM audio and the filter chains used
by the skills; minimal builds can omit required codecs.

```toml
[tools.ffmpeg]
command = ["/absolute/path/to/ffmpeg"]
[tools.ffprobe]
command = ["/absolute/path/to/ffprobe"]
```

Arrangement rendering invokes FFmpeg for MP3 encoding. Video assembly uses FFprobe
for durations and FFmpeg for speed changes, mixing and MP4 encoding. Check a short
assembly, then decode the entire result and verify its audio/video streams.

## Java, JJazzLab Toolkit and arrangement verification

Install a **Java 25+ JDK**, including a compiler, compatible with the retained
adapter. Obtain the [JJazzLab Toolkit](https://github.com/jjazzboss/JJazzLabToolkit)
JAR used by the collaborator workflow (5.2.1), plus its compatible rhythm/style
collection. Installing the JJazzLab desktop application alone does not establish
that these adapter resources are available.

```toml
[tools.java]
command = ["/absolute/path/to/java"]
[tools.javac]
command = ["/absolute/path/to/javac"]
[resources]
jjazzlab_toolkit = "/absolute/path/to/toolkit.jar"
jjazzlab_rhythms = "/absolute/path/to/rhythm-directory"
midi_audit = "/absolute/path/to/audit_existing_midi.py"
```

If the JDK provides the compiler module but no standalone launcher, a verified
alternative is `tools.javac.command = ["/absolute/path/to/java", "-m",
"jdk.compiler/com.sun.tools.javac.Main"]`. Both command prefixes are supported.

`execute_child_plans.py` compiles the retained Java source in a temporary directory,
uses the configured toolkit as its classpath, and passes the rhythm directory to
the adapter. Test actual adapter compilation and a baseline variation after a
simple Java compilation/runtime check succeeds.

`resources.midi_audit` must identify the collaborator's proven helper exposing
`read_midi(path)` and `triples(track, ppq)`. It is absent from the supplied bundle;
recover and validate it before enabling execution/rendering. A stub with matching
function names is insufficient. The automatic route also needs an approved
baseline arrangement; it does not create the first pitched arrangement.

## FluidSynth and soundfonts: arrangement audio

Install [FluidSynth](https://www.fluidsynth.org/download/) with a native shared
library matching this OS/architecture and the Python process. The renderer loads
that library through `ctypes`; the `fluidsynth` command alone is insufficient.
Library files are typically `.so` on Linux, `.dylib` on macOS or `.dll` on Windows.

Merge these keys into the **existing** `[resources]` table:

```toml
[resources]
fluidsynth_library = "/absolute/path/to/native/fluidsynth-library"
soundfont_manifest = "/absolute/path/to/soundfonts/banks.json"
soundfont_credits = "/absolute/path/to/soundfonts/CREDITS.md"
```

Obtain the approved SF2 palette and its source/license records externally. The
manifest maps each routing name to a file and attribution, for example:

```json
{"generaluser": {"path": "GeneralUser.sf2", "credits": "source and license attribution"}}
```

That example is one entry, not a complete palette. Required keys are `generaluser`,
`nylon`, `steel`, `bass`, `clarinet`, `drums`, `salamander`, plus any selected
`counter_library`. Bank paths may be absolute or relative to the manifest.
The renderer loads these banks, logs their hashes/routing and copies the configured
credits file into each delivery. Do not silently substitute different samples.
Check native-library loading and a short offline render, then validate the selected
palette, full/backing alignment, shared gain and listening quality.

## Chromium-family browser: listening-page checks

Install Chrome or a compatible Chromium-family browser outside the repo. The Python
Playwright client is supplied by `requirements-python.txt`; it uses this explicitly
configured browser rather than requiring a downloaded Playwright browser bundle.

```toml
[tools.browser]
command = ["/absolute/path/to/chrome-or-chromium"]
```

`check_delivery.py` launches it headlessly against the generated local listening
page. Verify audio loading, A/B tempo-position preservation and mobile layout.
This browser setting does not automate Google Flow generation.

## Nishiren voicebank: optional vocal synthesis

Only when this skill is selected, install the
[optional Python requirements](requirements-vocals.txt); the default list omits
ONNX Runtime. First check for an existing compatible bank as described above.

Obtain a compatible Nishiren ONNX voicebank, with permission to use the voice,
externally. Generic DiffSinger banks are not interchangeable with this adapter.
There is no `tools.nishiren` executable: the repo Python runs the ONNX CPU models.

```toml
[resources]
nishiren_root = "/absolute/path/to/Nishiren"
pronunciation_lexicon = "/absolute/path/to/pronunciation.json" # optional
```

Required contents beneath `nishiren_root`:

- `dsdur/`: `linguistic.onnx`, `dur.onnx`, `phonemes.json`, `languages.json`.
- `dsmain/`: `acoustic.onnx`, both JSON maps, and `<STYLE>.emb`.
- `dsvocoder/`: the compatible `.onnx` vocoder; avoid ambiguous extra candidates.
- Optional `dspitch/`: `linguistic.onnx`, `pitch.onnx`, both JSON maps.
- Optional `dsvariance/`: `linguistic.onnx`, `variance.onnx`, both JSON maps.

Optional groups must be complete if present. Each uses its own `<STYLE>.emb` when
available, otherwise `dsmain/<STYLE>.emb`; the duration model uses the same fallback.
See the [synthesis contract](../.agents/skills/synthesize_vocal_with_diffsinger/SKILL.md)
for supported inputs and timing.

Maps associate tokens/languages with integer IDs. Embeddings must contain 384
float values; this adapter assumes hop size 512 and does not read `dsconfig.yaml`.
The optional lexicon maps lowercase lyric tokens to phoneme lists; explicit event
phonemes avoid that requirement. Language/style/sample-rate and inference settings
are CLI arguments, not additional TOML variables. Validate one supported contiguous
sung phrase, then listen for timing and pronunciation; model loading alone is not
acceptance.

## RVC/SVC: optional manual voice refinement

Install the chosen tool in its own supported environment and obtain a compatible
voice model/index. These entries are read by the **skill's manual workflow**; this
repo does not ship an executable that automatically invokes RVC.

```toml
[tools.rvc]
command = ["/absolute/path/to/external/python", "/absolute/path/to/RVC/infer.py"]
[resources]
rvc_model = "/absolute/path/to/voice-model.pth"
rvc_index = "/absolute/path/to/voice-model.index" # only if needed
```

Use the actual installation's interface; the script name above is illustrative,
not a guaranteed RVC entrypoint. The skill appends its verified input/output/model
arguments and records the command. Compare output timing/intelligibility against
the original vocal before accepting it.

## Image and Flow services

Image generation/editing needs `OPENAI_API_KEY` in the process environment, plus an
explicit supported model passed to the image CLI. There is no API-key TOML variable;
never commit credentials. Test only an authorized request with the selected model.
Google Flow needs account access and the user-selected model/settings; generation
and clip download remain manual. No repository TOML entry automates that account.
