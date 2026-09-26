# Plan — j20260926-082131

1. In `calc/__init__.py`, fix `mean` to divide by `len(xs)` instead of `len(xs) - 1`, so `mean([1,2,3,4]) == 2.5` and `mean([7]) == 7` while the empty-list `ValueError` is still raised before any division (local-ok)
2. In `calc/__init__.py`, add one-line docstrings to `add`, `mean`, and `median` documenting the `ValueError("empty")` contract, changing no behaviour (local-ok)

Test: `python3 -m pytest -q`

## Log
- step 1 done by local/harness in 24.5 s
- step 2 done by local/harness in 44.5 s
