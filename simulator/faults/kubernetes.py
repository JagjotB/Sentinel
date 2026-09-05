from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from simulator.catalog import by_id
from simulator.models import Scenario


class CommandResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    args: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    def run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> CommandResult: ...


class SubprocessCommandRunner:
    def run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> CommandResult:
        executable = shutil.which(args[0])
        if executable is None:
            raise RuntimeError(f"required executable was not found: {args[0]}")
        completed = subprocess.run(  # noqa: S603 - fixed argv, shell is never enabled
            [executable, *args[1:]],
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(
            args=args,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class FaultReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: str
    root_cause: str
    namespace: str
    operations: list[list[str]] = Field(min_length=1)
    observation: dict[str, object] = Field(default_factory=dict)


class FaultEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: str
    service: str
    pod: str
    reason: str
    restart_count: int = Field(ge=0)


class KubernetesFaultController:
    """Mutates only the dedicated Sentinel demo namespace through argv-safe kubectl calls."""

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        namespace: str = "sentinel-demo",
        repository_root: Path | None = None,
    ) -> None:
        self.runner = runner or SubprocessCommandRunner()
        self.namespace = namespace
        self.repository_root = repository_root or Path(__file__).resolve().parents[2]
        self.operations: list[list[str]] = []

    def inject(self, scenario_id: str) -> FaultReceipt:
        scenario = by_id(scenario_id)
        self.operations = []
        self.reset(wait=False)
        self._set_fault_mode(scenario.service, scenario.root_cause, scenario.id)
        strategy = getattr(self, f"_inject_{scenario.root_cause}")
        strategy(scenario)
        observation = self._observe()
        return FaultReceipt(
            scenario_id=scenario.id,
            root_cause=scenario.root_cause,
            namespace=self.namespace,
            operations=list(self.operations),
            observation=observation,
        )

    def reset(self, *, wait: bool = True) -> list[list[str]]:
        self.operations = []
        namespace_manifest = (
            self.repository_root / "infrastructure" / "kubernetes" / "namespace.yaml"
        )
        service_manifest = (
            self.repository_root / "infrastructure" / "kubernetes" / "demo-services.yaml"
        )
        self._kubectl("apply", "-f", str(namespace_manifest))
        self._kubectl(
            "delete",
            "networkpolicy",
            "sentinel-deny-checkout-egress",
            "--ignore-not-found=true",
            check=False,
        )
        self._kubectl("apply", "-f", str(service_manifest))
        for deployment in ("checkout", "payments", "worker", "frontend"):
            self._kubectl(
                "set",
                "env",
                f"deployment/{deployment}",
                "SENTINEL_FAULT_MODE=none",
                "SENTINEL_SCENARIO_ID=baseline",
            )
        self._kubectl("set", "env", "deployment/payments", "OOM_ALLOCATION_MB-")
        self._kubectl("set", "env", "deployment/checkout", "FEATURE_FLAG-")
        self._patch_config("PAYMENTS_URL", "http://payments:8080")
        self._patch_config("TARGET_URL", "http://checkout:8080/work")
        self._patch_config("FEATURE_FLAG", "enabled")
        self._kubectl(
            "set", "env", "deployment/traffic-generator", "REQUESTS_PER_SECOND=2"
        )
        self._kubectl(
            "set",
            "image",
            "deployment/worker",
            "worker=sentinel/demo-service:local",
        )
        self._kubectl(
            "patch",
            "deployment/checkout",
            "--type=json",
            "-p",
            json.dumps(
                [
                    {
                        "op": "replace",
                        "path": "/spec/template/spec/containers/0/readinessProbe/httpGet/path",
                        "value": "/readyz",
                    }
                ]
            ),
        )
        self._kubectl(
            "patch",
            "service/frontend",
            "--type=merge",
            "-p",
            json.dumps({"spec": {"selector": {"app": "frontend"}}}),
        )
        self._kubectl(
            "patch",
            "deployment/payments",
            "--type=json",
            "-p",
            json.dumps(
                [
                    {
                        "op": "replace",
                        "path": "/spec/template/spec/containers/0/env/3/valueFrom/secretKeyRef/key",
                        "value": "PAYMENT_TOKEN",
                    }
                ]
            ),
        )
        self._patch_resources("checkout", cpu="500m", memory="512Mi")
        self._patch_resources("payments", cpu="500m", memory="512Mi")
        self._patch_resources(
            "worker", cpu="500m", memory="512Mi", ephemeral_storage="256Mi"
        )
        self._kubectl("rollout", "restart", "deployment/traffic-generator")
        if wait:
            for resource in (
                "statefulset/postgres",
                "deployment/checkout",
                "deployment/payments",
                "deployment/worker",
                "deployment/frontend",
                "deployment/traffic-generator",
            ):
                self._kubectl(
                    "rollout", "status", resource, "--timeout=120s", timeout_seconds=130
                )
        return list(self.operations)

    def wait_for_oom_killed(
        self,
        scenario_id: str,
        *,
        timeout_seconds: float = 90.0,
        poll_interval_seconds: float = 1.0,
    ) -> FaultEvidence:
        """Wait until Kubernetes records an actual OOM termination for the scenario."""
        scenario = by_id(scenario_id)
        if scenario.root_cause != "oom_killed":
            raise ValueError(f"scenario is not an OOM fault: {scenario_id}")
        deadline = time.monotonic() + timeout_seconds
        last_error = "Kubernetes has not reported OOMKilled"
        while time.monotonic() < deadline:
            result = self._kubectl(
                "get",
                "pods",
                "-l",
                f"app={scenario.service}",
                "-o",
                "json",
                check=False,
            )
            if result.returncode == 0:
                try:
                    payload: object = json.loads(result.stdout)
                except json.JSONDecodeError:
                    last_error = "kubectl returned non-JSON pod state"
                else:
                    evidence = self._find_oom_evidence(payload, scenario.id, scenario.service)
                    if evidence is not None:
                        return evidence
            else:
                last_error = result.stderr.strip() or "kubectl pod query failed"
            time.sleep(poll_interval_seconds)
        raise RuntimeError(
            f"timed out after {timeout_seconds:g}s waiting for OOMKilled "
            f"for {scenario.service}: {last_error}"
        )

    @staticmethod
    def _find_oom_evidence(
        payload: object, scenario_id: str, service: str
    ) -> FaultEvidence | None:
        if not isinstance(payload, dict):
            return None
        items = payload.get("items")
        if not isinstance(items, list):
            return None
        for item in items:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata")
            status = item.get("status")
            if not isinstance(metadata, dict) or not isinstance(status, dict):
                continue
            pod_name = metadata.get("name")
            container_statuses = status.get("containerStatuses")
            if not isinstance(pod_name, str) or not isinstance(container_statuses, list):
                continue
            for container_status in container_statuses:
                if not isinstance(container_status, dict):
                    continue
                restart_count_raw = container_status.get("restartCount", 0)
                restart_count = (
                    restart_count_raw if isinstance(restart_count_raw, int) else 0
                )
                for state_name in ("lastState", "state"):
                    state = container_status.get(state_name)
                    if not isinstance(state, dict):
                        continue
                    terminated = state.get("terminated")
                    if not isinstance(terminated, dict):
                        continue
                    if terminated.get("reason") == "OOMKilled":
                        return FaultEvidence(
                            scenario_id=scenario_id,
                            service=service,
                            pod=pod_name,
                            reason="OOMKilled",
                            restart_count=restart_count,
                        )
        return None

    def _set_fault_mode(self, deployment: str, cause: str, scenario_id: str) -> None:
        self._kubectl(
            "set",
            "env",
            f"deployment/{deployment}",
            f"SENTINEL_FAULT_MODE={cause}",
            f"SENTINEL_SCENARIO_ID={scenario_id}",
        )

    def _inject_oom_killed(self, _: Scenario) -> None:
        self._patch_resources("payments", memory="96Mi")
        self._kubectl("set", "env", "deployment/payments", "OOM_ALLOCATION_MB=192")
        self._set_traffic("http://payments:8080/work", 4)

    def _inject_cpu_throttling(self, _: Scenario) -> None:
        self._patch_resources("checkout", cpu="20m")
        self._set_traffic("http://checkout:8080/work", 6)

    def _inject_memory_leak(self, _: Scenario) -> None:
        self._patch_resources("payments", memory="128Mi")
        self._set_traffic("http://payments:8080/work", 10)

    def _inject_disk_pressure(self, _: Scenario) -> None:
        self._patch_resources("worker", ephemeral_storage="48Mi")
        self._set_traffic("http://worker:8080/work", 8)

    def _inject_bad_readiness_probe(self, _: Scenario) -> None:
        self._kubectl(
            "patch",
            "deployment/checkout",
            "--type=json",
            "-p",
            json.dumps(
                [
                    {
                        "op": "replace",
                        "path": "/spec/template/spec/containers/0/readinessProbe/httpGet/path",
                        "value": "/not-a-readiness-endpoint",
                    }
                ]
            ),
        )

    def _inject_bad_configmap(self, _: Scenario) -> None:
        self._patch_config("PAYMENTS_URL", "http://payment-does-not-exist:8080")
        self._kubectl("rollout", "restart", "deployment/checkout")

    def _inject_missing_secret(self, _: Scenario) -> None:
        self._kubectl(
            "patch",
            "deployment/payments",
            "--type=json",
            "-p",
            json.dumps(
                [
                    {
                        "op": "replace",
                        "path": "/spec/template/spec/containers/0/env/3/valueFrom/secretKeyRef/key",
                        "value": "MISSING_PAYMENT_TOKEN",
                    }
                ]
            ),
        )

    def _inject_image_pull_failure(self, _: Scenario) -> None:
        self._kubectl(
            "set",
            "image",
            "deployment/worker",
            "worker=sentinel/worker-image-does-not-exist:missing",
        )

    def _inject_selector_mismatch(self, _: Scenario) -> None:
        self._kubectl(
            "patch",
            "service/frontend",
            "--type=merge",
            "-p",
            json.dumps({"spec": {"selector": {"app": "frontend-mismatch"}}}),
        )

    def _inject_dns_failure(self, _: Scenario) -> None:
        self._patch_config("PAYMENTS_URL", "http://payments.invalid.sentinel:8080")
        self._kubectl("rollout", "restart", "deployment/checkout")

    def _inject_dependency_timeout(self, _: Scenario) -> None:
        self._set_fault_mode("payments", "dependency_timeout", "dependency_timeout")
        self._set_traffic("http://checkout:8080/work", 4)

    def _inject_network_policy_denied(self, _: Scenario) -> None:
        manifest = (
            self.repository_root
            / "infrastructure"
            / "kubernetes"
            / "faults"
            / "deny-checkout-egress.yaml"
        )
        self._kubectl("apply", "-f", str(manifest))

    def _inject_db_pool_exhaustion(self, _: Scenario) -> None:
        self._set_traffic("http://payments:8080/work", 12)

    def _inject_slow_query_lock(self, _: Scenario) -> None:
        self._set_traffic("http://payments:8080/work", 6)

    def _inject_bad_environment(self, _: Scenario) -> None:
        self._kubectl("set", "env", "deployment/checkout", "FEATURE_FLAG=definitely-invalid")

    def _inject_dependency_regression(self, _: Scenario) -> None:
        self._set_traffic("http://checkout:8080/work", 5)

    def _inject_queue_saturation(self, _: Scenario) -> None:
        self._set_traffic("http://worker:8080/work", 20)

    def _inject_downstream_rate_limit(self, _: Scenario) -> None:
        self._set_traffic("http://payments:8080/work", 15)

    def _patch_resources(
        self,
        deployment: str,
        *,
        cpu: str | None = None,
        memory: str | None = None,
        ephemeral_storage: str | None = None,
    ) -> None:
        limits: dict[str, str] = {}
        if cpu:
            limits["cpu"] = cpu
        if memory:
            limits["memory"] = memory
        if ephemeral_storage:
            limits["ephemeral-storage"] = ephemeral_storage
        payload = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {"name": deployment, "resources": {"limits": limits}}
                        ]
                    }
                }
            }
        }
        self._kubectl(
            "patch", f"deployment/{deployment}", "--type=strategic", "-p", json.dumps(payload)
        )

    def _patch_config(self, key: str, value: str) -> None:
        self._kubectl(
            "patch",
            "configmap/sentinel-demo-config",
            "--type=merge",
            "-p",
            json.dumps({"data": {key: value}}),
        )

    def _set_traffic(self, target: str, requests_per_second: int) -> None:
        self._patch_config("TARGET_URL", target)
        self._kubectl(
            "set",
            "env",
            "deployment/traffic-generator",
            f"REQUESTS_PER_SECOND={requests_per_second}",
        )
        self._kubectl("rollout", "restart", "deployment/traffic-generator")

    def _observe(self) -> dict[str, object]:
        result = self._kubectl(
            "get",
            "pods,services,deployments,statefulsets",
            "-o",
            "json",
            check=False,
        )
        if result.returncode != 0:
            return {"available": False, "error": result.stderr.strip()}
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"available": False, "error": "kubectl returned non-JSON state"}
        items = payload.get("items", []) if isinstance(payload, dict) else []
        return {"available": True, "resource_count": len(items), "resources": items}

    def _kubectl(
        self,
        *arguments: str,
        check: bool = True,
        timeout_seconds: float = 60.0,
    ) -> CommandResult:
        args = ["kubectl", *arguments, "--namespace", self.namespace]
        result = self.runner.run(args, timeout_seconds=timeout_seconds)
        self.operations.append(args)
        if check and result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"kubectl command failed ({' '.join(arguments)}): {message}")
        return result
