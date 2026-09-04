from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from simulator.faults.kubernetes import CommandResult, SubprocessCommandRunner


class KindCluster:
    def __init__(self, root: Path | None = None, cluster_name: str = "sentinel") -> None:
        self.root = root or Path(__file__).resolve().parents[1]
        self.cluster_name = cluster_name
        self.runner = SubprocessCommandRunner()

    def bootstrap(self) -> None:
        self._require("docker", "kind", "kubectl")
        clusters = self._run(["kind", "get", "clusters"])
        if self.cluster_name not in clusters.stdout.splitlines():
            self._run(
                [
                    "kind",
                    "create",
                    "cluster",
                    "--name",
                    self.cluster_name,
                    "--config",
                    str(self.root / "infrastructure" / "kubernetes" / "kind-config.yaml"),
                ]
            )
        images = (
            (
                "sentinel/demo-service:local",
                self.root / "infrastructure" / "docker" / "demo-service.Dockerfile",
            ),
            (
                "sentinel/traffic-generator:local",
                self.root / "infrastructure" / "docker" / "traffic.Dockerfile",
            ),
        )
        for image, dockerfile in images:
            self._run(
                ["docker", "build", "-f", str(dockerfile), "-t", image, str(self.root)],
                timeout_seconds=600,
            )
            self._run(
                ["kind", "load", "docker-image", image, "--name", self.cluster_name],
                timeout_seconds=180,
            )
        self._run(
            [
                "kubectl",
                "apply",
                "-f",
                str(self.root / "infrastructure" / "kubernetes" / "namespace.yaml"),
            ]
        )
        self._run(
            [
                "kubectl",
                "apply",
                "-f",
                str(self.root / "infrastructure" / "kubernetes" / "demo-services.yaml"),
            ]
        )
        for resource in (
            "statefulset/postgres",
            "deployment/checkout",
            "deployment/payments",
            "deployment/worker",
            "deployment/frontend",
            "deployment/traffic-generator",
        ):
            self._run(
                [
                    "kubectl",
                    "rollout",
                    "status",
                    resource,
                    "--namespace",
                    "sentinel-demo",
                    "--timeout=180s",
                ],
                timeout_seconds=190,
            )

    def delete(self) -> None:
        self._require("kind")
        self._run(["kind", "delete", "cluster", "--name", self.cluster_name])

    def status(self) -> CommandResult:
        self._require("kubectl")
        return self._run(
            [
                "kubectl",
                "get",
                "pods,services,deployments,statefulsets",
                "--namespace",
                "sentinel-demo",
                "-o",
                "wide",
            ]
        )

    @staticmethod
    def _require(*commands: str) -> None:
        missing = [command for command in commands if shutil.which(command) is None]
        if missing:
            raise RuntimeError(f"missing required executables: {', '.join(missing)}")

    def _run(self, args: list[str], *, timeout_seconds: float = 120.0) -> CommandResult:
        result = self.runner.run(args, timeout_seconds=timeout_seconds)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"command failed ({' '.join(args)}): {message}")
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Sentinel's local kind simulator")
    parser.add_argument("command", choices=("bootstrap", "status", "delete"))
    args = parser.parse_args()
    cluster = KindCluster()
    if args.command == "bootstrap":
        cluster.bootstrap()
        print(cluster.status().stdout)
    elif args.command == "status":
        print(cluster.status().stdout)
    else:
        cluster.delete()


if __name__ == "__main__":
    main()
