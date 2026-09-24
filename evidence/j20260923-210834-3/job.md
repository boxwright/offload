---
id: j20260923-210834-3
title: Offload: notify drafted spec, add --spec and opt-in --confirm to offload add
repo: ~/repos/offload.git
test: python3 -m pytest -q
branch: offload/j20260923-210834-3
tier: claude
gates: []
public: false
---
## Goal
In the offload engine source repo, make the job spec that intake drafts visible to the owner without ever introducing a wait. After intake produces the title, goal and done-when, emit them as a notification rather than a question, so the acceptance criteria are surfaced while the job continues to run unattended. Add an `offload add --spec FILE` option that reads a job.md style spec and bypasses the intake Claude call entirely, plus an opt-in `--confirm` flag that parks the job in an approval state before it runs. The default path must remain fully unattended: no new waiting state may be entered unless `--confirm` is passed.

## Done when
- `offload add` on the default path posts the drafted title, goal and done-when as a notification (never a question) and the job proceeds without pausing
- `offload add --spec FILE` ingests a job.md style spec, skips the intake Claude call entirely, and creates the job with fields taken from the file
- `offload add --confirm` parks the job in an approval/waiting state before execution, and that state is reachable only via the flag
- Tests cover all three paths and include an explicit test asserting the default path never enters a waiting state; the repo's test suite passes
