# Requirements

- [Default Python packages](requirements-python.txt) installed in the repo environment.
- [Optional vocal-synthesis packages](requirements-vocals.txt), only when that skill
  is selected; not part of default setup.
- [Non-Python requirements and installation](requirements.md), including tools,
  models, sample banks and recording installed paths in `config.local.toml`.

## Python

First check for Python 3.11+ and a working repo-root `env/`; reuse them when
compatible. Create a missing environment with `python3 -m venv env` on POSIX or
`py -3 -m venv env` on Windows, then satisfy
[the Python requirements](requirements-python.txt):

```console
env/bin/python -m pip install -r requirements/requirements-python.txt
```

Windows uses `env/Scripts/python.exe`. Pip reuses already satisfied packages; do not
use `--upgrade` or `--force-reinstall` for routine setup. Rerun after requirements
change, then check with `-m pip check`. For Nishiren synthesis only, use
`-m pip install -r requirements/requirements-vocals.txt` instead; it includes the
default list. Do not uninstall existing optional packages merely because a stage
does not use them. Inspect installed Python versions with `-m pip list`; the exact
package constraints remain in the requirements files.
On Linux, a missing `ensurepip` error means the interpreter's matching venv package
is needed. These requirements support retained skill code, not a snapshot of one
host's installed packages.

Use a Python installation compatible with the configured native libraries. A
Conda-based environment can load its bundled libraries ahead of system libraries;
if FluidSynth fails to load with a missing native-library version, test a fresh
system-Python environment before changing the renderer. Preserve the previous
environment until its replacement passes the project checks.
