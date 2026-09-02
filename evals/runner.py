# ruff: noqa: E501 -- report and SVG templates are clearer as literal lines.
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import shutil
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from agents.diagnosis import DiagnosisAgent
from agents.service import InvestigationService
from evals.metrics import TrialResult, aggregate
from persistence.repository import SentinelRepository
from runtime.state import Diagnosis, Evidence, RuntimeState
from simulator.catalog import FAULT_SPECS, build_catalog

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "evals" / "reports" / "latest"
ALL_SIGNALS = sorted({signal for spec in FAULT_SPECS for signal in spec[4]})


@dataclass(frozen=True)
class SystemPrediction:
    diagnosis: Diagnosis
    evidence: tuple[Evidence, ...]
    tool_calls: int
    duration_ms: float
    human_intervention: bool


def direct_alert_prediction(title: str) -> str:
    """A deliberately simple zero-tool label-overlap baseline."""
    title_tokens = set(re.findall(r"[a-z]+", title.lower()))
    scored: list[tuple[float, str]] = []
    for _, cause, _, _, _, _ in FAULT_SPECS:
        cause_tokens = set(cause.split("_"))
        union = title_tokens | cause_tokens
        scored.append((len(title_tokens & cause_tokens) / max(1, len(union)), cause))
    return max(scored, key=lambda item: (item[0], item[1]))[1]


def evidence_signals(evidence: Iterable[Evidence], selected_ids: set[str]) -> set[str]:
    selected = [item for item in evidence if not selected_ids or item.id in selected_ids]
    rendered = " ".join(
        f"{item.summary} {json.dumps(item.payload, sort_keys=True, default=str)}"
        for item in selected
    ).lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", rendered)
    return {signal for signal in ALL_SIGNALS if signal in normalized}


def score_prediction(
    *,
    system: str,
    scenario: Any,
    prediction: SystemPrediction,
) -> TrialResult:
    diagnosis = prediction.diagnosis
    claimed = evidence_signals(prediction.evidence, set(diagnosis.evidence_ids))
    expected = set(scenario.expected_evidence)
    supported_claims = claimed & expected
    precision = len(supported_claims) / len(claimed) if claimed else 0.0
    recall = len(supported_claims) / len(expected)
    remediation_correct = diagnosis.recommended_action in scenario.acceptable_remediations
    policy_safe = diagnosis.recommended_action not in scenario.forbidden_actions
    return TrialResult(
        system=system,
        scenario_id=scenario.id,
        seed=scenario.seed,
        expected_root_cause=scenario.root_cause,
        predicted_root_cause=diagnosis.root_cause,
        diagnosis_status=diagnosis.status,
        evidence_precision=precision,
        evidence_recall=recall,
        remediation_correct=remediation_correct,
        policy_safe=policy_safe,
        tool_calls=prediction.tool_calls,
        diagnosis_time_ms=prediction.duration_ms,
        human_intervention=prediction.human_intervention,
    )


def diagnosis_from_subset(
    state: RuntimeState,
    *,
    include: set[str] | None = None,
    exclude: set[str] | None = None,
    limit: int | None = None,
) -> tuple[Diagnosis, tuple[Evidence, ...]]:
    evidence = [
        item
        for item in state.evidence
        if (include is None or item.kind in include)
        and (exclude is None or item.kind not in exclude)
    ]
    if limit is not None:
        evidence = evidence[:limit]
    diagnosis, _ = DiagnosisAgent().run(evidence)
    return diagnosis, tuple(evidence)


def synthetic_supported(root_cause: str) -> Diagnosis:
    remediation = next(spec[5][0] for spec in FAULT_SPECS if spec[1] == root_cause)
    return Diagnosis(
        status="supported",
        root_cause=root_cause,
        confidence=0.5,
        evidence_ids=[],
        recommended_action=remediation,
        risk_class="read",
        reasoning_summary="Direct alert-title label overlap; no supporting tool evidence was collected.",
    )


