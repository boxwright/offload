"""Tests for readable job ids: `slugify()` and the optional `slug` argument to `add()`.

`slugify` turns a title into a short lowercase-ASCII slug; `add` builds either a
`j<date>-<slug>` id (when given a slug) or the current `j%Y%m%d-%H%M%S` stamp (when
not), keeping the `-2`, `-3` collision suffix for both shapes. No test touches the
network, Docker, or the real home directory.
"""
import re

from offload import jobs


# ---------------------------------------------------------------- slugify
def test_slugify_long_title_trims_to_a_word_boundary():
    """A long title is trimmed to at most 32 chars, stopping on a word boundary."""
    slug = jobs.slugify("This is a very long title that should be truncated at a word boundary")
    assert len(slug) <= 32
    # the last whole word that fits is "that"; "should" would push it past 32
    assert slug == "this-is-a-very-long-title-that"
    assert not slug.endswith("-")


def test_slugify_punctuation_and_mixed_case():
    """Punctuation is dropped and mixed case is lowercased; words join with one hyphen."""
    assert jobs.slugify("Hello, World!! (v2.0) -- Mixed CASE") == "hello-world-v2-0-mixed-case"
    assert jobs.slugify("Give   jobs: readable ids") == "give-jobs-readable-ids"


def test_slugify_empty_result_raises_value_error_naming_the_text():
    """No ASCII words left -> a ValueError whose message names the input text."""
    for text in ("!!!", "---", ""):
        try:
            jobs.slugify(text)
        except ValueError as err:
            assert text in str(err)
        else:
            raise AssertionError(f"slugify({text!r}) did not raise")


def test_slugify_drops_non_ascii_to_the_ascii_words():
    """Non-ASCII characters are dropped, keeping the ASCII words that remain."""
    assert jobs.slugify("café menu ok") == "caf-menu-ok"


# ---------------------------------------------------------------- add() id shapes
def test_add_without_slug_keeps_the_timestamp_shape(tmp_path):
    """No slug -> the id is the current j%Y%m%d-%H%M%S stamp."""
    job_id = jobs.add(str(tmp_path), "a one-liner idea")
    assert re.fullmatch(r"j\d{8}-\d{6}", job_id)


def test_add_with_slug_makes_a_date_plus_slug_id(tmp_path):
    """A slug -> the id is j<date>-<slug>."""
    job_id = jobs.add(str(tmp_path), "Give jobs readable ids", slug="give-jobs-readable-ids")
    assert re.fullmatch(r"j\d{8}-give-jobs-readable-ids", job_id)
    # the slug is recorded on the job's front matter id
    assert jobs.Job(str(tmp_path / job_id)).id == job_id


def test_add_two_same_slug_jobs_on_one_day_get_suffixes(tmp_path):
    """Two same-title jobs on one day keep the -2, -3 collision suffix."""
    first = jobs.add(str(tmp_path), "same title", slug="same-title")
    second = jobs.add(str(tmp_path), "same title", slug="same-title")
    third = jobs.add(str(tmp_path), "same title", slug="same-title")
    assert re.fullmatch(r"j\d{8}-same-title", first)
    assert second == first + "-2"
    assert third == first + "-3"


def test_add_timestamp_collision_still_gets_suffix(tmp_path, monkeypatch):
    """The timestamp shape keeps its -2 suffix too (same behavior as before)."""
    monkeypatch.setattr(jobs.time, "strftime", lambda fmt: "j20260101-000000")
    first = jobs.add(str(tmp_path), "one")
    second = jobs.add(str(tmp_path), "two")
    assert first == "j20260101-000000" and second == "j20260101-000000-2"


def test_a_spec_job_gets_a_slug_id_from_its_title(tmp_path):
    """The Discord question and `offload status` show the title's words, not a timestamp."""
    spec = tmp_path / "spec.md"
    spec.write_text("---\ntitle: Fix the failing statistics tests\nrepo: /r.git\n---\n## Goal\nfix\n")
    job_id = jobs.add(str(tmp_path / "jobs"), "", spec_file=str(spec))
    assert re.fullmatch(r"j\d{8}-fix-the-failing-statistics-tests", job_id)
    assert jobs.Job(str(tmp_path / "jobs" / job_id)).id == job_id
