from __future__ import annotations

import argparse
from pathlib import Path

from evaluation.runner import RESULTS_DIR, run_scenario


SENTINEL_SCENARIOS = ("sentinel-a", "sentinel-b", "sentinel-c", "sentinel-d")
BLAST_SCENARIOS = ("blast-01", "blast-02", "blast-03")
SCENARIOS = SENTINEL_SCENARIOS + BLAST_SCENARIOS


def main() -> int:
    parser = argparse.ArgumentParser(description="TopoAI independent adversarial evaluation harness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run one real Kubernetes Sentinel")
    run.add_argument("scenario", choices=SCENARIOS)
    run.add_argument("--context")
    run.add_argument("--timeout", type=float, default=240.0)
    run.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    run.add_argument("--forensic-output-dir", type=Path)
    run_all = subparsers.add_parser("run-all", help="Run all four Sentinels sequentially")
    run_all.add_argument("--context")
    run_all.add_argument("--timeout", type=float, default=240.0)
    run_all.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    run_all.add_argument("--forensic-output-dir", type=Path)
    run_blast = subparsers.add_parser(
        "run-blast",
        help="Run Sentinel D plus the three permanent BR-0 scenarios sequentially",
    )
    run_blast.add_argument("--context")
    run_blast.add_argument("--timeout", type=float, default=240.0)
    run_blast.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    run_blast.add_argument("--forensic-output-dir", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "run-all":
        scenarios = SENTINEL_SCENARIOS
    elif arguments.command == "run-blast":
        scenarios = ("sentinel-d",) + BLAST_SCENARIOS
    else:
        scenarios = (arguments.scenario,)
    exit_code = 0
    for scenario in scenarios:
        result, path = run_scenario(
            scenario,
            context=arguments.context,
            timeout_seconds=arguments.timeout,
            output_dir=arguments.output_dir,
            forensic_output_dir=arguments.forensic_output_dir,
        )
        print(f"{scenario}: {result.overall_status.value} -> {path}")
        if result.overall_status.value in {"HARNESS_ERROR", "INCONCLUSIVE"}:
            exit_code = 2
        elif result.overall_status.value == "FAIL" and exit_code == 0:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

