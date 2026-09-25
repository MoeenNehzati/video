# Portability requirements (lock)

Python environment updated: 2026-09-25. System-tool versions below retain the
2026-05-22 reference snapshot.

Repo scripts use the ignored `env/` virtual environment. The `bin/` wrappers
require `env/bin/python`; they do not fall back to system Python.

## Python runtimes

- Repo venv: `env/bin/python` (Python `3.13.5`, pip `25.1.1`)
- Minimum supported Python: 3.11 (the config reader uses stdlib `tomllib`).
- Optional OpenVPI backend: separate environment described by `conda-diffsinger.yml`.

## Python libraries used by repo scripts

Installed in `env/` from `requirements-python.txt`:

- `numpy==2.3.4`
- `pillow==11.1.0`
- `music21==10.5.0`
- `PyYAML==6.0.2`
- `onnxruntime==1.26.0`
- `soundfile==0.13.1`
- `g2p-en==2.1.0`

## Python libraries mentioned in skill docs (optional / future)

These are referenced in `.agents/skills/*/SKILL.md` but are not necessarily imported by current repo scripts.

- `librosa` (optional; not installed by the repo requirements)
- `pydub` (optional; not installed by the repo requirements)
- `phonemizer` (not checked)
- `pronouncing` (not checked)

## External command-line tools (used by skills/scripts)

- `Audiveris 5.10.2` (Commit `1b7cf44088c68f4168801822a613751d1bb1b584`, installed at `/opt/audiveris/bin/Audiveris`)
- Java: OpenJDK `21.0.10` (`openjdk-21-jre(-headless)` package version `21.0.10+7-1~25.10`)
- `musescore3` package version `3.2.3+dfsg2-19`
- `ffmpeg` package version `7:7.1.1-1ubuntu4.2`
- `fluidsynth` package version `2.4.7+dfsg-2`
- `sox` package version `14.4.2+git20190427-5build1`
- `tesseract-ocr` package version `5.5.0-1`
- `xvfb-run` (from `xvfb` package version `2:21.1.18-1ubuntu1.1`)
- Download helpers (used as fallbacks when present): `aria2c 1.37.0`, `curl 8.12.1`, `wget 1.25.0`

## External source checkouts

- OpenVPI DiffSinger and Nishiren/RVC voice models require separate installation.
  The Python requirements do not install model files or external source checkouts.

## Conda environment lockfiles

- `requirements/conda-diffsinger.yml` is a `conda env export -n diffsinger --no-builds` snapshot for portability.

## Recreate (suggested)

- Create a repo-local venv and install Python deps:
  - `python3 -m venv env`
  - `env/bin/python -m pip install -r requirements/requirements-python.txt`
- Recreate the DiffSinger conda env:
  - `conda env create -f requirements/conda-diffsinger.yml`
