#!/usr/bin/env python3
"""Run the tablet dashboard and keep it updated from GitHub.

The supervisor is intentionally small and cross-platform so the same deployment
pattern works first on the Windows MVP server and later on Raspberry Pi.

It starts ``web_dashboard.py``, periodically checks the configured Git branch,
fast-forwards the local checkout when a newer commit is available, and restarts
the dashboard process so the new code takes effect.

Safety rules:
- only the configured branch is followed
- tracked local changes block automatic pulls instead of being overwritten
- only fast-forward pulls are accepted
- config.yaml and credentials stay local/gitignored
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
log = logging.getLogger("dashboard.supervisor")


def _run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def _git_text(*args: str) -> str:
    return _run_git(*args).stdout.strip()


def _tracked_tree_is_clean() -> bool:
    # Ignore untracked/generated files; only tracked edits could conflict with a pull.
    return not _git_text("status", "--porcelain", "--untracked-files=no")


def _current_branch() -> str:
    return _git_text("branch", "--show-current")


def _changed_files(old_sha: str, new_sha: str) -> list[str]:
    output = _git_text("diff", "--name-only", old_sha, new_sha)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _update_available(branch: str) -> tuple[str, str] | None:
    """Fetch the branch and return (local_sha, remote_sha) when it can fast-forward."""
    _run_git("fetch", "origin", branch)
    local_sha = _git_text("rev-parse", "HEAD")
    remote_ref = f"origin/{branch}"
    remote_sha = _git_text("rev-parse", remote_ref)

    if local_sha == remote_sha:
        return None

    # Automatic deployment must never resolve merges or rewrite local history.
    is_ff = _run_git(
        "merge-base", "--is-ancestor", local_sha, remote_ref, check=False
    ).returncode == 0
    if not is_ff:
        log.error(
            "Remote branch cannot fast-forward the local checkout. "
            "Automatic update skipped; resolve the branch state manually."
        )
        return None

    return local_sha, remote_sha


def _pull(branch: str) -> None:
    result = _run_git("pull", "--ff-only", "origin", branch)
    if result.stdout.strip():
        log.info("git pull: %s", result.stdout.strip().replace("\n", " | "))


def _server_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "web_dashboard.py"),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--refresh-seconds",
        str(args.refresh_seconds),
        "--config",
        args.config,
    ]
    if args.no_cache:
        command.append("--no-cache")
    return command


def _start_server(args: argparse.Namespace) -> subprocess.Popen:
    command = _server_command(args)
    log.info("Starting dashboard server: %s", " ".join(command))
    return subprocess.Popen(command, cwd=ROOT)


def _stop_server(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    log.info("Stopping dashboard server for update...")
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        log.warning("Dashboard server did not stop in time; killing it")
        process.kill()
        process.wait(timeout=5)


def _reload_supervisor_if_needed(changed_files: list[str]) -> None:
    if Path(__file__).name not in changed_files:
        return
    log.info("Supervisor itself changed; reloading the updated supervisor")
    try:
        os.execv(sys.executable, [sys.executable, *sys.argv])
    except OSError:
        # If process replacement is unavailable for some reason, continue with
        # the already-running supervisor and at least restart the dashboard.
        log.exception(
            "Could not reload the supervisor process automatically; "
            "the new supervisor code will take effect after the next manual restart"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run web_dashboard.py and automatically deploy fast-forward Git updates"
    )
    parser.add_argument(
        "--branch",
        default="family-dashboard-v1",
        help="Git branch to follow (default: family-dashboard-v1)",
    )
    parser.add_argument(
        "--check-seconds",
        type=int,
        default=60,
        help="How often to check GitHub for a newer commit (default: 60)",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--refresh-seconds", type=int, default=30)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--no-cache", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.check_seconds < 30:
        raise SystemExit("--check-seconds must be at least 30")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        branch = _current_branch()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Git repository check failed: {exc}") from exc

    if branch != args.branch:
        raise SystemExit(
            f"Current Git branch is '{branch}', but supervisor is configured for "
            f"'{args.branch}'. Switch branches first; the supervisor will not do it automatically."
        )

    log.info(
        "Auto-update enabled: origin/%s every %ss; dashboard refresh every %ss",
        args.branch,
        args.check_seconds,
        args.refresh_seconds,
    )

    server: subprocess.Popen | None = _start_server(args)
    next_git_check = 0.0  # check immediately after startup

    try:
        while True:
            # Keep the dashboard alive even if it exits for an unrelated reason.
            if server is None or server.poll() is not None:
                exit_code = server.returncode if server is not None else None
                log.warning(
                    "Dashboard server is not running (last code %s); restarting in 5 seconds",
                    exit_code,
                )
                time.sleep(5)
                server = _start_server(args)

            now = time.monotonic()
            if now >= next_git_check:
                next_git_check = now + args.check_seconds
                try:
                    if not _tracked_tree_is_clean():
                        log.warning(
                            "Tracked local files have changes; automatic Git update skipped "
                            "to avoid overwriting local work"
                        )
                    else:
                        update = _update_available(args.branch)
                        if update:
                            old_sha, new_sha = update
                            files = _changed_files(old_sha, new_sha)
                            log.info(
                                "New repository version available: %s -> %s (%s)",
                                old_sha[:8],
                                new_sha[:8],
                                ", ".join(files) or "no file list",
                            )
                            _stop_server(server)
                            server = None
                            try:
                                _pull(args.branch)
                            except Exception:
                                # The old checkout is still usable if pull failed.
                                log.exception("Automatic git pull failed")
                                server = _start_server(args)
                            else:
                                if any(
                                    Path(name).name.startswith("requirements")
                                    for name in files
                                ):
                                    log.warning(
                                        "Requirements changed. Code was updated, but Python "
                                        "packages are not auto-installed; install requirements "
                                        "manually if the new version needs them."
                                    )
                                _reload_supervisor_if_needed(files)
                                server = _start_server(args)
                except FileNotFoundError:
                    log.exception("Git executable was not found; automatic updates disabled for this tick")
                except subprocess.CalledProcessError as exc:
                    stderr = (exc.stderr or "").strip()
                    log.error("Git update check failed: %s", stderr or exc)
                except Exception:
                    log.exception("Unexpected automatic-update error")

            time.sleep(2)
    except KeyboardInterrupt:
        log.info("Stopping supervisor...")
    finally:
        _stop_server(server)


if __name__ == "__main__":
    main()
