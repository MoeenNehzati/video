# Shared project data

Each collaborator sets the absolute path to their local Dropbox project-data copy
as `paths.data_root` in `config.local.toml`. Resolve it with the repo environment's
Python and `-m bin.read_config`. See [configuration](../configuration.md).

All song/run artifacts belong there, including JSON, prompts, reports and one-off
song builders. Preserve existing organization and reviewed inputs. Do not use a
repo-local output/vendor directory. Tools and models live outside the checkout
and are referenced through local configuration.

The proposed nested organization and append-only global history are specified in
[the artifact ledger plan](../artifact-ledger-plan.md). That mechanism is a separate
implementation task; current path validation does not record revisions or lineage.
