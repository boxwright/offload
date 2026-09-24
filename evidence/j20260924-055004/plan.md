# Plan — j20260924-055004

1. Fix `mean` in `calc/__init__.py` to divide by `len(xs)` instead of `len(xs) - 1`, so `mean([1,2,3,4]) == 2.5` and `mean([7]) == 7`, leaving `tests/` untouched (local-ok)
2. Harden the rest of `calc/__init__.py` against the same class of off-by-one/branch defect: confirm `median` picks `s[n // 2]` for odd `n` and averages the two middle values for even `n`, and add brief docstrings to `add`, `mean`, and `median` stating the expected behavior and the `ValueError` on empty input (hard)

Test: `python3 -m pytest -q`

## Log
- step 1 done by local/harness in 24.6 s
- step 2 done by local/harness in 35.8 s
