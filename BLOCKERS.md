# Blockers

Open items that stopped or limited a task. Each: what failed, what was tried, hypothesis, what unblocks it.

## B1 — verify.py not executed on Windows (open, non-blocking)
- **What**: the harness is written to be cross-platform (pure Python driver, `shutil.which` resolves `npx.cmd`/`npm.cmd`, pathlib, Windows gitleaks zip in `--install-tools`), but this build environment is Linux only, so it has never been run under PowerShell.
- **Risk**: path quoting in the Playwright `webServer` command (`"<python>" -m ...`) and Docker Desktop's compose `--wait` behaviour.
- **Unblock**: run `python scripts\verify.py --fast` then `--full` once on a Windows machine with Docker Desktop; log results here.
