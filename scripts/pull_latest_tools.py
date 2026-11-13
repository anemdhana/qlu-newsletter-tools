#!/usr/bin/env python3
"""
Install Git (if needed) and clone/pull the latest qlu-newsletter-tools
into the user's GitHub folder. Prints a short, readable recent log.

Typical paths:
  Windows:  %USERPROFILE%\\GitHub\\qlu-newsletter-tools
  macOS/Linux: ~/GitHub/qlu-newsletter-tools

Examples:
  python pull_latest_tools.py
  python scripts/pull_latest_tools.py
  python pull_latest_tools.py --dir D:\\GitHub
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_SSH = "git@github.com:anemdhana/qlu-newsletter-tools.git"
REPO_HTTPS = "https://github.com/anemdhana/qlu-newsletter-tools.git"
REPO_NAME = "qlu-newsletter-tools"
DEFAULT_BRANCH = "master"
LOG_COUNT = 12


# —— pretty console ——

class C:
  RESET = "\033[0m"
  BOLD = "\033[1m"
  DIM = "\033[2m"
  GREEN = "\033[32m"
  YELLOW = "\033[33m"
  CYAN = "\033[36m"
  RED = "\033[31m"
  MAGENTA = "\033[35m"


def _color_enabled() -> bool:
  if os.environ.get("NO_COLOR"):
    return False
  if sys.platform == "win32":
    try:
      import ctypes

      kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
      handle = kernel32.GetStdHandle(-11)
      mode = ctypes.c_uint32()
      if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
      pass
  return sys.stdout.isatty()


USE_COLOR = _color_enabled()


def paint(text: str, *codes: str) -> str:
  if not USE_COLOR or not codes:
    return text
  return "".join(codes) + text + C.RESET


def banner(title: str) -> None:
  line = "─" * max(40, len(title) + 4)
  print()
  print(paint(line, C.DIM))
  print(paint(f"  {title}", C.BOLD, C.CYAN))
  print(paint(line, C.DIM))


def ok(msg: str) -> None:
  print(paint("  ✓ ", C.GREEN) + msg)


def warn(msg: str) -> None:
  print(paint("  ! ", C.YELLOW) + msg)


def err(msg: str) -> None:
  print(paint("  ✗ ", C.RED) + msg, file=sys.stderr)


def step(n: int, total: int, msg: str) -> None:
  print(paint(f"\n[{n}/{total}] ", C.BOLD, C.MAGENTA) + msg)


def run(
  cmd: list[str],
  *,
  cwd: Path | None = None,
  check: bool = True,
  capture: bool = False,
) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    cmd,
    cwd=str(cwd) if cwd else None,
    check=check,
    text=True,
    encoding="utf-8",
    errors="replace",
    capture_output=capture,
  )


# —— git install ——

def git_exe() -> str | None:
  return shutil.which("git")


def install_git_windows() -> None:
  winget = shutil.which("winget")
  if winget:
    print("  Trying winget install Git.Git …")
    run(
      [
        winget,
        "install",
        "--id",
        "Git.Git",
        "-e",
        "--source",
        "winget",
        "--accept-package-agreements",
        "--accept-source-agreements",
      ],
      check=False,
    )
    # Refresh PATH for this process (common Git install locations)
    for extra in (
      Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "cmd",
      Path(os.environ.get("LocalAppData", "")) / "Programs" / "Git" / "cmd",
    ):
      if extra.is_dir():
        os.environ["PATH"] = str(extra) + os.pathsep + os.environ.get("PATH", "")
    return

  choco = shutil.which("choco")
  if choco:
    print("  Trying chocolatey install git …")
    run([choco, "install", "git", "-y"], check=False)
    return

  raise RuntimeError(
    "Git is not installed and neither winget nor chocolatey was found.\n"
    "  Install Git from https://git-scm.com/download/win then re-run this script."
  )


def install_git_unix() -> None:
  if shutil.which("brew"):
    print("  Trying brew install git …")
    run(["brew", "install", "git"], check=False)
    return
  if shutil.which("apt-get"):
    print("  Trying apt-get install git …")
    run(["sudo", "apt-get", "update", "-y"], check=False)
    run(["sudo", "apt-get", "install", "-y", "git"], check=False)
    return
  if shutil.which("dnf"):
    print("  Trying dnf install git …")
    run(["sudo", "dnf", "install", "-y", "git"], check=False)
    return
  raise RuntimeError(
    "Git is not installed. Install it with your package manager, then re-run.\n"
    "  e.g. sudo apt install git   or   brew install git"
  )


def ensure_git() -> str:
  found = git_exe()
  if found:
    ver = run([found, "--version"], capture=True, check=False)
    ok(f"Git ready — {(ver.stdout or ver.stderr or found).strip()}")
    return found

  warn("Git not found on PATH — installing…")
  if sys.platform == "win32":
    install_git_windows()
  else:
    install_git_unix()

  found = git_exe()
  if not found:
    raise RuntimeError(
      "Git was installed but is still not on PATH.\n"
      "  Close this terminal, open a new one, and run the script again."
    )
  ver = run([found, "--version"], capture=True, check=False)
  ok(f"Git installed — {(ver.stdout or found).strip()}")
  return found


# —— clone / pull ——

def default_github_root() -> Path:
  home = Path.home()
  return home / "GitHub"


def repo_remote_url(prefer_ssh: bool) -> str:
  return REPO_SSH if prefer_ssh else REPO_HTTPS


def ensure_repo(git: str, dest: Path, *, prefer_ssh: bool) -> None:
  dest.parent.mkdir(parents=True, exist_ok=True)
  git_dir = dest / ".git"

  if git_dir.is_dir():
    ok(f"Repo already present: {dest}")
    print("  Fetching origin…")
    run([git, "fetch", "origin", "--prune"], cwd=dest)
    # Detect current branch
    br = run([git, "rev-parse", "--abbrev-ref", "HEAD"], cwd=dest, capture=True)
    branch = (br.stdout or DEFAULT_BRANCH).strip() or DEFAULT_BRANCH
    print(f"  Pulling latest on branch {paint(branch, C.BOLD)}…")
    result = run(
      [git, "pull", "--ff-only", "origin", branch],
      cwd=dest,
      check=False,
      capture=True,
    )
    out = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
      warn("Fast-forward pull failed — trying merge pull…")
      result = run(
        [git, "pull", "origin", branch],
        cwd=dest,
        check=False,
        capture=True,
      )
      out = ((result.stdout or "") + (result.stderr or "")).strip()
      if result.returncode != 0:
        err(out or "git pull failed")
        raise RuntimeError(
          "Could not pull. You may have local changes — commit/stash them, then retry."
        )
    for line in out.splitlines() or ["Already up to date."]:
      print(f"    {line}")
    ok("Pull finished.")
    return

  url = repo_remote_url(prefer_ssh)
  print(f"  Cloning {paint(url, C.CYAN)}")
  print(f"       → {paint(str(dest), C.DIM)}")
  result = run(
    [git, "clone", "--branch", DEFAULT_BRANCH, url, str(dest)],
    check=False,
    capture=True,
  )
  if result.returncode != 0 and prefer_ssh:
    warn("SSH clone failed — retrying with HTTPS…")
    result = run(
      [git, "clone", "--branch", DEFAULT_BRANCH, REPO_HTTPS, str(dest)],
      check=False,
      capture=True,
    )
  if result.returncode != 0:
    err(((result.stdout or "") + (result.stderr or "")).strip())
    raise RuntimeError("git clone failed.")
  ok("Clone finished.")


def show_log(git: str, dest: Path, count: int) -> None:
  banner(f"Recent commits — {REPO_NAME}")
  fmt = "%C(yellow)%h%Creset  %C(green)%ad%Creset  %C(bold)%s%Creset%n         %C(dim)%an%Creset"
  result = run(
    [
      git,
      "log",
      f"-n{count}",
      "--date=short",
      f"--pretty=format:{fmt}",
    ],
    cwd=dest,
    capture=True,
    check=False,
  )
  text = (result.stdout or "").rstrip()
  if not text:
    warn("No commits to show.")
    return
  # git already colorizes when pretty uses %C — force color for pipes on some builds
  if not USE_COLOR:
    # strip common ANSI if we disabled color but format still emitted codes
    import re

    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
  print(text)
  print()
  status = run([git, "status", "-sb"], cwd=dest, capture=True, check=False)
  branch_line = (status.stdout or "").strip().splitlines()[:1]
  if branch_line:
    print(paint("  branch  ", C.DIM) + branch_line[0])
  print(paint("  folder  ", C.DIM) + str(dest))
  print()


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(
    description=f"Install Git if needed and pull latest {REPO_NAME} into ~/GitHub.",
  )
  parser.add_argument(
    "--dir",
    type=Path,
    default=None,
    help="Parent folder for the repo (default: USERPROFILE/GitHub or ~/GitHub)",
  )
  parser.add_argument(
    "--ssh",
    action="store_true",
    help="Prefer SSH remote (git@github.com:…). Default is HTTPS.",
  )
  parser.add_argument(
    "--log",
    type=int,
    default=LOG_COUNT,
    help=f"How many commits to show (default: {LOG_COUNT})",
  )
  args = parser.parse_args(argv)

  banner("QLU Newsletter Tools — update")
  print(paint(f"  Target repo  ", C.DIM) + REPO_NAME)
  root = (args.dir or default_github_root()).expanduser().resolve()
  dest = root / REPO_NAME
  print(paint(f"  GitHub folder ", C.DIM) + str(root))

  try:
    step(1, 3, "Ensure Git is installed")
    git = ensure_git()

    step(2, 3, "Clone or pull latest tools repository")
    ensure_repo(git, dest, prefer_ssh=bool(args.ssh))

    step(3, 3, "Show recent history")
    show_log(git, dest, max(1, args.log))

    print(paint("Done.", C.BOLD, C.GREEN))
    print(f"  Open: {dest}")
    print(f"  UI:   python serve.py   (from that folder)")
    print()
    return 0
  except (RuntimeError, OSError, subprocess.CalledProcessError) as e:
    err(str(e))
    return 1


if __name__ == "__main__":
  raise SystemExit(main())