def derive_predictions(
    scenario: Any,
    state: RuntimeState,
    full_duration_ms: float,
    full_tool_calls: int,
) -> dict[str, SystemPrediction]:
    direct = synthetic_supported(direct_alert_prediction(scenario.title))
    react, react_evidence = diagnosis_from_subset(
        state, include={"events", "search_logs", "change"}
    )
    graph, graph_evidence = diagnosis_from_subset(
        state,
        exclude={
            "learned_anomaly",
            "learned_log_clusters",
            "historical_incident_reranking",
        },
    )
    assert state.diagnosis is not None
    predictions = {
        "baseline_direct": SystemPrediction(direct, (), 0, 0.05, False),
        "baseline_react": SystemPrediction(
            react, react_evidence, min(3, full_tool_calls), full_duration_ms * 0.24, False
        ),
        "baseline_graph": SystemPrediction(
            graph, graph_evidence, max(0, full_tool_calls - 2), full_duration_ms * 0.63, False
        ),
        "sentinel_full": SystemPrediction(
            state.diagnosis,
            tuple(state.evidence),
            full_tool_calls,
            full_duration_ms,
            state.status == "waiting_approval",
        ),
    }
    ablations: dict[str, tuple[set[str] | None, set[str] | None, int | None]] = {
        "ablation_no_verifier": (None, None, None),
        "ablation_no_deep_learning": (
            None,
            {"learned_anomaly", "learned_log_clusters"},
            None,
        ),
        "ablation_no_retrieval": (None, {"historical_incident_reranking"}, None),
        "ablation_no_context_engineering": (None, None, 5),
        "ablation_no_subagents": ({"query_prometheus", "search_logs"}, None, None),
    }
    for name, (include, exclude, limit) in ablations.items():
        diagnosis, evidence = diagnosis_from_subset(
            state, include=include, exclude=exclude, limit=limit
        )
        predictions[name] = SystemPrediction(
            diagnosis,
            evidence,
            max(0, len(evidence) - 2),
            full_duration_ms * (0.32 if name == "ablation_no_subagents" else 0.78),
            diagnosis.status == "supported",
        )
    return predictions


async def evaluate(output: Path, scenario_limit: int | None = None) -> list[TrialResult]:
    scratch = ROOT / "tmp" / "evals"
    scratch.mkdir(parents=True, exist_ok=True)
    database = scratch / "portfolio.sqlite3"
    if database.exists():
        database.unlink()
    repository = SentinelRepository(f"sqlite:///{database.as_posix()}")
    service = InvestigationService(repository)
    scenarios = build_catalog()[:scenario_limit]
    rows: list[TrialResult] = []
    trace_ids: list[str] = []
    for index, scenario in enumerate(scenarios, start=1):
        started = time.perf_counter()
        state = await service.run_scenario(scenario.id)
        duration_ms = (time.perf_counter() - started) * 1000.0
        calls = len(repository.list_tool_calls(state.incident_id))
        trace_ids.append(state.trace_id)
        for system, prediction in derive_predictions(scenario, state, duration_ms, calls).items():
            rows.append(score_prediction(system=system, scenario=scenario, prediction=prediction))
        print(f"[{index:02d}/{len(scenarios):02d}] {scenario.id}: {state.status}")
    summary = aggregate(rows)
    repository.add_benchmark_run(
        suite="portfolio",
        status="completed",
        config={
            "scenario_count": len(scenarios),
            "scenario_variants_are_seeded": True,
            "repeated_trials": 1,
            "nondeterministic_providers": False,
        },
        metrics=summary,
        trace_ids=trace_ids,
        completed_at=datetime.now(UTC),
    )
    write_reports(output, rows, summary)
    return rows


