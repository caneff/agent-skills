"""Run a long command, alone or in a throwaway worktree, under a wall clock (spec #1730).

The one copy of what drain's per-merge run and the nightly backstop's full run share: a command in
its own process group, so the wall clock, ctrl-C and SIGTERM reach everything it started, and a
detached scratch worktree of a revision (`shellcmd.scratch_worktree`) with every tracked
`package-lock.json` installed before the command. Every failure raises `ScratchError`; callers wrap
it in their own exception type at their edge. The directory belongs to no skill, so backstop uses
this without importing drain (#1779)."""
import contextlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile

import shellcmd


class ScratchError(Exception):
    """A run failed: it could not start, passed its wall clock, or exited non-zero."""


def one_line(text, limit=300):
    """`text` with its whitespace collapsed, cut to `limit` characters."""
    return " ".join(str(text).split())[:limit]


def _kill(proc):
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()
    if proc.stdout:
        proc.stdout.close()


def run_group(cmd, cwd, timeout, out=None, preexec=None):
    """`(exit code, output)` of `cmd` in its own process group, with the git-redirecting variables
    scrubbed. With `out` (an open file) the output goes there and `output` is ''. Past `timeout`
    seconds the whole group is killed and `ScratchError` raised; a command that cannot start raises
    `OSError`."""
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=out or subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            env=shellcmd.scrubbed_env(), start_new_session=True, preexec_fn=preexec)
    try:
        text, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill(proc)
        raise ScratchError(f"{cmd[0]} passed the {timeout}s wall clock") from None
    except BaseException:
        _kill(proc)
        raise
    return proc.returncode, text or ""


def install_node_deps(directory, timeout, out=None):
    """Run `npm ci` in `directory` when it holds a `package-lock.json`; return whether it did. The one
    install the scratch run (#1445, #1502) and the lane's worktree creation (#1624) share. A failed or
    unstartable install raises `ScratchError`; a directory with no lockfile is left alone, and says so
    by returning False. With `out` (an open file) npm's output goes there."""
    if not os.path.isfile(os.path.join(directory, "package-lock.json")):
        return False
    try:
        code, _ = run_group(["npm", "ci"], directory, timeout, out=out)
    except OSError as exc:
        raise ScratchError(f"`npm ci` could not start: {exc}") from exc
    if code:
        raise ScratchError("`npm ci` failed")
    return True


def run_in_scratch_tree(root, rev, cmd, log, timeout, head=None):
    """`cmd` (a shell string) in a throwaway detached worktree of `root` at `rev`, with `head`
    merged in first when given (the merge commit uses the identity the repo is configured with).
    Each directory holding a tracked `package-lock.json` gets `npm ci` before `cmd`, since a bare
    worktree has no `node_modules` (#1445, #1502). Everything after the merge writes to `log`.
    Raises `ScratchError` on a failed add, a conflict, a failed install or a non-zero exit."""
    scratch = tempfile.mkdtemp(prefix="scratch-run-")
    try:
        with shellcmd.scratch_worktree(root, rev, scratch):
            if head:
                merged = shellcmd.git(["merge", "--no-edit", head], cwd=scratch, ok=range(256))
                if merged.returncode:
                    raise ScratchError(f"merging {head} into {rev} failed: "
                                       + one_line(merged.stderr or merged.stdout, 200))
            with open(log, "w") as out:
                listed = shellcmd.git(["ls-files", "-z", "--", "package-lock.json", "*/package-lock.json"],
                                      cwd=scratch).stdout
                for lock in sorted(x for x in listed.split("\0") if x):
                    try:
                        install_node_deps(os.path.join(scratch, os.path.dirname(lock)), timeout, out=out)
                    except ScratchError as exc:
                        raise ScratchError(f"{exc} (output in {log})") from None
                code, _ = run_group(["sh", "-c", cmd], scratch, timeout, out=out)
            if code:
                raise ScratchError(f"`{cmd}` failed (output in {log})")
    except shellcmd.CmdError as exc:
        raise ScratchError(str(exc)) from None
    except OSError as exc:
        raise ScratchError(f"{type(exc).__name__}: {exc}") from None
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _install_cli(directory, timeout=900, tail=20):
    """`scratch_run.py install <dir>`: what the lane runs on a fresh worktree. Exit 0 and silent when
    the install ran or there was no lockfile; exit 1 with npm's last `tail` lines and the command to
    re-run when it did not, so a failed install is never read as a bare worktree."""
    with tempfile.TemporaryFile(mode="w+") as out:
        try:
            install_node_deps(directory, timeout, out=out)
        except ScratchError as exc:
            out.seek(0)
            last = "".join(out.readlines()[-tail:])
            print(f"{exc} in {directory}\n{last}re-run: cd {directory} && npm ci", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "install":
        sys.exit("usage: scratch_run.py install <dir>")
    sys.exit(_install_cli(sys.argv[2]))
