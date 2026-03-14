from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

GATE_MIN = 1
GATE_MAX = 22


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
    seen_ids: set[str] = set()
    covered_gates: set[int] = set()
    for index, pod in enumerate(pods, start=1):
        if not isinstance(pod, dict):
            raise ValueError(f"Pod {index} must be an object.")

        pod_id = _require_text(pod, "id", index)
        if pod_id in seen_ids:
            raise ValueError(f"Duplicate pod id: {pod_id}")
        seen_ids.add(pod_id)

        start_gate = _require_int(pod, "start_gate", index)
        end_gate = _require_int(pod, "end_gate", index)
        if start_gate > end_gate:
            raise ValueError(f"Pod {pod_id} has start_gate greater than end_gate.")
        if not GATE_MIN <= start_gate <= GATE_MAX or not GATE_MIN <= end_gate <= GATE_MAX:
            raise ValueError(f"Pod {pod_id} must stay within G{GATE_MIN}-G{GATE_MAX}.")

        overlapping = [gate for gate in range(start_gate, end_gate + 1) if gate in covered_gates]
        if overlapping:
            overlap_labels = ", ".join(f"G{gate}" for gate in overlapping)
            raise ValueError(f"Pod {pod_id} overlaps existing gate coverage: {overlap_labels}")

        covered_gates.update(range(start_gate, end_gate + 1))
        loaded.append(
            PodRange(
                id=pod_id,
                label=_require_text(pod, "label", index),
                start_gate=start_gate,
                end_gate=end_gate,
            )
        )

    expected_gates = set(range(GATE_MIN, GATE_MAX + 1))
    if covered_gates != expected_gates:
        missing_labels = ", ".join(f"G{gate}" for gate in sorted(expected_gates - covered_gates))
        raise ValueError(f"Pod config must cover every gate from G{GATE_MIN}-G{GATE_MAX}; missing {missing_labels}")

    return loaded


def assign_pod(gate: int, pods: list[PodRange]) -> PodRange | None:
    for pod in pods:
        if pod.contains(gate):
            return pod
    return None


def _require_text(pod: dict, key: str, index: int) -> str:
    value = pod.get(key)
    if value is None:
        raise ValueError(f"Pod {index} is missing {key}.")
    text = str(value).strip()
    if not text:
        raise ValueError(f"Pod {index} has an empty {key}.")
    return text


def _require_int(pod: dict, key: str, index: int) -> int:
    value = pod.get(key)
    if value is None:
        raise ValueError(f"Pod {index} is missing {key}.")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Pod {index} has an invalid {key}: {value}") from error
