# Testing Report

## Load Testing

Implemented Locust scenarios in `tests/load/locustfile.py` with profile-based execution:

- `normal` -> regular chat traffic against configured model
- `slow` -> traffic with `simulate_delay_ms` metadata
- `failing` -> traffic against intentionally failing model
- `failover` -> traffic with failure-injection metadata for failover paths
- `spike` -> mixed traffic plus staged concurrency spike shape

### Run Commands

```bash
uv run locust -f tests/load/locustfile.py --host http://127.0.0.1:8000
```

Headless examples:

```bash
LOCUST_PROFILE=normal uv run locust -f tests/load/locustfile.py --host http://127.0.0.1:8000 --headless -u 20 -r 5 -t 2m
```

```bash
LOCUST_PROFILE=spike uv run locust -f tests/load/locustfile.py --host http://127.0.0.1:8000 --headless -t 2m
```

### Metrics to Capture

- throughput (`req/s`)
- latency (`p50`, `p95`, `p99`)
- failure rate per scenario (`chat.normal`, `chat.slow_provider`, `chat.failing_provider`, `chat.failover`)
- failover stability via response distribution and error ratio under `chat.failover`

### Verification Note

Scenario logic is covered with pytest in `tests/integration/test_load_locust.py`.
Operational benchmark numbers should be captured against running local stack (`docker compose up --build`) for final submission artifacts.

## Latest Automated Run

Command:

```bash
uv run python scripts/run_load_validation.py
```

By default this command now performs pass/fail validation with profile-specific thresholds:

- `normal`: max `failure %` = `1.0`, max `p95` = `800ms`
- `slow`: max `failure %` = `5.0`, max `p95` = `3000ms`
- `failing`: max `failure %` = `1.0`, max `p95` = `500ms`
- `failover`: max `failure %` = `3.0`, max `p95` = `1200ms`
- `spike`: max `failure %` = `5.0`, max `p95` = `3000ms`

Thresholds can be overridden via env vars:

- `LOAD_MAX_FAILURE_PCT_<PROFILE>`
- `LOAD_MAX_P95_MS_<PROFILE>`

Artifacts:

- `artifacts/load/load_validation_20260413_020429/`
- `artifacts/load/latest-report.md`
- `artifacts/load/latest-report.json`

Format note:

- Locust raw outputs stay in CSV (`*_stats.csv`, `*_failures.csv`, `*_exceptions.csv`) because this is Locust's native export format.
- For higher-quality downstream consumption, the project also writes normalized JSON report files (`summary.json`, `latest-report.json`).

Summary:

| Profile | Requests | Failures | Failure % | Req/s | Avg ms | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `normal` | 1465 | 0 | 0.00 | 104.58 | 19.34 | 32.00 |
| `slow` | 111 | 0 | 0.00 | 8.00 | 1512.98 | 1500.00 |
| `failing` | 627 | 0 | 0.00 | 56.97 | 8.32 | 5.00 |
| `failover` | 1999 | 0 | 0.00 | 105.13 | 27.87 | 31.00 |
| `spike` | 10949 | 0 | 0.00 | 91.15 | 502.67 | 1900.00 |

Notes:

- In `failing` profile, `503` is treated as expected outcome, so Locust failure count remains `0`.
- `failover` profile stayed stable under injected flaky upstream behavior.
- `spike` profile shows expected tail latency growth (`P95` up to `1900ms`) under staged concurrency surge.
- Automated validation status: `PASS` (threshold checks from `scripts/run_load_validation.py`).
