# Plan — a1-plain

The defect is in `calc/__init__.py:8` — `mean` divides by `len(xs) - 1` instead of `len(xs)`, which breaks `test_mean` (returns 3.33 instead of 2.5) and makes `mean([7])` a ZeroDivisionError. `median` is correct.

1. In `calc/__init__.py`, fix `mean` to divide the sum by `len(xs)` instead of `len(xs) - 1`, keeping the empty-list `ValueError` guard intact. (local-ok)
2. In `calc/__init__.py`, add a brief docstring to `mean` and `median` stating the averaging semantics (population mean; median averages the two middle values for even-length input) so the off-by-one is not reintroduced. (local-ok)

Test: `python3 -m pytest -q`

## Log
- step 1 done by local/harness in 16.4 s
- step 2 done by local/harness in 17.6 s
