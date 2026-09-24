# Plan — demo-008

Defect confirmed: `calc/__init__.py:8` divides by `len(xs) - 1` (sample-variance style denominator) instead of `len(xs)`, which makes `mean([1,2,3,4])` return 3.33 and `mean([7])` raise `ZeroDivisionError`.

1. In `calc/__init__.py`, change `mean` to divide `sum(xs)` by `len(xs)` instead of `len(xs) - 1`, keeping the existing empty-input `ValueError` guard intact. (local-ok)
2. Add short docstrings to `add`, `mean`, and `median` in `calc/__init__.py` documenting return values and the `ValueError` on empty input, without altering any behavior. (local-ok)

Test: `python3 -m pytest -q`

## Log
- step 1 done by local/harness in 17.9 s
- step 2 done by local/harness in 18.5 s
