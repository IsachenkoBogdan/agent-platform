from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

try:
    from scripts.load_reporting import (
        LoadMetrics,
        LoadThreshold,
        build_report_payload,
        build_thresholds,
        evaluate_thresholds,
        read_aggregated_metrics,
        render_markdown,
        render_validation_markdown,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from load_reporting import (
        LoadMetrics,
        LoadThreshold,
        build_report_payload,
        build_thresholds,
        evaluate_thresholds,
        read_aggregated_metrics,
        render_markdown,
        render_validation_markdown,
    )

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = ROOT / "artifacts" / "load"


@dataclass(frozen=True, slots=True)
class ProfileRun:
    name: str
    users: int
    spawn_rate: int
    duration: str


@dataclass(slots=True)
class ManagedProcess:
    name: str
    process: subprocess.Popen[bytes]
    handle: object


PROFILES = (
    ProfileRun(name="normal", users=20, spawn_rate=5, duration="15s"),
    ProfileRun(name="slow", users=15, spawn_rate=5, duration="15s"),
    ProfileRun(name="failing", users=10, spawn_rate=3, duration="12s"),
    ProfileRun(name="failover", users=20, spawn_rate=6, duration="20s"),
    ProfileRun(name="spike", users=30, spawn_rate=10, duration="30s"),
)

DEFAULT_THRESHOLDS: dict[str, LoadThreshold] = {
    "normal": LoadThreshold(max_failure_pct=1.0, max_p95_ms=800.0),
    "slow": LoadThreshold(max_failure_pct=5.0, max_p95_ms=3000.0),
    "failing": LoadThreshold(max_failure_pct=1.0, max_p95_ms=500.0),
    "failover": LoadThreshold(max_failure_pct=3.0, max_p95_ms=1200.0),
    "spike": LoadThreshold(max_failure_pct=5.0, max_p95_ms=3000.0),
}


def main() -> int:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ARTIFACTS_ROOT / f"load_validation_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    processes: list[ManagedProcess] = []
    try:
        processes.append(
            _start_process(
                name="provider-a",
                command=[
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "services.mock_provider.app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "9101",
                ],
                env_overrides={
                    "MOCK_PROVIDER_ID": "provider-a",
                    "MOCK_PROVIDER_BEHAVIOR": "flaky",
                },
                log_path=output_dir / "provider-a.log",
            )
        )
        processes.append(
            _start_process(
                name="provider-b",
                command=[
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "services.mock_provider.app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "9102",
                ],
                env_overrides={
                    "MOCK_PROVIDER_ID": "provider-b",
                    "MOCK_PROVIDER_BEHAVIOR": "stable",
                },
                log_path=output_dir / "provider-b.log",
            )
        )

        providers_json = json.dumps(
            [
                {
                    "provider_id": "provider-a",
                    "provider_name": "Provider A",
                    "base_url": "http://127.0.0.1:9101/v1",
                    "supported_models": ["gpt-4o-mini"],
                    "priority": 100,
                    "enabled": True,
                },
                {
                    "provider_id": "provider-b",
                    "provider_name": "Provider B",
                    "base_url": "http://127.0.0.1:9102/v1",
                    "supported_models": ["gpt-4o-mini"],
                    "priority": 200,
                    "enabled": True,
                },
            ]
        )
        processes.append(
            _start_process(
                name="gateway",
                command=[
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "services.gateway.app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ],
                env_overrides={
                    "AUTH_TOKENS_CSV": "",
                    "GUARDRAILS_ENABLED": "false",
                    "GATEWAY_SUPPORTED_MODELS_CSV": "gpt-4o-mini,unsupported-load-model",
                    "GATEWAY_PROVIDER_EJECTION_SECONDS": "3",
                    "GATEWAY_PROVIDERS_JSON": providers_json,
                },
                log_path=output_dir / "gateway.log",
            )
        )

        _wait_http_ok("http://127.0.0.1:9101/healthz")
        _wait_http_ok("http://127.0.0.1:9102/healthz")
        _wait_http_ok("http://127.0.0.1:8000/healthz")

        results: list[LoadMetrics] = []
        for profile in PROFILES:
            print(f"Running profile: {profile.name}")
            profile_env = {
                "LOCUST_PROFILE": profile.name,
            }
            if profile.name == "failing":
                profile_env["LOCUST_MODEL_FAILING"] = "unsupported-load-model"

            prefix = output_dir / profile.name
            command = [
                sys.executable,
                "-m",
                "locust",
                "-f",
                str(ROOT / "tests" / "load" / "locustfile.py"),
                "--host",
                "http://127.0.0.1:8000",
                "--headless",
                "-u",
                str(profile.users),
                "-r",
                str(profile.spawn_rate),
                "-t",
                profile.duration,
                "--only-summary",
                "--csv",
                str(prefix),
            ]
            log_path = output_dir / f"{profile.name}.locust.log"
            with log_path.open("wb") as log_handle:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    env={**os.environ, **profile_env},
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            if completed.returncode != 0:
                raise RuntimeError(f"Locust failed for profile={profile.name}")
            metrics = read_aggregated_metrics(
                profile.name, prefix.with_name(f"{profile.name}_stats.csv")
            )
            results.append(metrics)

        thresholds = build_thresholds(DEFAULT_THRESHOLDS, env=os.environ)
        violations = evaluate_thresholds(results, thresholds)

        summary_markdown = render_markdown(results) + "\n" + render_validation_markdown(violations)
        summary_path = output_dir / "summary.md"
        summary_path.write_text(summary_markdown, encoding="utf-8")

        summary_payload = build_report_payload(results, thresholds, violations)
        summary_payload["generated_at_utc"] = datetime.now(UTC).isoformat()
        summary_json_path = output_dir / "summary.json"
        summary_json_path.write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        latest_md_path = ARTIFACTS_ROOT / "latest-report.md"
        latest_md_path.parent.mkdir(parents=True, exist_ok=True)
        latest_md_path.write_text(summary_markdown, encoding="utf-8")

        latest_json_path = ARTIFACTS_ROOT / "latest-report.json"
        latest_json_path.write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"Load validation summary: {summary_path}")
        print(f"Load validation structured report: {summary_json_path}")
        if violations:
            for violation in violations:
                print(f"Validation violation: {violation}")
            return 1
        return 0
    finally:
        _stop_processes(processes)


def _start_process(
    *,
    name: str,
    command: list[str],
    env_overrides: dict[str, str],
    log_path: Path,
) -> ManagedProcess:
    handle = log_path.open("wb")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env={**os.environ, **env_overrides},
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    return ManagedProcess(name=name, process=process, handle=handle)


def _wait_http_ok(url: str, timeout_seconds: float = 20) -> None:
    started = time.monotonic()
    while True:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:  # noqa: S310
                if 200 <= response.status < 300:
                    return
        except Exception:
            pass
        if time.monotonic() - started >= timeout_seconds:
            raise TimeoutError(f"Timed out waiting for {url}")
        time.sleep(0.3)


def _stop_processes(processes: list[ManagedProcess]) -> None:
    for managed in reversed(processes):
        process = managed.process
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        handle = managed.handle
        if hasattr(handle, "close"):
            handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
