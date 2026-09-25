# Requirements

This directory contains pinned dependency snapshots for the pipeline.
Repo scripts use `env/`. External inference backends and system tools have separate setup requirements.

---

## 1. Python virtual environment (repo scripts)

Use Python 3.11+ to create the local venv and install Python dependencies:

```bash
python3 -m venv env
env/bin/python -m pip install -r requirements/requirements-python.txt
```

Run Python commands with `env/bin/python`. The `bin/` wrappers require this interpreter; they do not fall back to system Python.

---

## 2. DiffSinger conda environment (vocal synthesis)

The optional OpenVPI DiffSinger backend has a separate conda environment
for its external inference tools:

```bash
conda env create -f requirements/conda-diffsinger.yml
```

Activate it when running DiffSinger inference directly:

```bash
conda activate diffsinger
```

The repo wrappers do not activate conda automatically. Run external OpenVPI
inference explicitly in its environment. The repo’s Nishiren ONNX backend uses
`env/`; its voicebank must be supplied separately. English phonemization with
`g2p-en` also requires NLTK language data; installing the Python package alone
does not install that data.

---

## 3. System tools

The pipeline relies on several external command-line tools. Install them via
your system package manager (e.g. `apt` on Ubuntu/Debian):

```bash
sudo apt install openjdk-21-jre musescore3 ffmpeg fluidsynth sox tesseract-ocr xvfb
```

Audiveris (sheet music recognition) requires a separate install:

```
/opt/audiveris/bin/Audiveris   ← expected path
```

See `requirements-tools.txt` for the exact versions used on the reference machine.

---

## Files in this directory

- `requirements-python.txt` — pip packages for repo scripts
- `requirements-tools.txt` — system tool versions captured from the reference machine
- `conda-diffsinger.yml` — conda env export for DiffSinger
- `requirements.lock.md` — full portability snapshot: Python runtimes, installed versions, and what is missing
