"""Launch the Sentinel API, durable worker, and operator console together."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
MINIMUM_NODE_MAJOR = 22


@dataclass(frozen=True)
class Service:
    name: str
    command: list[str]
    cwd: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Sentinel's local control plane and operator console."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate prerequisites without starting any services",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open the operator console after startup",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    npm = validate_prerequisites()
    if args.check:
        print("Sentinel demo prerequisites are ready.")
        return 0

    subprocess.run(  # noqa: S603 - fixed interpreter and module argv
        [sys.executable, "-m", "simulator.bootstrap", "--materialize"],
        cwd=ROOT,
        check=True,
    )
    services = [
        Service("API", [sys.executable, "-m", "api.main"], ROOT),
        Service("worker", [sys.executable, "-m", "runtime.worker"], ROOT),
        Service("console", [npm, "run", "dev"], FRONTEND),
    ]
    processes: list[tuple[Service, subprocess.Popen[bytes]]] = []
    try:
        for service in services:
            process = subprocess.Popen(  # noqa: S603 - validated executable, fixed argv
                service.command,
                cwd=service.cwd,
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                ),
                start_new_session=os.name != "nt",
            )
            processes.append((service, process))
            print(f"Started {service.name:<7} pid={process.pid}")

        wait_until_ready("http://127.0.0.1:8000/healthz", "API")
        wait_until_ready("http://localhost:3000", "console")
        print("\nSentinel is ready: http://localhost:3000")
        print("API documentation: http://127.0.0.1:8000/docs")
        print("Press Ctrl+C to stop every service.\n")
        if not args.no_browser:
            webbrowser.open("http://localhost:3000")

        while all(process.poll() is None for _, process in processes):
            time.sleep(0.5)
        failed = next(
            (service for service, process in processes if process.poll() is not None),
            None,
        )
        if failed is not None:
            print(f"{failed.name} stopped unexpectedly.", file=sys.stderr)
            return 1
        return 0
    except KeyboardInterrupt:
        print("\nStopping Sentinel...")
        return 0
    finally:
        stop_processes(processes)


def validate_prerequisites() -> str:
    required_modules = ("fastapi", "langchain", "langgraph", "sqlalchemy", "uvicorn")
    missing: list[str] = []
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        raise SystemExit(
            "Missing Python dependencies. Run: python -m pip install -e \".[dev]\""
        )

    node = shutil.which("node")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if node is None or npm is None:
        raise SystemExit("Node.js 22.13+ and npm are required for the operator console.")
    completed = subprocess.run(  # noqa: S603 - resolved executable, version-only argv
        [node, "--version"], capture_output=True, check=True, text=True
    )
    version = completed.stdout.strip().lstrip("v")
    major_text = version.split(".", maxsplit=1)[0]
    if not major_text.isdigit() or int(major_text) < MINIMUM_NODE_MAJOR:
        raise SystemExit(f"Node.js 22.13+ is required; found {version or 'unknown'}.")
    if not (FRONTEND / "node_modules").is_dir():
        raise SystemExit("Frontend dependencies are missing. Run: cd frontend; npm ci")
    return npm


def wait_until_ready(url: str, name: str, timeout_seconds: float = 45.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):  # noqa: S310 - fixed localhost URL
                return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.5)
    raise RuntimeError(f"{name} did not become ready at {url} within {timeout_seconds:g}s")


def stop_processes(processes: list[tuple[Service, subprocess.Popen[bytes]]]) -> None:
    for _, process in reversed(processes):
        if process.poll() is not None:
            continue
        if os.name == "nt":
            process.terminate()
        else:
            kill_process_group(process.pid, signal.SIGTERM)
    for _, process in reversed(processes):
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                process.kill()
            else:
                kill_process_group(
                    process.pid, getattr(signal, "SIGKILL", signal.SIGTERM)
                )


def kill_process_group(process_id: int, stop_signal: signal.Signals) -> None:
    killpg = getattr(os, "killpg", None)
    if not callable(killpg):
        raise RuntimeError("process-group termination is unavailable on this platform")
    killpg(process_id, stop_signal)


if __name__ == "__main__":
    raise SystemExit(main())
