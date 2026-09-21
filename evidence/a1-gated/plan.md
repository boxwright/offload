# Plan — a1-gated

The defect is in `mean`: it divides by `len(xs) - 1` instead of `len(xs)` (`calc/__init__.py:8`), which breaks `test_mean` and crashes `test_mean_single` with ZeroDivisionError. `median` is correct.

1. Fix the divisor in `mean` in `calc/__init__.py` to divide the sum by `len(xs)` instead of `len(xs) - 1`, keeping the existing empty-input `ValueError` guard. (local-ok)
2. Add a short docstring to `mean` in `calc/__init__.py` stating it returns the arithmetic mean over all elements and raises `ValueError` on empty input, so the population-vs-sample divisor is not reintroduced. (local-ok)

Test: `python3 -m pytest -q`

## Log
- step 1 done by local/harness in 16.6 s
- step 2 done by local/harness in 15.8 s
