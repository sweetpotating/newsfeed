"""Start the digest workflows on time.

GitHub's ``schedule`` trigger is best-effort: on free runners the 08:00/18:00
SGT bot digest has been starting 3-9 hours late and the "hourly" channel only
4-6 times a day. The always-on listener therefore acts as the clock: at each
due time it starts the workflow itself through the GitHub API, which begins
within about a minute.

The rule for every job is the same, wherever it is checked: a slot counts as
done if *any* run of that workflow was created at or after the slot time. So
the listener never starts a job twice, and the workflows' own (late) schedule
runs — kept as a backup in case the listener is down — skip themselves when
the slot already ran (``python -m ainews.clock should-run``).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional, Tuple

import requests

log = logging.getLogger("ainews.clock")

API = "https://api.github.com"


@dataclass(frozen=True)
class Job:
    workflow: str                       # workflow file name
    hours_utc: Optional[Tuple[int, ...]]  # None = every hour, on the hour
    # How long after a missed slot the listener still starts it (e.g. after a
    # listener restart). Past this, wait for the next slot instead.
    catch_up: timedelta


JOBS = (
    Job("digest-channel.yml", None, timedelta(minutes=55)),
    # 08:00 and 18:00 Singapore time.
    Job("digest-bot.yml", (0, 10), timedelta(hours=6)),
)


def job_for(workflow: str) -> Job:
    for job in JOBS:
        if job.workflow == workflow:
            return job
    raise KeyError(workflow)


def last_slot(job: Job, now: datetime) -> datetime:
    """The most recent due time at or before ``now``."""
    top = now.replace(minute=0, second=0, microsecond=0)
    if job.hours_utc is None:
        return top
    for back in range(0, 25):
        cand = top - timedelta(hours=back)
        if cand.hour in job.hours_utc:
            return cand
    raise ValueError("job has no valid hours")


class GitHubActions:
    """Minimal GitHub Actions REST client for one repo and branch."""

    def __init__(self, repo: str, token: str, branch: str, timeout: int = 20):
        self.repo = repo
        self.branch = branch
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    def runs_since(self, workflow: str, since: datetime,
                   exclude_run_id: Optional[str] = None) -> int:
        """Number of runs of ``workflow`` created at or after ``since``."""
        stamp = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = requests.get(
            f"{API}/repos/{self.repo}/actions/workflows/{workflow}/runs",
            params={"created": f">={stamp}", "per_page": 10},
            headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        runs = resp.json().get("workflow_runs", [])
        return sum(1 for r in runs if str(r.get("id")) != str(exclude_run_id))

    def dispatch(self, workflow: str) -> None:
        resp = requests.post(
            f"{API}/repos/{self.repo}/actions/workflows/{workflow}/dispatches",
            json={"ref": self.branch}, headers=self.headers,
            timeout=self.timeout)
        resp.raise_for_status()


class Scheduler:
    """Called repeatedly by the listener; starts each job once per slot."""

    def __init__(self, actions: GitHubActions, jobs=JOBS,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.actions = actions
        self.jobs = jobs
        self.now = now
        self.done: Dict[str, datetime] = {}   # workflow -> last handled slot

    def tick(self) -> None:
        now = self.now()
        for job in self.jobs:
            slot = last_slot(job, now)
            if self.done.get(job.workflow) == slot:
                continue
            if now - slot > job.catch_up:
                self.done[job.workflow] = slot      # too late; next slot
                continue
            try:
                if self.actions.runs_since(job.workflow, slot) == 0:
                    self.actions.dispatch(job.workflow)
                    log.info("Started %s for the %s UTC slot.",
                             job.workflow, slot.strftime("%H:%M"))
                self.done[job.workflow] = slot
            except requests.RequestException as exc:
                # Leave the slot open; the next tick retries.
                log.warning("Couldn't check/start %s: %s", job.workflow, exc)


def should_run(actions: GitHubActions, workflow: str, now: datetime,
               run_id: Optional[str]) -> bool:
    """For a late schedule run: go ahead only if nothing ran this slot."""
    slot = last_slot(job_for(workflow), now)
    try:
        return actions.runs_since(workflow, slot, exclude_run_id=run_id) == 0
    except requests.RequestException as exc:
        log.warning("Couldn't check earlier runs (%s); running anyway.", exc)
        return True


def from_env(branch: Optional[str] = None) -> Optional[GitHubActions]:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    branch = branch or os.environ.get("GITHUB_REF_NAME")
    if not (token and repo and branch):
        return None
    return GitHubActions(repo, token, branch)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ainews.clock")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("should-run", help="Print true/false: should this "
                       "scheduled run go ahead?")
    p.add_argument("--workflow", required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    actions = from_env()
    if actions is None:
        print("true")           # can't check; don't block the digest
        return 0
    ok = should_run(actions, args.workflow, datetime.now(timezone.utc),
                    os.environ.get("GITHUB_RUN_ID"))
    print("true" if ok else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
