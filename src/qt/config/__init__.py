"""Config schemas and fail-fast loading for the four config files.

Every process on the money path loads config through :mod:`qt.config.loader`,
which validates against the pydantic schemas in :mod:`qt.config.schemas` and
refuses to start on any violation. ``config/risk.yaml`` is human-edited only.
"""

from qt.config.loader import ConfigError, load_all_configs, load_config
from qt.config.schemas import (
    AppConfig,
    DataConfig,
    InstrumentsConfig,
    RiskConfig,
    StrategiesConfig,
)

__all__ = [
    "AppConfig",
    "ConfigError",
    "DataConfig",
    "InstrumentsConfig",
    "RiskConfig",
    "StrategiesConfig",
    "load_all_configs",
    "load_config",
]
