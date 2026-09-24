# Plan — window-001

1. In `calc/__init__.py`, fix `mean` to divide by `len(xs)` instead of `len(xs) - 1` so the sample-size-off-by-one is gone and both `test_mean` and `test_mean_single` pass. (local-ok)
2. In `calc/__init__.py`, add short docstrings to `add`, `mean`, and `median` stating the exact averaging convention (population mean over `len(xs)`, median averaging the two middle values for even-length input) so the corrected behaviour is documented at the source. (local-ok)

Test: `python3 -m pytest -q`

## Log
- step 1 done by local/harness in 21.2 s
- step 2 done by local/harness in 11.0 s
