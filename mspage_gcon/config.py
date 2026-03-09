from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class PodRange:
    id: str
    label: str
    start_gate: int
    end_gate: int

    def contains(self, gate: int) -> bool:
        return self.start_gate <= gate <= self.end_gate


def load_pod_ranges(path: Path) -> list[PodRange]:
    data = json.loads(path.read_text(encoding="utf-8"))
    pods = data.get("pods")
    if not isinstance(pods, list) or not pods:
        raise ValueError("Pod config must contain a non-empty 'pods' list.")

    loaded: list[PodRange] = []
    for pod in pods:
        loaded.append(
            PodRange(
                id=str(pod["id"]),
                label=str(pod["label"]),
                start_gate=int(pod["start_gate"]),
                end_gate=int(pod["end_gate"]),
            )
        )

    return loaded


def assign_pod(gate: int, pods: list[PodRange]) -> PodRange | None:
    for pod in pods:
        if pod.contains(gate):
            return pod
    return None
