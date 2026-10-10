# Arrangement implementation

`jjazzlab_experiments/` contains the reusable portion of the collaborator's
adapter. See [setup and limitations](../references/barnsang-adapter.md).

The skill calls compiler → executor → `ChildExperiment.java` → child renderer →
local publisher/delivery checker. The renderer imports `verification.py` and
`sample_renderer.py`; the publisher uses `listening_page.html`. Historical batch
mains, library converters, fixed song choices and experiment records are excluded.
External installations and resources are configured locally; all produced files
belong under the project data root. Importing these modules does not load native
libraries, run tools or create directories.
