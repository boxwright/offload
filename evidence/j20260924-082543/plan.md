# Plan — j20260924-082543

Read `jobs.py`, `cli.py`, `report.py` (the status table, not `status.py`, is where the title is cut to 50) and the tests. Note: `offload add --spec FILE` and an `offload retry` command do not exist yet, so the plan adds `--spec` and applies prefix resolution to the commands that do exist (`report`, `answer`, `cancel`, plus `retry` if it lands later).

1. In `src/offload/jobs.py` add `slugify(text)` (lowercase ASCII words joined by single hyphens, other characters dropped, trimmed to at most 32 chars on a word boundary, leading/trailing hyphens stripped, raising a `ValueError` naming the text when the result is empty) and give `add()` an optional `slug=None` argument that makes the id `j<date>-<slug>` when given and the current `j%Y%m%d-%H%M%S` stamp when not, keeping the existing `-2`, `-3` collision suffix for both shapes; add tests in `tests/test_job.py` for a long title, punctuation and mixed case, an empty result, the timestamp shape, the slug shape and two same-title jobs on one day. (local-ok)
2. In `src/offload/jobs.py` add `resolve_job_id(jobs_root, text)` returning the single job id starting with `text`, with an exact match winning even when it also prefixes other ids, a `KeyError`/`ValueError` naming the text when nothing matches and an error listing the candidates when more than one does; add tests for unique prefix, no match, ambiguous prefix and exact-match-that-also-prefixes. (hard)
3. In `src/offload/jobs.py` add `add_from_spec(jobs_root, spec_path)` that parses the spec's front matter with the existing parser, slugifies `name` if present else `title` and falls back to the timestamp id when neither key exists or the slug comes out empty, creates the job directory, writes the spec as `job.md` with the `id` key set to the new id, and sets status `ready`; wire it to a new `offload add --spec FILE` flag in `src/offload/cli.py` (making `text` optional so `--spec` alone is valid) and test that a spec titled "Give jobs readable ids" yields an id of the date then `give-jobs-readable-ids` while a keyless spec keeps the timestamp shape. (hard)
4. In `src/offload/cli.py` make `_job_dir` resolve a non-path job argument through `resolve_job_id` against the jobs root (paths and full ids keep working unchanged, the resolver's error is printed as a clean message rather than a traceback) so `report`, `answer`, `cancel` and any future `retry` accept a unique prefix; add a CLI-level test that `report` on a unique prefix prints the full job's REPORT.md and that an ambiguous prefix errors with both candidates. (local-ok)
5. In `src/offload/report.py` widen the status table for slug ids: keep titles to 60 characters instead of 50 in `_title` and widen the id column from 18 so a date-plus-slug id is not padded into the status column; add a test that a 60-character title survives intact and a long slug id does not collide with the next column. (local-ok)

Test: python3 -m pytest -q tests

## Log
- step 1 done by local/harness in 351.9 s
- step 2 done by local/harness in 204.0 s
- step 3 done by local/harness in 343.5 s
- step 4 done by local/harness in 392.8 s
- step 5 done by local/harness in 178.4 s
