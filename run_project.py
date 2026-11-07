
"""Integrated runner for Parts A-D of the Instamart Capstone."""

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from src.data_pipeline import audit, clean_data, validate
from src.customer_models import rfm_and_segments, build_lapse_model
from src.triage import run_pipeline, FEW
from src.policy_rag import PolicyRAG, evaluate
from src.refund_agent import run_agent


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
SCENARIOS = ROOT / "data" / "raw" / "agent_scenarios.csv"


def check_existing():
    """Check existing project artifacts without regenerating them."""

    required_files = [
        ROOT / "data" / "instamart.db",
        ROOT / "data" / "clean" / "customers.csv",
        ROOT / "data" / "clean" / "orders.csv",
        ROOT / "data" / "clean" / "products.csv",
        OUTPUTS / "customer_segments.csv",
        OUTPUTS / "lapse_model.joblib",
        OUTPUTS / "retention_list.csv",
        OUTPUTS / "triage_results.csv",
        OUTPUTS / "triage_budget_demo.csv",
        OUTPUTS / "agent_runs.jsonl",
        OUTPUTS / "refund_ledger.jsonl",
        SCENARIOS,
    ]

    print("\n=== EXISTING ARTIFACT CHECK ===")
    passed = True

    for path in required_files:
        exists = path.is_file()
        print(f"{'PASS' if exists else 'MISSING'}: {path.relative_to(ROOT)}")
        passed = passed and exists

    if passed:
        with SCENARIOS.open("r", encoding="utf-8-sig", newline="") as file:
            scenarios = pd.read_csv(file)

        print(f"\nScenario input rows: {len(scenarios)}")
        print(f"Scenario columns: {list(scenarios.columns)}")

        with (OUTPUTS / "agent_runs.jsonl").open(
            "r", encoding="utf-8"
        ) as file:
            run_records = [
                json.loads(line)
                for line in file
                if line.strip()
            ]

        print(f"Existing agent run records: {len(run_records)}")
        passed = len(scenarios) == 7 and len(run_records) == 7

    print("\nExisting artifact check:", "PASSED" if passed else "FAILED")
    return passed


def run_part_a():
    print("\n=== PART A: DATA FOUNDATION ===")
    audit()
    clean_data()
    validate()


def run_part_b():
    print("\n=== PART B: CUSTOMER SEGMENTS AND LAPSE ===")

    rfm, diagnostics, profile, pca = rfm_and_segments()

    print("\nK-means diagnostics:")
    print(diagnostics.to_string(index=False))

    print("\nSegment profile:")
    print(profile.to_string(index=False))

    print("\nPCA explained variance:", pca)

    print("\nLapse model summary:")
    print(build_lapse_model())


def run_part_c():
    print("\n=== PART C: SUPPORT TICKET TRIAGE ===")

    triage, summary = run_pipeline(
        prompt=FEW,
        token_budget=100000
    )

    print("\nTriage summary:")
    print(summary)

    print("\nSample results:")
    print(triage.head().to_string(index=False))


def extract_refund(result):
    """Read the amount recorded by the refund or escalation tool."""

    amount = 0.0

    for step in result.get("steps", []):
        if step.get("tool") in ("issue_refund", "escalate_to_human"):
            observation = step.get("observation", {})
            amount = float(observation.get("refund_inr", 0.0))

    return round(amount, 2)


def run_part_d():
    print("\n=== PART D: POLICY RAG ===")

    rag = PolicyRAG()
    print("Policy chunks:", len(rag.chunks))

    evaluation = evaluate(rag)
    print("\nPolicy QA evaluation:")
    print(evaluation.to_string(index=False))

    print("\n=== PART D: REFUND AGENT SCENARIOS ===")

    scenarios = pd.read_csv(SCENARIOS)

    if len(scenarios) != 7:
        raise ValueError(
            f"Expected 7 scenarios, found {len(scenarios)}."
        )

    results = []

    for _, scenario in scenarios.iterrows():
        scenario_id = str(scenario["scenario_id"])
        message = str(scenario["message"])
        expected = str(scenario["expected_outcome"]).upper()
        expected_refund = round(
            float(scenario["expected_refund_inr"]), 2
        )

        print(f"\nRunning {scenario_id}...")

        result = run_agent(
            user_message=message,
            scenario_id=scenario_id,
            max_iterations=6,
            token_limit=6000,
            time_limit_seconds=10
        )

        actual = str(result["status"]).upper()
        actual_refund = extract_refund(result)

        outcome_match = (
            actual.startswith("FALLBACK")
            if expected == "FALLBACK"
            else actual == expected
        )

        refund_match = abs(actual_refund - expected_refund) < 0.01
        passed = outcome_match and refund_match

        record = {
            "scenario_id": scenario_id,
            "expected_outcome": expected,
            "actual_outcome": actual,
            "expected_refund_inr": expected_refund,
            "actual_refund_inr": actual_refund,
            "passed": passed,
            "final_answer": result.get("final_answer", ""),
            "llm_calls": result.get("llm_calls", 0),
            "tokens_used": result.get("tokens_used", 0),
            "run_id": result.get("run_id"),
            "steps": result.get("steps", [])
        }

        results.append(record)

        print(
            f"{scenario_id}: expected={expected}, "
            f"actual={actual}, "
            f"refund=INR {actual_refund:.2f}, "
            f"{'PASS' if passed else 'FAIL'}"
        )

    OUTPUTS.mkdir(parents=True, exist_ok=True)

    # This intentionally replaces the previous batch result file.
    with (OUTPUTS / "agent_runs.jsonl").open(
        "w", encoding="utf-8"
    ) as file:
        for record in results:
            file.write(json.dumps(record, default=str) + "\n")

    summary = pd.DataFrame([
        {
            "scenario_id": item["scenario_id"],
            "expected": item["expected_outcome"],
            "actual": item["actual_outcome"],
            "expected_refund": item["expected_refund_inr"],
            "actual_refund": item["actual_refund_inr"],
            "result": "PASS" if item["passed"] else "FAIL"
        }
        for item in results
    ])

    print("\nSeven-scenario acceptance summary:")
    print(summary.to_string(index=False))

    passed_count = sum(item["passed"] for item in results)
    print(f"\nScenarios passed: {passed_count}/7")

    if passed_count != 7:
        print("WARNING: Some refund scenarios did not meet expectations.")
    else:
        print("All seven refund scenarios passed.")


def main():
    parser = argparse.ArgumentParser(
        description="Instamart Intelligence & Support Copilot runner"
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check-only",
        action="store_true",
        help="Check existing artifacts without regenerating them."
    )
    mode.add_argument(
        "--run-all",
        action="store_true",
        help="Execute Parts A, B, C and D."
    )

    args = parser.parse_args()

    if args.check_only:
        if not check_existing():
            raise SystemExit(1)
        return

    print("Starting the complete Instamart project pipeline.")

    run_part_a()
    run_part_b()
    run_part_c()
    run_part_d()

    print("\n=== PROJECT PIPELINE FINISHED ===")
    print("Review outputs/, state/ and data/instamart.db.")


if __name__ == "__main__":
    main()
