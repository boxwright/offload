"""The `offload` command. Each subcommand imports only what it needs, so `offload status` stays quick."""
import argparse
import json
import os

DESCRIPTION = "Offload: make your Claude subscription last longer by doing the typing on a local model."


def _jobs_root(args):
    from offload.config import get_config
    return getattr(args, "jobs", None) or get_config().jobs_root


def _job_dir(name):
    """A job given by id is looked up under the jobs root; a path is used as it is."""
    from offload.config import get_config
    return name if os.path.isdir(name) else os.path.join(get_config().jobs_root, name)


def _cmd_init(args):
    from offload.setup_cmds import init
    return init(systemd=not args.no_systemd)


def _cmd_doctor(args):
    from offload.setup_cmds import doctor
    return doctor()


def _cmd_demo(args):
    from offload.setup_cmds import demo
    return demo()


def _cmd_serve(args):
    from offload.daemon import serve
    serve(_jobs_root(args))
    return 0


def _cmd_run(args):
    from offload.engine import EXIT_PARKED, run
    from offload.status import Parked, set_status
    job_dir = _job_dir(args.job_dir)
    try:
        return run(job_dir)
    except Parked as parked:
        set_status(job_dir, parked.status, **parked.wake)
        print(f"parked: {parked.status} {parked.wake}. Run the job again when the wait is over.")
        return EXIT_PARKED


def _cmd_add(args):
    from offload.jobs import add
    add(_jobs_root(args), " ".join(args.text))
    return 0


def _cmd_status(args):
    from offload.report import status_table
    status_table(_jobs_root(args))
    return 0


def _cmd_cost(args):
    from offload.budget import cost_table
    cost_table()
    return 0


def _cmd_report(args):
    from offload.files import read_text
    print(read_text(os.path.join(_job_dir(args.job_dir), "REPORT.md")))
    return 0


def _cmd_answer(args):
    from offload.jobs import answer
    answer(_job_dir(args.job_dir), " ".join(args.text))
    return 0


def _cmd_cancel(args):
    from offload.jobs import cancel
    cancel(_job_dir(args.job_dir))
    return 0


def _cmd_digest(args):
    from offload.report import digest
    digest(_jobs_root(args), send=not args.no_post)
    return 0


def _cmd_budget(args):
    from offload.budget import load_budget, pace_status
    pace = pace_status(load_budget())
    print(json.dumps({"allowed_now": pace.allowed, "spent_week_usd": round(pace.spent, 3),
                      "pace_now_usd": round(pace.pace_now, 3), "allowance_week_usd": pace.allowance,
                      "wait_s": pace.wait_s}))
    return 0


def _cmd_cleanup(args):
    from offload.cleanup import run_cleanup
    run_cleanup(_jobs_root(args), dry_run=args.dry_run)
    return 0


def _cmd_pause(args):
    from offload.config import get_config
    pause_file = get_config().pause_file
    os.makedirs(os.path.dirname(pause_file), exist_ok=True)
    open(pause_file, "w").close()
    print("paused")
    return 0


def _cmd_unpause(args):
    from offload.config import get_config
    from offload.files import remove_if_exists
    remove_if_exists(get_config().pause_file)
    print("unpaused")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="offload", description=DESCRIPTION)
    commands = parser.add_subparsers(dest="command")

    def command(name, handler, help_text, jobs_root=False):
        sub = commands.add_parser(name, help=help_text)
        if jobs_root:
            sub.add_argument("jobs", nargs="?", default=None, help="the jobs root (default: jobs_root in the config)")
        sub.set_defaults(func=handler)
        return sub

    init = command("init", _cmd_init, "create the config, budget and service files (never overwrites)")
    init.add_argument("--no-systemd", action="store_true", help="do not write the systemd user units")
    command("doctor", _cmd_doctor, "check Docker, the sandbox image, the model proxy and the token")
    command("demo", _cmd_demo, "queue a two-minute job on a sample repository")
    command("serve", _cmd_serve, "watch the jobs root and run jobs one at a time", jobs_root=True)
    command("run", _cmd_run, "run one job end to end").add_argument("job_dir", help="a job id or a path")
    add = command("add", _cmd_add, "add a one-line job to the inbox")
    add.add_argument("--jobs", default=None, help="the jobs root (default: jobs_root in the config)")
    add.add_argument("text", nargs="+")
    command("status", _cmd_status, "print a table of jobs and their status", jobs_root=True)
    command("cost", _cmd_cost, "print weekly spend and the per-job cost ledger", jobs_root=True)
    command("report", _cmd_report, "print a finished job's REPORT.md").add_argument("job_dir")
    answer = command("answer", _cmd_answer, "record the owner's answer to an open gate")
    answer.add_argument("job_dir")
    answer.add_argument("text", nargs="+")
    cancel = command("cancel", _cmd_cancel, "stop a job: now if it waits, before its next worker call if it runs")
    cancel.add_argument("job_dir")
    digest = command("digest", _cmd_digest, "print (and post) the daily digest", jobs_root=True)
    digest.add_argument("--no-post", action="store_true", help="print only")
    command("budget", _cmd_budget, "print the budget pacer state as JSON")
    cleanup = command("cleanup", _cmd_cleanup, "remove old job folders and rotate the ledger", jobs_root=True)
    cleanup.add_argument("--dry-run", action="store_true", help="print what a cleanup would sweep, and change nothing")
    command("pause", _cmd_pause, "start no new work until unpaused")
    command("unpause", _cmd_unpause, "resume the engine")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)
