# Plan — a2-killed

1. Fix the divisor bug in `mean()` in `calc/__init__.py` so it divides the sum by `len(xs)` instead of `len(xs) - 1`, keeping the empty-input `ValueError` intact. (local-ok)
2. Re-check `median()` in `calc/__init__.py` against the odd/even cases in `tests/test_calc.py` and adjust the branch or add a clarifying docstring/comment so both parity paths are correct and documented. (hard)

Test: `python3 -m pytest -q`

## Log
- step 1 done by local/harness in 16.6 s
- step 2 done by local/harness in 28.4 s
