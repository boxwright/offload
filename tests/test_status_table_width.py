"""The status table stays aligned for readable job ids.

Slug ids are longer than the old timestamp stamps, so the id column is wide enough
that a date-plus-slug id never pads into the status column, and titles survive to
60 characters. No test touches the network, Docker, or the real home directory.
"""
from conftest import make_job_dir

from offload.report import _title, status_table

# 60 characters: the first 50 are the old limit, the last 10 prove the new one.
TITLE_60 = ("a" * 50) + ("b" * 10)
# 34 characters: the widest id the table must not truncate (10 for j<date>-, 24 slug).
LONG_ID = "j20260924-" + ("a" * 24)


def test_title_keeps_sixty_characters(job_factory):
    """A 60-character title survives the status table's title cut intact."""
    job_dir = job_factory("j-title", meta={"id": "j-title", "title": TITLE_60})
    assert _title(job_dir) == TITLE_60
    assert len(_title(job_dir)) == 60


def test_long_slug_id_does_not_collide_with_the_status_column(settings, capsys):
    """A 34-character date-plus-slug id prints in full, with the status column
    starting on its own fixed field instead of inside the id's padding."""
    jobs_root = settings.jobs_root
    make_job_dir(jobs_root, LONG_ID, meta={"id": LONG_ID, "title": "Long slug"})
    make_job_dir(jobs_root, "j20260924-short", meta={"id": "j20260924-short", "title": "Short"})

    status_table(jobs_root)
    out = capsys.readouterr().out.splitlines()

    long_row = next(line for line in out if line.startswith(LONG_ID))
    short_row = next(line for line in out if line.startswith("j20260924-short"))
    # the id is printed in full, not cut, and the status column starts at a fixed
    # offset (id field 34 + one space) — the long id's padding does not swallow it
    assert long_row[:34] == LONG_ID
    assert long_row[34] == " "
    # the status column starts at the same fixed field for both rows
    assert long_row[35:49].strip() == short_row[35:49].strip() == "ready"
