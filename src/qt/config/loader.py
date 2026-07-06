"""Fail-fast YAML loading for the four config files.

Any problem — missing file, unparseable YAML, schema violation, cross-file
inconsistency — raises :class:`ConfigError` with the offending path in the
message. Nothing on the money path may start with a half-valid config.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from qt.config.schemas import (
    AppConfig,
    DataConfig,
    InstrumentsConfig,
    RiskConfig,
    StrategiesConfig,
)

CONFIG_FILENAMES: dict[str, str] = {
    "risk": "risk.yaml",
    "instruments": "instruments.yaml",
    "strategies": "strategies.yaml",
    "data": "data.yaml",
}


class ConfigError(Exception):
    """A config file is missing, unparseable, or invalid. Fatal at startup."""


class _StrictKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys.

    PyYAML's default is silently last-wins, so a risk limit accidentally repeated
    at the bottom of risk.yaml would override the real one without a trace.
    """

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _value_node in node.value:
            key = self.construct_object(key_node, deep=True)
            if isinstance(key, (str, int, float, bool)):  # unhashable keys fail in the base class
                if key in seen:
                    raise yaml.constructor.ConstructorError(
                        None, None, f"duplicate mapping key {key!r}", key_node.start_mark
                    )
                seen.add(key)
        return super().construct_mapping(node, deep)


def load_config[M: BaseModel](path: Path, model: type[M]) -> M:
    """Load one YAML file and validate it against ``model``. Fail fast on any error."""
    if not path.is_file():
        msg = f"config file not found: {path}"
        raise ConfigError(msg)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        msg = f"cannot read config file {path}: {exc}"
        raise ConfigError(msg) from exc
    try:
        raw = yaml.load(text, Loader=_StrictKeyLoader)
    except yaml.YAMLError as exc:
        msg = f"invalid YAML in {path}: {exc}"
        raise ConfigError(msg) from exc
    if not isinstance(raw, dict):
        msg = f"config root in {path} must be a mapping, got {type(raw).__name__}"
        raise ConfigError(msg)
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        msg = f"invalid config {path}:\n{exc}"
        raise ConfigError(msg) from exc


def load_all_configs(config_dir: Path) -> AppConfig:
    """Load all four config files from ``config_dir`` and cross-validate them."""
    risk = load_config(config_dir / CONFIG_FILENAMES["risk"], RiskConfig)
    instruments = load_config(config_dir / CONFIG_FILENAMES["instruments"], InstrumentsConfig)
    strategies = load_config(config_dir / CONFIG_FILENAMES["strategies"], StrategiesConfig)
    data = load_config(config_dir / CONFIG_FILENAMES["data"], DataConfig)
    try:
        return AppConfig(risk=risk, instruments=instruments, strategies=strategies, data=data)
    except ValidationError as exc:
        msg = f"cross-file config validation failed in {config_dir}:\n{exc}"
        raise ConfigError(msg) from exc
