from __future__ import annotations

from simulator.engine import IncidentSimulator, SimulationSnapshot
from simulator.faults.kubernetes import FaultReceipt, KubernetesFaultController


def inject(simulator: IncidentSimulator, scenario_id: str) -> SimulationSnapshot:
    """The only local mutation entry point; reset keeps evaluation trials idempotent."""
    simulator.reset()
    return simulator.inject(scenario_id)


def inject_cluster(
    scenario_id: str, controller: KubernetesFaultController | None = None
) -> FaultReceipt:
    return (controller or KubernetesFaultController()).inject(scenario_id)


def _inject_cause(cause: str, controller: KubernetesFaultController) -> FaultReceipt:
    return controller.inject(f"{cause}_001")


def inject_oom_killed(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("oom_killed", controller)


def inject_cpu_throttling(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("cpu_throttling", controller)


def inject_memory_leak(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("memory_leak", controller)


def inject_disk_pressure(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("disk_pressure", controller)


def inject_bad_readiness_probe(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("bad_readiness_probe", controller)


def inject_bad_configmap(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("bad_configmap", controller)


def inject_missing_secret(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("missing_secret", controller)


def inject_image_pull_failure(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("image_pull_failure", controller)


def inject_selector_mismatch(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("selector_mismatch", controller)


def inject_dns_failure(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("dns_failure", controller)


def inject_dependency_timeout(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("dependency_timeout", controller)


def inject_network_policy_denied(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("network_policy_denied", controller)


def inject_db_pool_exhaustion(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("db_pool_exhaustion", controller)


def inject_slow_query_lock(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("slow_query_lock", controller)


def inject_bad_environment(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("bad_environment", controller)


def inject_dependency_regression(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("dependency_regression", controller)


def inject_queue_saturation(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("queue_saturation", controller)


def inject_downstream_rate_limit(controller: KubernetesFaultController) -> FaultReceipt:
    return _inject_cause("downstream_rate_limit", controller)
