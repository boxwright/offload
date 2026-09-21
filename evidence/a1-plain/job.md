---
id: a1-plain
title: Fix the failing statistics tests in the demo repository
repo: ~/.local/share/offload/demo-calc.git
test: python3 -m pytest -q
---
## Goal
The tests in `tests/` fail because of a defect in `calc/__init__.py`. Find and fix it without changing the tests.

## Done when
`python3 -m pytest -q` passes, the change touches only `calc/`, and the branch is pushed.
