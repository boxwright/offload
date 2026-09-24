# Plan — demo-011

1. In `calc/__init__.py`, fix `mean` to divide the sum by `len(xs)` instead of `len(xs) - 1`, which currently skews every average and raises `ZeroDivisionError` for single-element input. (local-ok)
2. Add short docstrings to `add`, `mean`, and `median` in `calc/__init__.py` stating the population-mean divisor and the empty-input `ValueError` contract, so the off-by-one is not reintroduced. (local-ok)

Test: `python3 -m pytest -q`

## Log
- step 1 done by local/harness in 20.6 s
- step 2 done by local/harness in 18.0 s
