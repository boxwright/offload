"""The planner's two read modes: full mode sends today's prompt and the paid worker's tools,
index mode sends the `git ls-files` file tree and a tool list without `Read` or `Bash(cat *)`.

`engine._plan` is driven directly on a real git worktree, with only the paid worker faked.
"""
import dataclasses
import os
import subprocess

from conftest import make_job_dir

from offload import config as config_module
from offload import engine, prompts
from offload.jobs import Job

PLAN_TEXT = "1. write a.txt\n2. write b.txt\n3. write c.txt\n"


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _worktree_with_tree(tmp_path, name="wt"):
    """A git worktree with three files, the same shape `git ls-files` reports them in."""
    work = tmp_path / name
    work.mkdir()
    _git("init", "-q", "-b", "main", cwd=work)
    (work / "a.txt").write_text("a\n")
    (work / "b.txt").write_text("b\n")
    (work / "c.txt").write_text("c\n")
    _git("add", "-A", cwd=work)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "seed", cwd=work)
    return str(work)


def _run_plan(tmp_path, monkeypatch):
    """One `engine._plan` on a fresh job over a seeded worktree. Returns (captured call, Job)."""
    work = _worktree_with_tree(tmp_path)
    job_dir = make_job_dir(tmp_path, "plan-reads", {"id": "plan-reads", "repo": "/r.git"})
    job = Job(job_dir)
    os.symlink(work, job.work)
    calls = {}

    def claude(_job, prompt, model, max_turns, purpose, tools=None):
        calls.update(prompt=prompt, model=model, max_turns=max_turns, purpose=purpose, tools=tools)
        return PLAN_TEXT, {}
    monkeypatch.setattr(engine, "claude", claude)
    plan_text, steps = engine._plan(job)
    assert plan_text == PLAN_TEXT and len(steps) == 3
    return calls, job


def test_full_mode_sends_todays_prompt_and_tools(settings, tmp_path, monkeypatch):
    """Full mode: the prompt is word for word what the planner got before this change, and the
    tools are the paid worker's, `Read` and `Bash(cat *)` included."""
    calls, _ = _run_plan(tmp_path, monkeypatch)
    assert calls["prompt"] == prompts.plan_prompt(Job(os.path.join(tmp_path, "plan-reads")))
    assert "Read this repository (read-only)" in calls["prompt"]
    assert "file tree" not in calls["prompt"]
    assert calls["tools"] == settings.claude_tools
    assert "Read" in calls["tools"].split(",") and "Bash(cat *)" in calls["tools"].split(",")
    assert calls["purpose"] == "plan" and calls["model"] == "auto"
    assert calls["max_turns"] == settings.plan_max_turns


def test_index_mode_sends_the_file_tree_and_no_content_tools(settings, tmp_path, monkeypatch):
    """Index mode: the prompt carries the `git ls-files` tree, and the tools keep everything
    except the two that read file contents."""
    config = dataclasses.replace(settings, plan_reads="index")
    config_module.set_config(config)
    try:
        calls, _ = _run_plan(tmp_path, monkeypatch)
    finally:
        config_module.set_config(settings)
    assert "file tree" in calls["prompt"]
    assert "a.txt" in calls["prompt"] and "b.txt" in calls["prompt"] and "c.txt" in calls["prompt"]
    assert "Read this repository" not in calls["prompt"]
    parts = calls["tools"].split(",")
    assert "Read" not in parts and "Bash(cat *)" not in parts
    assert parts == [t for t in settings.claude_tools.split(",") if t not in ("Read", "Bash(cat *)")]
    assert "Glob" in parts and "Grep" in parts
    assert calls["max_turns"] == config.plan_max_turns


def test_plan_prompt_without_a_tree_is_the_unchanged_prompt(settings):
    """`plan_prompt(job)` with no tree is byte for byte the old prompt; the tree is appended after it."""
    job = Job(make_job_dir(settings.jobs_root, "prompt-shape", {"id": "prompt-shape", "repo": "/r.git"}))
    base = prompts.plan_prompt(job)
    assert prompts.plan_prompt(job, None) == base
    assert "file tree" not in base
    sentence = "Read this repository (read-only) and write a plan for the job below."
    tree = "a.txt\nb.txt\nc.txt"
    with_tree = prompts.plan_prompt(job, tree)
    # the tree takes the place of the read-the-repo sentence; the rest of the prompt is untouched
    assert with_tree.startswith("    You are the planner. This is the repository's file tree "
                                "(read-only; do not read file contents):\n" + tree
                                + "\nWrite a plan for the job below.")
    assert with_tree.endswith(base[base.index(sentence) + len(sentence):])


def test_file_tree_lists_the_worktree_files(settings, tmp_path):
    """`_file_tree` is the worktree's `git ls-files` output, one path per line."""
    work = _worktree_with_tree(tmp_path)
    assert engine._file_tree(work) == "a.txt\nb.txt\nc.txt"
