"""Data models and config loading for the context-efficiency module."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DEFAULTS = {
    "enabled": False,
    "analyze_on_shutdown": False,
    "min_confidence": 0.7,
    "project_dirs": [],
    "hooks_enabled": False,
}


def load_config(config_path: Path) -> dict:
    """Load context_efficiency config from config.json, with defaults for missing keys."""
    try:
        with open(config_path) as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULTS)

    section = raw.get("context_efficiency", {})
    return {key: section.get(key, default) for key, default in DEFAULTS.items()}


@dataclass
class ToolCall:
    tool_name: str
    tool_id: str
    tool_input: dict
    result_text: str
    result_tokens: int

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> "ToolCall":
        return cls(**d)

    @classmethod
    def from_json(cls, s: str) -> "ToolCall":
        return cls.from_dict(json.loads(s))


@dataclass
class UtilizationScore:
    substring_ratio: float
    action_signal: float
    null_response: float
    composite: float

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> "UtilizationScore":
        return cls(**d)

    @classmethod
    def from_json(cls, s: str) -> "UtilizationScore":
        return cls.from_dict(json.loads(s))


@dataclass
class FilterRule:
    id: str
    tool: str
    pattern: str
    match_field: str
    avg_output_tokens: int
    avg_utilization: float
    sample_count: int
    confidence: float
    action: str
    action_params: dict
    description: str

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> "FilterRule":
        return cls(**d)

    @classmethod
    def from_json(cls, s: str) -> "FilterRule":
        return cls.from_dict(json.loads(s))
