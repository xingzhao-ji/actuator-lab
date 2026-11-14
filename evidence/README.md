# Historical evidence and publication checks

The October 2026 experiment is retained here. `results.json`, `frozen-inputs.json`, all compressed numerical traces, PNG/PDF figures, independent numerical results and the original paired checkpoint are unchanged. The HTML report only updates its reproduction command. `final-checks.txt` replaces the private home directory with `$HOME` and the old sibling interpreter with `<historical-python>`; no result lines are changed.

`manifest.json` is an unchanged **historical** manifest. It identifies the original workspace, including documentation that is excluded or edited in this public package; it is not a manifest of the current checkout. [Publication provenance](../docs/publication-provenance.json) records source and published hashes for the changed files and exclusions. No historical experiment has been represented as a fresh packaging test.

Use the routine `make test sanitize` commands in [README](../README.md) for this checkout. The included experiment/report/manifest scripts remain available for a new full experiment in a separate disposable checkout; `make verify` rewrites that checkout's evidence.

`publication-checks.txt` records the separate bounded build/unit/CLI/sanitizer checks performed for public packaging. It does not rerun historical experiment gates or change the frozen result.

A later cleanup shortened the cache directory name in `final-checks.txt` and removed authorship/endorsement sentences from both HTML reports and `metrics-v2/README.md`; no measured value changed. The hashes recorded for those files in the historical manifests and publication provenance therefore differ from the current files. The cache directory default was renamed after this record was made, so the hashes for `python/report.py`, `scripts/guard.py`, `tests/test_cli.py` and `tests/test_metrics_cli.py` differ from the current files.
