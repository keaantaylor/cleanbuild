#!/usr/bin/env python3
"""TrueBind verification harness (Windows PowerShell and Linux/macOS).

    python scripts/verify.py --fast      lint, types, unit tests (seconds to minutes)
    python scripts/verify.py --full      everything, against real services (docker)
    python scripts/verify.py --install-tools   fetch gitleaks + Playwright chromium

Run it with the backend virtualenv's Python (truebind-web/backend/.venv), which
has the backend, the engine and the QA tools installed (requirements-dev.txt).

Prints a one-screen summary, writes verify-report.json at the repo root, and
exits non-zero if any step fails. Step logs: .verify/logs/<step>.log.
Quality ratchet and baselines: scripts/quality.json.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "truebind-web" / "backend"
FRONTEND = ROOT / "truebind-web" / "frontend"
ENGINE = ROOT / "bordereaux"
LOGS = ROOT / ".verify" / "logs"
TOOLS = ROOT / ".tools"
QUALITY = json.loads((ROOT / "scripts" / "quality.json").read_text(encoding="utf-8"))
OPENAPI_SNAPSHOT = ROOT / "scripts" / "openapi-snapshot.json"
COMPOSE = ["docker", "compose", "-f", str(ROOT / "docker-compose.test.yml")]
PY = sys.executable
WINDOWS = os.name == "nt"
GITLEAKS_VERSION = "8.28.0"

# Where docker-compose.test.yml exposes each service (host side).
PG_ADMIN = ["exec", "-T", "postgres", "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-c"]
PG_APP = "postgresql+psycopg://truebind_app:truebind-test-only@127.0.0.1:55433/{db}"
E2E_API_PORT, E2E_WEB_PORT = 8765, 3100
READINESS = {
    "mock-oauth2": "http://127.0.0.1:58081/default/.well-known/openid-configuration",
    "minio": "http://127.0.0.1:59000/minio/health/live",
    "mailpit": "http://127.0.0.1:58025/api/v1/info",
    "sftpgo": "http://127.0.0.1:58080/healthz",
    "webhook-receiver": "http://127.0.0.1:58090/health",
}


@dataclass
class Result:
    name: str
    ok: bool
    seconds: float
    detail: str = ""
    metrics: dict[str, object] = field(default_factory=dict)


class StepFailedError(Exception):
    pass


def _exe(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise StepFailedError(f"'{name}' not found on PATH")
    return found


def run(
    step: str,
    cmd: list[str],
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int = 3600,
    check: bool = True,
) -> str:
    """Run a command, tee its output to the step log, return the output."""
    LOGS.mkdir(parents=True, exist_ok=True)
    full_env = {**os.environ, **(env or {})}
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=full_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    with (LOGS / f"{step}.log").open("a", encoding="utf-8") as fh:
        fh.write(f"$ {' '.join(cmd)}  (cwd={cwd})\n{out}\n[exit {proc.returncode}]\n\n")
    if check and proc.returncode != 0:
        tail = "\n".join(out.strip().splitlines()[-15:])
        raise StepFailedError(f"exit {proc.returncode}: {' '.join(cmd[:4])}...\n{tail}")
    return out


def pytest_counts(out: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for n, kind in re.findall(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|deselected)", out):
        counts[kind] = counts.get(kind, 0) + int(n)
    return counts


def pytest_detail(out: str) -> tuple[str, dict[str, object]]:
    c = pytest_counts(out)
    if c.get("xfailed") or c.get("xpassed"):
        raise StepFailedError("xfail/xpass markers are not allowed (anti-cheating rule)")
    return ", ".join(f"{v} {k}" for k, v in c.items()), dict(c)


# ---------------------------------------------------------------- fast steps


def step_ruff() -> tuple[str, dict[str, object]]:
    legacy = [
        "truebind-web/backend/app",
        "truebind-web/backend/tests",
        "truebind-web/backend/migrations",
        "bordereaux/src",
        "bordereaux/tests",
        "scripts",
    ]
    run("ruff", [PY, "-m", "ruff", "check", "--isolated", "--select", "E4,E7,E9,F", "--line-length", "120", *legacy])
    strict = QUALITY["strict_paths"]
    run(
        "ruff",
        [
            PY,
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--target-version",
            "py311",
            "--line-length",
            "120",
            "--select",
            ",".join(QUALITY["strict_ruff_select"]),
            *[a for pfi in QUALITY["strict_per_file_ignores"] for a in ("--per-file-ignores", pfi)],
            *strict,
        ],
    )
    run("ruff", [PY, "-m", "ruff", "format", "--isolated", "--line-length", "120", "--check", *strict])
    return f"legacy ruleset clean; {len(strict)} strict path(s) lint+format clean", {}


def step_mypy() -> tuple[str, dict[str, object]]:
    env = {"MYPYPATH": str(ENGINE / "src")}
    strict = [p for p in QUALITY["strict_paths"] if p.endswith(".py") or (ROOT / p).is_dir()]
    run(
        "mypy", [PY, "-m", "mypy", "--strict", "--ignore-missing-imports", "--explicit-package-bases", *strict], env=env
    )
    out = run(
        "mypy",
        [PY, "-m", "mypy", "--ignore-missing-imports", "app", str(ENGINE / "src" / "bordereaux")],
        cwd=BACKEND,
        env=env,
        check=False,
    )
    m = re.search(r"Found (\d+) errors?", out)
    legacy = int(m.group(1)) if m else 0
    ceiling = int(QUALITY["baseline"]["mypy_legacy_errors"])
    if legacy > ceiling:
        raise StepFailedError(f"legacy mypy errors rose to {legacy} (baseline {ceiling}); fix the new ones")
    return f"strict paths: 0 errors; legacy {legacy}/{ceiling} (ratchet)", {"legacy_errors": legacy}


# Wall-clock assertions: they gate in engine-tests (run WITHOUT coverage);
# the separate coverage-collection run deselects them because line tracing
# slows the code under test, which is not the scenario they measure.
TIMING_SENSITIVE = (
    "tests/test_stray_cell_bounded_scan.py::test_stray_cell_does_not_trigger_unbounded_scan",
    "tests/test_dedupe_scale.py",
)


def step_engine_tests() -> tuple[str, dict[str, object]]:
    out = run("engine-tests", [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=ENGINE)
    return pytest_detail(out)


def _engine_coverage() -> None:
    deselect = [a for t in TIMING_SENSITIVE for a in ("--deselect", t)]
    run(
        "coverage",
        [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests", "--cov=bordereaux", "--cov-report=", *deselect],
        cwd=ENGINE,
        env={"COVERAGE_FILE": str(ROOT / ".verify" / ".coverage.engine")},
    )


def step_backend_tests_sqlite() -> tuple[str, dict[str, object]]:
    out = run(
        "backend-tests",
        [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests", "-m", "not integration"],
        cwd=BACKEND,
        env={"TRUEBIND_TEST_DATABASE_URL": "", "TRUEBIND_IT": ""},
    )
    return pytest_detail(out)


def step_frontend_lint() -> tuple[str, dict[str, object]]:
    npx = _exe("npx")
    run("frontend-lint", [npx, "eslint", "."], cwd=FRONTEND)
    run("frontend-lint", [npx, "tsc", "--noEmit"], cwd=FRONTEND)
    return "eslint + tsc --noEmit clean", {}


def step_vitest() -> tuple[str, dict[str, object]]:
    out = run("vitest", [_exe("npx"), "vitest", "run"], cwd=FRONTEND)
    m = re.search(r"Tests\s+(\d+) passed", out)
    return (f"{m.group(1)} passed" if m else "passed"), {"passed": int(m.group(1)) if m else 0}


# ---------------------------------------------------------------- full steps


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:  # noqa: S310  # nosec B310 (fixed local http URLs)
            return bool(r.status == 200)
    except OSError:
        return False


def step_services_up() -> tuple[str, dict[str, object]]:
    run("services", [*COMPOSE, "up", "-d", "--wait"], timeout=900)
    deadline = time.monotonic() + 180
    pending = dict(READINESS)
    while pending and time.monotonic() < deadline:
        pending = {k: u for k, u in pending.items() if not _http_ok(u)}
        if pending:
            time.sleep(2)
    if pending:
        raise StepFailedError(f"services not ready: {sorted(pending)}")
    for db in ("truebind_test", "truebind_migrations", "truebind_e2e"):
        run("services", [*COMPOSE, *PG_ADMIN, f"DROP DATABASE IF EXISTS {db} WITH (FORCE)"])
        run("services", [*COMPOSE, *PG_ADMIN, f"CREATE DATABASE {db} OWNER truebind_app"])
    return "8 services healthy; test databases recreated empty", {}


def step_migrations() -> tuple[str, dict[str, object]]:
    env = {"DATABASE_URL": PG_APP.format(db="truebind_migrations"), "TRUEBIND_NO_DOTENV": "1", "TRUEBIND_ENV": "test"}
    heads = []
    for args in (["upgrade", "head"], ["downgrade", "-1"], ["upgrade", "head"]):
        run("migrations", [PY, "-m", "alembic", *args], cwd=BACKEND, env=env)
        out = run("migrations", [PY, "-m", "alembic", "current"], cwd=BACKEND, env=env)
        m = re.search(r"^([0-9A-Za-z_]+)( \(head\))?\s*$", out, re.MULTILINE)
        heads.append(m.group(0).strip() if m else "<none>")
    if heads[0] != heads[2] or heads[0] == heads[1] or not heads[2].endswith("(head)"):
        raise StepFailedError(f"round-trip did not return to head: {heads}")
    return f"fresh DB: upgrade -> downgrade -1 ({heads[1]}) -> upgrade ({heads[2]})", {"revisions": heads}


def step_backend_tests_pg() -> tuple[str, dict[str, object]]:
    env = {
        "TRUEBIND_TEST_DATABASE_URL": PG_APP.format(db="truebind_test"),
        "TRUEBIND_IT": "1",
        "COVERAGE_FILE": str(ROOT / ".verify" / ".coverage.backend"),
    }
    out = run(
        "backend-tests-pg",
        [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests", "--cov=app", "--cov=bordereaux", "--cov-report="],
        cwd=BACKEND,
        env=env,
    )
    return pytest_detail(out)


def step_golden() -> tuple[str, dict[str, object]]:
    targets = [str(ENGINE / "tests" / "test_boundary_fixture.py")]
    golden = ROOT / "fixtures" / "golden"
    targets += [str(p) for p in sorted(golden.glob("*/test_*.py"))] if golden.exists() else []
    out = run("golden", [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", *targets], cwd=ROOT)
    detail, metrics = pytest_detail(out)
    return f"{len(targets)} golden suite(s): {detail}", metrics


def step_next_build() -> tuple[str, dict[str, object]]:
    env = {
        "NEXT_PUBLIC_API_URL": "/api/v1",
        "TRUEBIND_API_ORIGIN": f"http://127.0.0.1:{E2E_API_PORT}",
        "NEXT_TELEMETRY_DISABLED": "1",
    }
    run("next-build", [_exe("npx"), "next", "build"], cwd=FRONTEND, env=env, timeout=1200)
    return "production build OK", {}


def step_e2e() -> tuple[str, dict[str, object]]:
    env = {
        "TRUEBIND_PYTHON": PY,
        "E2E_DATABASE_URL": PG_APP.format(db="truebind_e2e"),
        "E2E_API_PORT": str(E2E_API_PORT),
        "E2E_WEB_PORT": str(E2E_WEB_PORT),
    }
    out = run("e2e", [_exe("npx"), "playwright", "test"], cwd=FRONTEND, env=env, timeout=1800)
    m = re.search(r"(\d+) passed", out)
    return (f"{m.group(1)} passed (Postgres)" if m else "passed"), {"passed": int(m.group(1)) if m else 0}


def _gitleaks() -> str:
    local = TOOLS / ("gitleaks.exe" if WINDOWS else "gitleaks")
    return str(local) if local.exists() else _exe("gitleaks")


def step_security() -> tuple[str, dict[str, object]]:
    run("security", [PY, "-m", "pip_audit", "--skip-editable", "--progress-spinner", "off"], timeout=600)
    run("security", [_exe("npm"), "audit", "--audit-level=high"], cwd=FRONTEND, timeout=600)
    run(
        "security",
        [PY, "-m", "bandit", "-ll", "-q", "-r", str(BACKEND / "app"), str(ENGINE / "src"), str(ROOT / "scripts")],
    )
    gl = _gitleaks()
    run("security", [gl, "git", "--no-banner", "--redact", str(ROOT)])
    run("security", [gl, "git", "--no-banner", "--redact", "--pre-commit", str(ROOT)])
    run("security", [gl, "git", "--no-banner", "--redact", "--staged", str(ROOT)])
    return "pip-audit, npm audit (high), bandit -ll, gitleaks (history + uncommitted): clean", {}


def _changed_lines() -> dict[str, set[int]]:
    """Added/modified line numbers per file versus the merge-base with origin/main."""
    base = run("coverage", ["git", "merge-base", "HEAD", "origin/main"], check=False).strip().splitlines()
    ref = base[-1] if base and re.fullmatch(r"[0-9a-f]{40}", base[-1]) else "HEAD"
    diff = run("coverage", ["git", "diff", "--unified=0", ref, "--", "truebind-web/backend/app", "bordereaux/src"])
    changed: dict[str, set[int]] = {}
    current = ""
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = str((ROOT / line[6:]).resolve())
        elif line.startswith("@@") and current:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if m:
                start, count = int(m.group(1)), int(m.group(2) or 1)
                changed.setdefault(current, set()).update(range(start, start + count))
    return changed


def step_coverage() -> tuple[str, dict[str, object]]:
    _engine_coverage()
    data = ROOT / ".verify"
    env = {"COVERAGE_FILE": str(data / ".coverage")}
    parts = [str(p) for p in (data / ".coverage.engine", data / ".coverage.backend") if p.exists()]
    run("coverage", [PY, "-m", "coverage", "combine", "--keep", *parts], env=env)
    report = data / "coverage.json"
    run("coverage", [PY, "-m", "coverage", "json", "-o", str(report)], env=env)
    cov = json.loads(report.read_text(encoding="utf-8"))
    total = round(float(cov["totals"]["percent_covered"]), 2)
    baseline = QUALITY["baseline"]["coverage_total_pct"]
    if baseline is not None and total + 0.01 < float(baseline):
        raise StepFailedError(f"total coverage {total}% fell below the baseline {baseline}%")
    covered = executable = 0
    for path, lines in _changed_lines().items():
        f = cov["files"].get(path) or next(
            (v for k, v in cov["files"].items() if Path(k).resolve() == Path(path)), None
        )
        if f is None:
            continue
        exe = (set(f["executed_lines"]) | set(f["missing_lines"])) & lines
        executable += len(exe)
        covered += len(exe & set(f["executed_lines"]))
    new_pct = round(100.0 * covered / executable, 2) if executable else None
    minimum = float(QUALITY["new_code_coverage_min_pct"])
    if new_pct is not None and new_pct < minimum:
        raise StepFailedError(f"new/changed code coverage {new_pct}% < {minimum}% ({covered}/{executable} lines)")
    new_txt = f"{new_pct}% of {executable} changed lines" if new_pct is not None else "no changed executable lines"
    return (
        f"total {total}% (baseline {baseline}); new code {new_txt}",
        {"total_pct": total, "baseline_pct": baseline, "new_code_pct": new_pct, "new_code_lines": executable},
    )


def _openapi() -> dict[str, object]:
    code = (
        "import json,os,sys;sys.path.insert(0,'.');os.environ.setdefault('TRUEBIND_NO_DOTENV','1');"
        "os.environ.setdefault('TRUEBIND_ENV','test');os.environ.setdefault('DATABASE_URL','sqlite://');"
        "from app.main import app;print(json.dumps(app.openapi(),sort_keys=True))"
    )
    out = run("openapi", [PY, "-c", code], cwd=BACKEND)
    doc: dict[str, object] = json.loads(out.strip().splitlines()[-1])
    return doc


def _operations(doc: dict[str, object]) -> set[str]:
    paths = doc.get("paths", {})
    assert isinstance(paths, dict)  # noqa: S101 (shape of the OpenAPI document)
    return {f"{m.upper()} {p}" for p, ops in paths.items() for m in ops if m != "parameters"}


def step_openapi(update: bool) -> tuple[str, dict[str, object]]:
    current = _openapi()
    if update or not OPENAPI_SNAPSHOT.exists():
        OPENAPI_SNAPSHOT.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return f"snapshot written ({len(_operations(current))} operations)", {"updated": True}
    snap = json.loads(OPENAPI_SNAPSHOT.read_text(encoding="utf-8"))
    if snap == current:
        return f"matches snapshot ({len(_operations(current))} operations)", {}
    removed = sorted(_operations(snap) - _operations(current))
    added = sorted(_operations(current) - _operations(snap))
    kind = "BREAKING (operations removed)" if removed else "changed (additive or schema-level)"
    raise StepFailedError(
        f"API contract {kind}. removed={removed[:8]} added={added[:8]}. If intentional, note it in PROGRESS.md "
        "and re-run with --update-openapi to accept the new snapshot."
    )


# ---------------------------------------------------------------- driver


def install_tools() -> None:
    TOOLS.mkdir(exist_ok=True)
    system, machine = platform.system().lower(), platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    osname = {"windows": "windows", "darwin": "darwin"}.get(system, "linux")
    ext = "zip" if osname == "windows" else "tar.gz"
    url = (
        f"https://github.com/gitleaks/gitleaks/releases/download/v{GITLEAKS_VERSION}/"
        f"gitleaks_{GITLEAKS_VERSION}_{osname}_{arch}.{ext}"
    )
    archive = TOOLS / f"gitleaks.{ext}"
    urllib.request.urlretrieve(url, archive)  # nosec B310 (pinned https GitHub release URL)
    if ext == "zip":
        with zipfile.ZipFile(archive) as z:
            z.extract("gitleaks.exe", TOOLS)
    else:
        with tarfile.open(archive) as t:
            t.extract("gitleaks", TOOLS, filter="data")
    archive.unlink()
    print(f"gitleaks {GITLEAKS_VERSION} -> {TOOLS}")
    if not os.environ.get("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"):
        subprocess.run([_exe("npx"), "playwright", "install", "chromium"], cwd=FRONTEND, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fast", action="store_true")
    mode.add_argument("--full", action="store_true")
    mode.add_argument("--install-tools", action="store_true")
    ap.add_argument("--keep-services", action="store_true", help="leave docker services running after --full")
    ap.add_argument("--update-openapi", action="store_true", help="accept the current API as the new snapshot")
    ap.add_argument("--only", help="comma-separated step names to run (debugging); the report marks it partial")
    args = ap.parse_args()
    if args.install_tools:
        install_tools()
        return 0

    shutil.rmtree(LOGS, ignore_errors=True)
    for stale in (ROOT / ".verify").glob(".coverage*"):
        stale.unlink()
    full = bool(args.full)
    steps: list[tuple[str, Callable[[], tuple[str, dict[str, object]]]]] = [
        ("ruff", step_ruff),
        ("mypy", step_mypy),
        ("engine-tests", step_engine_tests),
        ("frontend-lint", step_frontend_lint),
        ("vitest", step_vitest),
    ]
    if full:
        steps += [
            ("services", step_services_up),
            ("migrations", step_migrations),
            ("backend-tests-pg", step_backend_tests_pg),
            ("golden", step_golden),
            ("next-build", step_next_build),
            ("e2e", step_e2e),
            ("security", step_security),
            ("coverage", step_coverage),
            ("openapi", lambda: step_openapi(args.update_openapi)),
        ]
    else:
        steps.insert(3, ("backend-tests", step_backend_tests_sqlite))
    only = set(args.only.split(",")) if args.only else None

    results: list[Result] = []
    started = time.monotonic()
    try:
        for name, fn in steps:
            if only and name not in only:
                continue
            print(f"-> {name} ...", flush=True)
            t0 = time.monotonic()
            try:
                detail, metrics = fn()
                results.append(Result(name, True, time.monotonic() - t0, detail, metrics))
            except (StepFailedError, subprocess.TimeoutExpired, OSError) as exc:
                results.append(Result(name, False, time.monotonic() - t0, str(exc)))
                if name == "services":
                    break  # nothing after this can run meaningfully
    finally:
        if full and not args.keep_services and (not only or "services" in only):
            run("services", [*COMPOSE, "down", "-v"], check=False, timeout=300)

    all_ok = all(r.ok for r in results)
    ok = all_ok and not only  # a partial run is never a green verify
    status = "PASS" if ok else ("PARTIAL" if all_ok else "FAIL")
    width = max(len(r.name) for r in results) if results else 10
    print("\n" + "=" * 100)
    print(
        f" TrueBind verify --{'full' if full else 'fast'}   {status}"
        f"{'  (partial: --only)' if only else ''}   {time.monotonic() - started:.0f}s"
    )
    print("=" * 100)
    for r in results:
        first = r.detail.splitlines()[0] if r.detail else ""
        print(f" {'OK  ' if r.ok else 'FAIL'}  {r.name:<{width}}  {r.seconds:7.1f}s  {first[:70]}")
    print("=" * 100)
    for r in results:
        if not r.ok:
            print(f"\n[{r.name}] {r.detail}\n  log: {LOGS / (r.name + '.log')}")

    sha = run("git", ["git", "rev-parse", "HEAD"], check=False).strip().splitlines()
    dirty = bool(run("git", ["git", "status", "--porcelain"], check=False).strip())
    (ROOT / "verify-report.json").write_text(
        json.dumps(
            {
                "mode": "full" if full else "fast",
                "passed": ok,
                "partial": bool(only),
                "git_sha": sha[-1] if sha else None,
                "dirty_worktree": dirty,
                "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "steps": [
                    {
                        "name": r.name,
                        "ok": r.ok,
                        "seconds": round(r.seconds, 1),
                        "detail": r.detail,
                        "metrics": r.metrics,
                    }
                    for r in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
