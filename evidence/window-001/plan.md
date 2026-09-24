# Plan — window-001

1. In `calc/__init__.py`, fix `mean` to divide `sum(xs)` by `len(xs)` instead of `len(xs) - 1`, so `mean([1,2,3,4]) == 2.5` and `mean([7]) == 7` without a ZeroDivisionError. (local-ok)
2. In `calc/__init__.py`, add a one-line docstring to `mean` (and `median`) stating the arithmetic definition and the empty-input `ValueError`, without changing behaviour. (local-ok)

Test: `python3 -m pytest -q`

## Log
- step 1 done by local/harness in 13.6 s
- step 2 done by local/harness in 20.2 s
