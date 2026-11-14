#!/usr/bin/env python3
"""
Install Git + Node.js (if needed), clone/pull the latest
quantum-life-university-news into the user's GitHub folder, then start
dev-web.cmd (CMS API + Astro; admin UI is not opened).

Typical paths:
  Windows:  %USERPROFILE%\\GitHub\\quantum-life-university-news
  macOS/Linux: ~/GitHub/quantum-life-university-news

Examples:
  python scripts/pull_latest_news.py
  python scripts/pull_latest_news.py --dir D:\\GitHub
  python scripts/pull_latest_news.py --no-start
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_SSH = "git@github.com:anemdhana/quantum-life-university-news.git"
REPO_HTTPS = "https://github.com/anemdhana/quantum-life-university-news.git"
REPO_NAME = "quantum-life-university-news"
DEFAULT_BRANCH = "main"
LOG_COUNT = 12
DEV_WEB_CMD = "dev-web.cmd"


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


# —— node / npm install ——

def _prepend_path(*dirs: Path) -> None:
  for d in dirs:
    if d.is_dir():
      os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")


def refresh_node_path() -> None:
  """Pick up common Node install dirs after winget/choco/brew."""
  if sys.platform == "win32":
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    _prepend_path(
      pf / "nodejs",
      Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "nodejs",
      Path(os.environ.get("LocalAppData", "")) / "Programs" / "node",
    )
  else:
    _prepend_path(
      Path("/usr/local/bin"),
      Path.home() / ".nvm" / "current" / "bin",
      Path("/opt/homebrew/bin"),
    )


def node_exe() -> str | None:
  return shutil.which("node")


def npm_exe() -> str | None:
  return shutil.which("npm")


def install_node_windows() -> None:
  winget = shutil.which("winget")
  if winget:
    print("  Trying winget install OpenJS.NodeJS.LTS …")
    run(
      [
        winget,
        "install",
        "--id",
        "OpenJS.NodeJS.LTS",
        "-e",
        "--source",
        "winget",
        "--accept-package-agreements",
        "--accept-source-agreements",
      ],
      check=False,
    )
    refresh_node_path()
    return

  choco = shutil.which("choco")
  if choco:
    print("  Trying chocolatey install nodejs-lts …")
    run([choco, "install", "nodejs-lts", "-y"], check=False)
    refresh_node_path()
    return

  raise RuntimeError(
    "Node.js is not installed and neither winget nor chocolatey was found.\n"
    "  Install Node LTS from https://nodejs.org/ then re-run this script."
  )


def install_node_unix() -> None:
  if shutil.which("brew"):
    print("  Trying brew install node …")
    run(["brew", "install", "node"], check=False)
    refresh_node_path()
    return
  if shutil.which("apt-get"):
    print("  Trying apt-get install nodejs npm …")
    run(["sudo", "apt-get", "update", "-y"], check=False)
    run(["sudo", "apt-get", "install", "-y", "nodejs", "npm"], check=False)
    refresh_node_path()
    return
  if shutil.which("dnf"):
    print("  Trying dnf install nodejs npm …")
    run(["sudo", "dnf", "install", "-y", "nodejs", "npm"], check=False)
    refresh_node_path()
    return
  raise RuntimeError(
    "Node.js is not installed. Install it with your package manager, then re-run.\n"
    "  e.g. brew install node   or   sudo apt install nodejs npm"
  )


def ensure_nodejs() -> str:
  found = node_exe()
  if found:
    ver = run([found, "--version"], capture=True, check=False)
    npm = npm_exe() or "npm (missing)"
    ok(f"Node ready — {(ver.stdout or found).strip()}  ·  npm: {npm}")
    if not npm_exe():
      raise RuntimeError(
        "node is on PATH but npm is missing. Reinstall Node.js LTS from https://nodejs.org/"
      )
    return found

  warn("Node.js not found on PATH — installing LTS…")
  if sys.platform == "win32":
    install_node_windows()
  else:
    install_node_unix()

  refresh_node_path()
  found = node_exe()
  if not found:
    raise RuntimeError(
      "Node.js was installed but is still not on PATH.\n"
      "  Close this terminal, open a new one, and run the script again."
    )
  ver = run([found, "--version"], capture=True, check=False)
  ok(f"Node installed — {(ver.stdout or found).strip()}")
  if not npm_exe():
    raise RuntimeError(
      "Node installed but npm is still missing. Open a new terminal and re-run."
    )
  return found


# —— clone / pull ——

def default_github_root() -> Path:
  return Path.home() / "GitHub"


def repo_remote_url(prefer_ssh: bool) -> str:
  return REPO_SSH if prefer_ssh else REPO_HTTPS


def ensure_repo(git: str, dest: Path, *, prefer_ssh: bool) -> None:
  dest.parent.mkdir(parents=True, exist_ok=True)
  git_dir = dest / ".git"

  if git_dir.is_dir():
    ok(f"Repo already present: {dest}")
    print("  Fetching origin…")
    run([git, "fetch", "origin", "--prune"], cwd=dest)
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
  if not USE_COLOR:
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


def launch_dev_web(dest: Path) -> None:
  """Open CMS API + Astro via dev-web.cmd (does not open /admin in the browser)."""
  cmd_path = dest / DEV_WEB_CMD
  if not cmd_path.is_file():
    warn(f"{DEV_WEB_CMD} not found in {dest} — skip launch")
    print("  Start manually:  .\\dev-web.cmd")
    return

  if sys.platform == "win32":
    # New console window; this script can exit
    subprocess.Popen(
      ["cmd.exe", "/c", "start", "QLU News (CMS+Astro)", str(cmd_path)],
      cwd=str(dest),
      close_fds=True,
    )
    ok(f"Started {DEV_WEB_CMD} in a new window")
    print(paint("  CMS API  ", C.DIM) + "http://localhost:3000  (no admin UI)")
    print(paint("  Site     ", C.DIM) + "http://localhost:4321")
    return

  # macOS / Linux: no .cmd — start CMS + Astro in background
  warn(f"{DEV_WEB_CMD} is Windows-only — starting npm run dev:cms + dev:web …")
  subprocess.Popen(
    ["npm", "run", "dev:cms"],
    cwd=str(dest),
    start_new_session=True,
  )
  subprocess.Popen(
    ["npm", "run", "dev:web"],
    cwd=str(dest),
    start_new_session=True,
  )
  ok("Started CMS API + Astro in the background")
  print(paint("  CMS API  ", C.DIM) + "http://localhost:3000  (no admin UI opened)")
  print(paint("  Site     ", C.DIM) + "http://localhost:4321")


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(
    description=(
      f"Install Git + Node.js if needed, pull latest {REPO_NAME}, "
      "then start CMS API + Astro via dev-web.cmd (admin UI not opened)."
    ),
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
  parser.add_argument(
    "--no-start",
    action="store_true",
    help="Pull only — do not launch dev-web.cmd",
  )
  args = parser.parse_args(argv)

  banner("QLU News — update + CMS API + Astro")
  print(paint(f"  Target repo  ", C.DIM) + REPO_NAME)
  root = (args.dir or default_github_root()).expanduser().resolve()
  dest = root / REPO_NAME
  print(paint(f"  GitHub folder ", C.DIM) + str(root))

  total = 4 if args.no_start else 5
  try:
    step(1, total, "Ensure Git is installed")
    git = ensure_git()

    step(2, total, "Ensure Node.js (npm) is installed")
    ensure_nodejs()

    step(3, total, "Clone or pull latest news repository")
    ensure_repo(git, dest, prefer_ssh=bool(args.ssh))

    step(4, total, "Show recent history")
    show_log(git, dest, max(1, args.log))

    if not args.no_start:
      step(5, total, f"Start CMS API + Astro ({DEV_WEB_CMD})")
      launch_dev_web(dest)

    print(paint("Done.", C.BOLD, C.GREEN))
    print(f"  Open: {dest}")
    if args.no_start:
      print(f"  Site: .\\{DEV_WEB_CMD}   (from that folder)")
    print()
    return 0
  except (RuntimeError, OSError, subprocess.CalledProcessError) as e:
    err(str(e))
    return 1


if __name__ == "__main__":
  raise SystemExit(main())
