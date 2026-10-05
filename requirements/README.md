# Dependencies

Use Python 3.11+ in the repo-root `env/` virtual environment. Install the maintained
[Python requirements](requirements-python.txt) with that environment's Python:

```console
env/bin/python -m pip install -r requirements/requirements-python.txt
```

Windows uses `env/Scripts/python.exe`. Reinstall after requirements change.
These are direct dependencies of retained skill code, not an export of one host's
installed packages. Backend/voicebank model compatibility must be checked against
the chosen external installation.

Install MuseScore, FFmpeg, Java/JJazzLab, FluidSynth, sound banks and voice models
outside the checkout as needed. Set tool argument lists and absolute resource
paths in `config.local.toml`; see [configuration](../docs/configuration.md) and
[JJazzLab setup](../tools/jjazzlab/README_SETUP.md). Native packages, model weights,
sample libraries and inference runtimes are not vendored here. Optional manual
RVC work uses its separately configured environment.
