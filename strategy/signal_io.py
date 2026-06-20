from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import SignalResult, StrategyState


def _json_safe(value: Any) -> Any:
    if isinstance(value, StrategyState):
        return value.value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def signal_to_dict(result: SignalResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["current_state"] = result.current_state.value
    payload["target_state"] = result.target_state.value
    payload["current_position_pct"] = result.current_position_pct
    payload["target_position_pct"] = result.target_position_pct
    return _json_safe(payload)


def write_signal_json(result: SignalResult, path: str | Path, extra: dict[str, Any] | None = None) -> None:
    payload = signal_to_dict(result)
    if extra:
        payload["auto_update"] = _json_safe(extra)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: str | Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
