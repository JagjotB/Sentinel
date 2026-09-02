from __future__ import annotations

from simulator.models import Scenario

FAULT_SPECS: tuple[tuple[str, str, str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "resources",
        "oom_killed",
        "payments",
        "container memory exceeded its limit",
        ("oom_event", "memory_spike", "resource_limit"),
        ("restore_memory_limit", "rollback_deployment"),
    ),
    (
        "resources",
        "cpu_throttling",
        "checkout",
        "CPU limit throttled checkout workers",
        ("cpu_throttle", "latency_spike", "resource_limit"),
        ("restore_cpu_limit", "scale_checkout"),
    ),
    (
        "resources",
        "memory_leak",
        "payments",
        "payments retained request buffers",
        ("memory_trend", "gc_pressure", "error_onset"),
        ("rollback_deployment", "restart_after_approval"),
    ),
    (
        "resources",
        "disk_pressure",
        "worker",
        "node ephemeral storage exhausted",
        ("disk_pressure", "eviction_event", "log_growth"),
        ("rotate_logs", "increase_ephemeral_storage"),
    ),
    (
        "kubernetes",
        "bad_readiness_probe",
        "checkout",
        "readiness probe path regressed",
        ("probe_failure", "zero_ready_endpoints", "manifest_diff"),
        ("restore_probe_path", "rollback_deployment"),
    ),
    (
        "kubernetes",
        "bad_configmap",
        "checkout",
        "invalid upstream URL was deployed",
        ("configmap_diff", "connection_error", "rollout_event"),
        ("restore_configmap", "rollback_deployment"),
    ),
    (
        "kubernetes",
        "missing_secret",
        "payments",
        "payment credential secret key was absent",
        ("secret_key_missing", "startup_failure", "rollout_event"),
        ("restore_secret_reference", "rollback_deployment"),
    ),
    (
        "kubernetes",
        "image_pull_failure",
        "worker",
        "release referenced an unavailable image",
        ("image_pull_backoff", "manifest_diff", "zero_ready_pods"),
        ("restore_image_tag", "rollback_deployment"),
    ),
    (
        "kubernetes",
        "selector_mismatch",
        "frontend",
        "service selector no longer matched pods",
        ("empty_endpoints", "selector_diff", "healthy_pods"),
        ("restore_selector", "rollback_deployment"),
    ),
    (
        "network",
        "dns_failure",
        "checkout",
        "cluster DNS resolution failed for payments",
        ("dns_error", "dependency_timeout", "trace_gap"),
        ("restore_dns_policy", "rollback_network_change"),
    ),
    (
        "network",
        "dependency_timeout",
        "payments",
        "bank gateway latency exceeded client timeout",
        ("downstream_latency", "timeout_log", "trace_span"),
        ("increase_bounded_timeout", "enable_circuit_breaker"),
    ),
    (
        "network",
        "network_policy_denied",
        "checkout",
        "network policy blocked payments egress",
        ("denied_flow", "policy_diff", "dependency_timeout"),
        ("restore_egress_rule", "rollback_network_policy"),
    ),
    (
        "database",
        "db_pool_exhaustion",
        "payments",
        "database connection pool was exhausted",
        ("pool_saturation", "acquire_timeout", "latency_spike"),
        ("tune_pool_limit", "reduce_concurrency"),
    ),
    (
        "database",
        "slow_query_lock",
        "payments",
        "ledger update lock serialized requests",
        ("lock_wait", "slow_query", "trace_span"),
        ("terminate_safe_query", "deploy_index_patch"),
    ),
    (
        "deployment",
        "bad_environment",
        "checkout",
        "release set an invalid feature flag value",
        ("environment_diff", "validation_error", "rollout_event"),
        ("restore_environment", "rollback_deployment"),
    ),
    (
        "deployment",
        "dependency_regression",
        "checkout",
        "new serializer rejected legacy payloads",
        ("exception_cluster", "commit_diff", "error_onset"),
        ("apply_compatibility_patch", "rollback_deployment"),
    ),
    (
        "traffic",
        "queue_saturation",
        "worker",
        "arrival rate exceeded worker capacity",
        ("queue_depth", "consumer_lag", "traffic_spike"),
        ("scale_workers", "apply_backpressure"),
    ),
    (
        "traffic",
        "downstream_rate_limit",
        "payments",
        "bank gateway enforced a lower rate limit",
        ("http_429_cluster", "rate_limit_headers", "traffic_spike"),
        ("reduce_request_rate", "enable_retry_budget"),
    ),
)


def build_catalog() -> list[Scenario]:
    scenarios: list[Scenario] = []
    for index, (category, cause, service, description, evidence, remediations) in enumerate(
        FAULT_SPECS
    ):
        for variant in range(1, 3):
            scenario_id = f"{cause}_{variant:03d}"
            scenarios.append(
                Scenario(
                    id=scenario_id,
                    title=f"{service} {description} (variant {variant})",
                    category=category,
                    service=service,
                    fault_injector=f"simulator.faults.injector:inject_{cause}",
                    root_cause=cause,
                    expected_evidence=list(evidence),
                    acceptable_remediations=list(remediations),
                    forbidden_actions=["delete_namespace", "drop_database", "disable_audit_log"],
                    difficulty=("easy", "medium", "hard")[(index + variant) % 3],
                    seed=10_000 + index * 101 + variant,
                )
            )
    return scenarios


def by_id(scenario_id: str) -> Scenario:
    try:
        return next(s for s in build_catalog() if s.id == scenario_id)
    except StopIteration as exc:
        raise KeyError(f"unknown scenario: {scenario_id}") from exc
