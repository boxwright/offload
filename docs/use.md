# Using Offload from a project

Offload runs on the box. Your project stays on the box. What comes back is a branch on the repository you
registered and a report. This page is the short version; the full procedure a Claude session follows is
`skills/offload/SKILL.md`, and it is written for people too.

## Install the skill on the machine you work from

```bash
mkdir -p ~/.claude/skills && cp -r skills/offload ~/.claude/skills/offload
```

From then on `/offload` in a Claude Code session, or any request to queue a job, follows that procedure.
On a laptop, `bin/offload-remote` symlinked as `offload`, with the box's SSH name in `~/.config/offload/host`,
gives the same command over SSH.

## The four steps

1. `offload doctor` and `offload repo list`. Register the repository once:
   `offload repo add <path-or-url the box can reach> "one line on what it is"`.
2. Write a spec (template in the skill): goal, numbered requirements naming files, done-when with commands.
   Put the file on the box.
3. `offload add --spec /path/on/the/box.md`, with `--confirm` if you want to say yes before it starts. A one-line
   `offload add --confirm "..."` works too: intake drafts the spec and posts it to you.
4. `offload status`, `offload report <job>`. Then fetch `offload/<job id>` from the repository you gave,
   read the diff, run the tests, merge.

## Where the branch goes

To the repository you registered, nowhere else. A repository that lives only on the box keeps the code on the
box; review it there. A clone on another machine sees the branch after `git fetch` from that repository.

## When it waits

A job that waits for you (`waiting_owner`) shows the question in `offload status` and in your Discord or ntfy
channel. `offload answer <job> yes`. A rate limit or the weekly budget parks the job and the next one runs.

## Deploying Offload itself

The box runs `main` of its own repository. `offload-deploy` on the box fetches it, installs, restarts and runs doctor.
No other path changes the installed package. See `docs/design/one-deployer.md`.
