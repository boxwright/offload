---
title: Give jobs readable ids and accept an id prefix everywhere
repo: ~/repos/offload.git
test: python3 -m pytest -q tests
id: j20260924-082543
branch: offload/j20260924-082543
---
## Goal
A job id is a timestamp: `j20260924-082225`. The owner cannot tell from `offload
status`, or from a Discord message, which job is which, and has to copy a
twenty-character string to run `offload report`. Titles already exist and are
already shown, truncated. Put the title into the id where that is possible, and
let every command take a short unique prefix so nobody retypes a timestamp.

A job created from a spec knows its title before the job directory exists, so its
id can carry a slug. A job created from a one-line request does not, because
intake runs after the directory is made, so it keeps the timestamp id. Do not
rename a job directory after intake: a rename mid-flight breaks the paths already
written into events and reports.

Requirements:
1. `src/offload/jobs.py`: add `slugify(text)` returning at most 32 characters of
   lowercase ASCII, words joined by single hyphens, every other character dropped,
   leading and trailing hyphens stripped. An empty result is reported to the
   caller, never a silent empty id.
2. `src/offload/jobs.py`: `add()` gains an optional `slug` argument. When given,
   the job id is the date, a hyphen, then the slug. When not given, the id is
   exactly what it is today. The existing collision suffix applies to both shapes.
3. `src/offload/cli.py`: for `offload add --spec FILE`, read `name` from the spec
   front matter if present, otherwise `title`, pass it through `slugify`, and use
   it as the slug. A spec with neither key falls back to the timestamp id rather
   than failing.
4. `src/offload/jobs.py`: add `resolve_job_id(jobs_root, text)` returning the one
   job id starting with `text`. No match is an error naming the text. More than
   one match is an error listing the matches. An exact match always wins, even
   when it is also a prefix of another id.
5. `src/offload/cli.py`: `report`, `answer`, `cancel` and `retry` resolve their job
   argument through `resolve_job_id`.
6. `src/offload/status.py`: do not truncate a title below 60 characters.
7. Tests in `tests/`: slugify on a long title, on punctuation and mixed case, and
   on a title that slugifies to nothing; a spec-created id carries the slug; a
   one-line job keeps the timestamp shape; two jobs from one title on one day get
   the collision suffix; prefix resolution for a unique prefix, for no match, for
   an ambiguous prefix, and for an exact match that also prefixes another id.

## Done when
- `python3 -m pytest -q tests` passes
- A spec titled "Give jobs readable ids" yields an id beginning with the date then `give-jobs-readable-ids`
- A one-line `offload add` still yields an id of the current timestamp shape
- `offload report <unique-prefix>` resolves to the full id