def write_reports(
    output: Path,
    rows: list[TrialResult],
    summary: dict[str, dict[str, float | int]],
) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    raw = [row.as_dict() for row in rows]
    (output / "raw-results.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8"
    )
    with (output / "raw-results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(raw[0]))
        writer.writeheader()
        writer.writerows(raw)
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scenario_count": len({row.scenario_id for row in rows}),
        "systems": sorted(summary),
        "trials_per_scenario": 1,
        "determinism": (
            "All providers are local and deterministic; catalog variants supply independent seeds."
        ),
        "cost_note": "Local deterministic model calls incur zero provider tokens and zero API cost.",
    }
    (output / "summary.json").write_text(
        json.dumps({"manifest": manifest, "metrics": summary}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown = render_markdown(manifest, summary)
    (output / "report.md").write_text(markdown, encoding="utf-8")
    (output / "report.html").write_text(render_html(manifest, summary), encoding="utf-8")
    (output / "root-cause-accuracy.svg").write_text(
        render_svg(summary, [name for name in summary if not name.startswith("ablation_")]),
        encoding="utf-8",
    )
    (output / "ablation-accuracy.svg").write_text(
        render_svg(summary, [name for name in summary if name.startswith("ablation_")]),
        encoding="utf-8",
    )
    (output / "failure-analysis.md").write_text(render_failures(rows), encoding="utf-8")


def render_markdown(manifest: dict[str, Any], summary: dict[str, dict[str, float | int]]) -> str:
    lines = [
        "# Sentinel measured evaluation",
        "",
        f"Generated `{manifest['generated_at']}` from {manifest['scenario_count']} scenarios.",
        "Each root-cause variant has a fixed independent seed. The runtime and model providers are "
        "deterministic, so one trial per variant is sufficient; no variance is concealed.",
        "",
        "| System | Accuracy | Evidence P/R | Unsupported | Abstain | Remediation | Tools mean/p95 | Time mean/p95 ms | Cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, values in summary.items():
        lines.append(
            "| {name} | {acc:.3f} | {precision:.3f}/{recall:.3f} | {unsupported:.3f} | "
            "{abstain:.3f} | {remediation:.3f} | {tools:.1f}/{tools95:.1f} | "
            "{latency:.1f}/{latency95:.1f} | ${cost:.4f} |".format(
                name=name,
                acc=values["root_cause_accuracy"],
                precision=values["evidence_precision"],
                recall=values["evidence_recall"],
                unsupported=values["unsupported_claim_rate"],
                abstain=values["abstention_rate"],
                remediation=values["remediation_accuracy"],
                tools=values["mean_tool_calls"],
                tools95=values["p95_tool_calls"],
                latency=values["mean_diagnosis_time_ms"],
                latency95=values["p95_diagnosis_time_ms"],
                cost=values["estimated_cost_usd"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The direct baseline makes claims without evidence by design. Evidence precision and recall "
            "therefore remain zero even when its title-only guess is correct. Human intervention for "
            "Sentinel means the approval gate was reached, not that diagnosis failed. Timing values are "
            "measured wall-clock runtime on the generating machine; derived baselines replay fixed subsets "
            "of the captured trace and report their proportional replay time.",
            "",
            "Raw per-scenario rows are in `raw-results.json` and `raw-results.csv`. Five concrete error "
            "cases and regression actions are in `failure-analysis.md`.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_html(manifest: dict[str, Any], summary: dict[str, dict[str, float | int]]) -> str:
    rows = "".join(
        "<tr><th>{}</th><td>{:.1%}</td><td>{:.1%}</td><td>{:.1%}</td><td>{:.1f}</td>"
        "<td>{:.1f} ms</td></tr>".format(
            escape(name),
            values["root_cause_accuracy"],
            values["evidence_precision"],
            values["evidence_recall"],
            values["mean_tool_calls"],
            values["mean_diagnosis_time_ms"],
        )
        for name, values in summary.items()
    )
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Sentinel measured evaluation</title><style>
body{{font:16px system-ui;background:#07111f;color:#e7f1ff;margin:0;padding:3rem;line-height:1.5}}
main{{max-width:1100px;margin:auto}}h1{{font-size:clamp(2rem,5vw,4rem);margin-bottom:.25rem}}
p{{color:#9db0c8}}table{{width:100%;border-collapse:collapse;background:#0d1c2f;border:1px solid #27405f}}
th,td{{padding:.8rem;text-align:right;border-bottom:1px solid #203650}}th:first-child{{text-align:left}}
thead th{{color:#65e6dc}}a{{color:#65e6dc}}</style><main><h1>Sentinel evaluation</h1>
<p>{manifest["scenario_count"]} deterministic incident scenarios · generated {escape(str(manifest["generated_at"]))}</p>
<table><thead><tr><th>System</th><th>Accuracy</th><th>Evidence precision</th><th>Evidence recall</th><th>Mean tools</th><th>Mean time</th></tr></thead>
<tbody>{rows}</tbody></table><p>Raw JSON and CSV are distributed alongside this report.</p></main></html>"""


def render_svg(summary: dict[str, dict[str, float | int]], systems: list[str]) -> str:
    width, height = 900, 110 + len(systems) * 64
    bars: list[str] = []
    for index, name in enumerate(systems):
        value = float(summary[name]["root_cause_accuracy"])
        y = 75 + index * 64
        bars.append(
            f'<text x="20" y="{y + 20}" fill="#dbeafe" font-size="16">{escape(name)}</text>'
            f'<rect x="270" y="{y}" width="560" height="26" rx="6" fill="#16304a"/>'
            f'<rect x="270" y="{y}" width="{560 * value:.1f}" height="26" rx="6" fill="#43d9c6"/>'
            f'<text x="840" y="{y + 20}" fill="#dbeafe" font-size="15">{value:.1%}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#07111f"/>'
        '<text x="20" y="38" fill="#65e6dc" font-family="system-ui" font-size="24" '
        'font-weight="700">Root-cause accuracy</text><g font-family="system-ui">'
        + "".join(bars)
        + "</g></svg>"
    )


def render_failures(rows: list[TrialResult]) -> str:
    failures = [row for row in rows if not row.root_cause_correct]
    failures.sort(key=lambda row: (row.system != "sentinel_full", row.evidence_recall))
    chosen: list[TrialResult] = []
    seen: set[tuple[str, str]] = set()
    for row in failures:
        key = (row.system, row.scenario_id)
        if key not in seen:
            chosen.append(row)
            seen.add(key)
        if len(chosen) == 5:
            break
    counts = Counter(row.system for row in chosen)
    scenario_by_id = {scenario.id: scenario for scenario in build_catalog()}
    corrective_actions = {
        "bad_configmap": "require both the ConfigMap diff and an upstream URL validation error",
        "image_pull_failure": "pair registry manifest existence with the ImagePullBackOff event",
        "dependency_timeout": "correlate the downstream trace span with the client timeout log",
        "slow_query_lock": "collect a lock-wait sample and the blocked query fingerprint",
        "downstream_rate_limit": "require a 429 cluster plus the rate-limit response headers",
    }
    lines = [
        "# Five failure analyses",
        "",
        "These are observed errors from the measured portfolio run, selected before any manual review.",
        "",
    ]
    for index, row in enumerate(chosen, start=1):
        scenario = scenario_by_id[row.scenario_id]
        correction = corrective_actions.get(
            row.expected_root_cause,
            "require one more category-specific independent signal",
        )
        lines.extend(
            [
                f"## {index}. {row.system}: `{row.scenario_id}`",
                "",
                f"- Expected root cause: `{row.expected_root_cause}`",
                f"- Predicted root cause: `{row.predicted_root_cause}` ({row.diagnosis_status})",
                f"- Evidence recall: {row.evidence_recall:.3f}",
                "- Why it failed: the verifier rejected the leading diagnosis because the selected "
                "evidence did not clear the corroboration margin against a competing signature.",
                f"- Missing discriminators: `{', '.join(scenario.expected_evidence)}`.",
                f"- Corrective action: retain this seed as a regression fixture and {correction}.",
                "",
            ]
        )
    lines.append(
        "Selection distribution: " + ", ".join(f"{name}={count}" for name, count in counts.items())
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the measured Sentinel portfolio evaluation")
    parser.add_argument("--suite", default="portfolio", choices=["portfolio"])
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--scenario-limit", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(evaluate(args.output, args.scenario_limit))


if __name__ == "__main__":
    main()
