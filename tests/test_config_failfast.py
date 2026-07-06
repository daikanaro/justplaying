"""Every class of config corruption must fail loudly at load time, never at trade time."""

import copy
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from qt.config import (
    ConfigError,
    DataConfig,
    InstrumentsConfig,
    RiskConfig,
    StrategiesConfig,
    load_all_configs,
    load_config,
    schemas,
)


@pytest.fixture(scope="module")
def base(config_dir: Path) -> dict[str, dict[str, Any]]:
    """The shipped configs as plain dicts — known-valid starting points to corrupt."""
    out: dict[str, dict[str, Any]] = {}
    for name in ("risk", "instruments", "strategies", "data"):
        loaded = yaml.safe_load((config_dir / f"{name}.yaml").read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        out[name] = loaded
    return out


def mutated(base: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Deep-copy ``base`` and set a dotted ``path`` to ``value`` (DELETE removes the key)."""
    out = copy.deepcopy(base)
    node = out
    *parents, leaf = path.split(".")
    for key in parents:
        node = node[key]
    if value is DELETE:
        del node[leaf]
    else:
        node[leaf] = value
    return out


DELETE = object()


# ---------------------------------------------------------------------------
# File-level failures (loader)
# ---------------------------------------------------------------------------


def test_missing_file_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "risk.yaml", RiskConfig)


def test_unparseable_yaml_fails(tmp_path: Path) -> None:
    bad = tmp_path / "risk.yaml"
    bad.write_text("mode: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(bad, RiskConfig)


def test_non_mapping_root_fails(tmp_path: Path) -> None:
    bad = tmp_path / "risk.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_config(bad, RiskConfig)


def test_schema_violation_reported_with_path(tmp_path: Path) -> None:
    bad = tmp_path / "risk.yaml"
    bad.write_text("mode: paper\n", encoding="utf-8")
    # re.escape: on Windows the tmp path contains backslashes that are regex escapes.
    with pytest.raises(ConfigError, match=re.escape(str(bad))):
        load_config(bad, RiskConfig)


def test_non_utf8_file_fails_as_config_error(tmp_path: Path) -> None:
    bad = tmp_path / "risk.yaml"
    bad.write_bytes(b"mode: paper  # \xff\n")  # e.g. a cp1251-encoded comment
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(bad, RiskConfig)


def test_duplicate_top_level_key_fails(tmp_path: Path, base: dict[str, dict[str, Any]]) -> None:
    text = yaml.safe_dump(base["risk"]) + "\nper_trade_risk_max: 0.05\n"
    bad = tmp_path / "risk.yaml"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="duplicate mapping key"):
        load_config(bad, RiskConfig)


def test_duplicate_nested_key_fails(tmp_path: Path) -> None:
    bad = tmp_path / "risk.yaml"
    bad.write_text("max_contracts: {MES: 2, MES: 99, M2K: 6}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="duplicate mapping key"):
        load_config(bad, RiskConfig)


# ---------------------------------------------------------------------------
# risk.yaml schema invariants
# ---------------------------------------------------------------------------

RISK_MUTATIONS: list[tuple[str, str, Any]] = [
    ("unknown key is fatal", "surprise_knob", 1),
    ("bad mode", "mode", "yolo"),
    ("zero per-trade risk", "per_trade_risk_default", 0.0),
    ("absurd per-trade risk", "per_trade_risk_max", 0.5),
    ("positive daily halt", "daily_loss_halt", 0.03),
    ("positive kill threshold", "kill_drawdown_hwm", 0.35),
    ("kill shallower than daily halt", "kill_drawdown_hwm", -0.01),
    ("negative contract cap", "max_contracts.MES", -1),
    ("negative cap on non-whitelisted symbol", "max_contracts.MNQ", -1),
    ("zero collar", "price_collar_pct", 0.0),
    ("negative blackout", "event_blackout_min", -5),
    ("auto rearm not allowed in v1", "rearm", "auto"),
    ("missing mode", "mode", DELETE),
    ("inf disables gross notional cap", "gross_notional_max_x_equity", float("inf")),
    ("inf disables VIX gate", "vix_max_for_mr", float("inf")),
    ("1e999 typo coerced to inf", "vix_max_for_mr", "1e999"),
    ("nan risk fraction", "per_trade_risk_default", float("nan")),
    ("lowercase whitelist symbol", "instrument_whitelist", ["mes", "M2K"]),
    ("whitelist symbol with trailing newline", "instrument_whitelist", ["MES\n", "M2K"]),
]


@pytest.mark.parametrize(
    ("label", "path", "value"),
    RISK_MUTATIONS,
    ids=[label for label, _, _ in RISK_MUTATIONS],
)
def test_risk_mutation_rejected(
    base: dict[str, dict[str, Any]], label: str, path: str, value: Any
) -> None:
    with pytest.raises(ValidationError):
        RiskConfig.model_validate(mutated(base["risk"], path, value))


def test_risk_default_above_max_rejected(base: dict[str, dict[str, Any]]) -> None:
    bad = mutated(base["risk"], "per_trade_risk_default", 0.02)  # max is 0.01
    with pytest.raises(ValidationError, match="exceeds"):
        RiskConfig.model_validate(bad)


def test_whitelisted_symbol_without_cap_rejected(base: dict[str, dict[str, Any]]) -> None:
    bad = copy.deepcopy(base["risk"])
    del bad["max_contracts"]["M2K"]
    with pytest.raises(ValidationError, match="no max_contracts"):
        RiskConfig.model_validate(bad)


def test_whitelisted_symbol_with_zero_cap_rejected(base: dict[str, dict[str, Any]]) -> None:
    bad = mutated(base["risk"], "max_contracts.MES", 0)
    with pytest.raises(ValidationError, match="must be > 0"):
        RiskConfig.model_validate(bad)


def test_duplicate_whitelist_symbol_rejected(base: dict[str, dict[str, Any]]) -> None:
    bad = mutated(base["risk"], "instrument_whitelist", ["MES", "MES"])
    with pytest.raises(ValidationError, match="duplicate"):
        RiskConfig.model_validate(bad)


# ---------------------------------------------------------------------------
# instruments.yaml schema invariants
# ---------------------------------------------------------------------------


def test_inconsistent_tick_value_rejected(base: dict[str, dict[str, Any]]) -> None:
    # MES: 5 $/pt x 0.25 tick = 1.25, not 0.50. Wrong tick value = wrong P&L everywhere.
    bad = mutated(base["instruments"], "instruments.MES.tick_value", 0.50)
    with pytest.raises(ValidationError, match="inconsistent"):
        InstrumentsConfig.model_validate(bad)


def test_eth_slippage_below_rth_rejected(base: dict[str, dict[str, Any]]) -> None:
    bad = mutated(base["instruments"], "slippage.eth_ticks_per_side", 0)
    with pytest.raises(ValidationError, match="overnight"):
        InstrumentsConfig.model_validate(bad)


def test_stress_multipliers_must_include_1_2_3(base: dict[str, dict[str, Any]]) -> None:
    bad = mutated(base["instruments"], "slippage.stress_multipliers", [1, 2])
    with pytest.raises(ValidationError, match="must include"):
        InstrumentsConfig.model_validate(bad)


def test_duplicate_stress_multipliers_rejected(base: dict[str, dict[str, Any]]) -> None:
    bad = mutated(base["instruments"], "slippage.stress_multipliers", [1, 1, 2, 3])
    with pytest.raises(ValidationError, match="strictly ascending"):
        InstrumentsConfig.model_validate(bad)


def test_unknown_instrument_field_rejected(base: dict[str, dict[str, Any]]) -> None:
    bad = mutated(base["instruments"], "instruments.MES.margin", 1500)
    with pytest.raises(ValidationError):
        InstrumentsConfig.model_validate(bad)


def test_inf_dollars_per_point_rejected(base: dict[str, dict[str, Any]]) -> None:
    # inf $/point + inf tick_value would also defeat the tick check (inf-inf is nan).
    bad = mutated(base["instruments"], "instruments.MES.dollars_per_point", float("inf"))
    bad = mutated(bad, "instruments.MES.tick_value", float("inf"))
    with pytest.raises(ValidationError):
        InstrumentsConfig.model_validate(bad)


def test_inf_commission_rejected(base: dict[str, dict[str, Any]]) -> None:
    bad = mutated(base["instruments"], "instruments.MES.commission_per_side", float("inf"))
    with pytest.raises(ValidationError):
        InstrumentsConfig.model_validate(bad)


def test_malformed_instrument_key_rejected(base: dict[str, dict[str, Any]]) -> None:
    bad = copy.deepcopy(base["instruments"])
    bad["instruments"]["TOOLONG7"] = bad["instruments"]["MES"]  # 7 chars, max is 6
    with pytest.raises(ValidationError, match="invalid symbol"):
        InstrumentsConfig.model_validate(bad)


# ---------------------------------------------------------------------------
# strategies.yaml schema invariants
# ---------------------------------------------------------------------------

STRATEGY_MUTATIONS: list[tuple[str, str, Any]] = [
    ("donchian below 2", "s1_trend_breakout.tf_h.donchian_n", 1),
    ("zero atr stop", "s1_trend_breakout.tf_h.atr_stop_k", 0.0),
    ("tf_h on daily bars", "s1_trend_breakout.tf_h.bar_timeframe", "1d"),
    ("tf_d on hourly bars", "s1_trend_breakout.tf_d.bar_timeframe", "1h"),
    ("tf_h without entry session", "s1_trend_breakout.tf_h.entry_session_utc", None),
    ("malformed session time", "s1_trend_breakout.tf_h.entry_session_utc.start", "25:00"),
    (
        "session time with trailing newline",
        "s1_trend_breakout.tf_h.entry_session_utc.start",
        "13:30\n",
    ),
    ("unsorted research grid", "s1_trend_breakout.research_grid.donchian_n", [55, 20, 80]),
    ("duplicate grid cells", "s1_trend_breakout.research_grid.donchian_n", [20, 20, 40]),
    ("inf grid atr stop", "s1_trend_breakout.research_grid.atr_stop_k", [2.5, float("inf")]),
    ("inf atr stop", "s1_trend_breakout.tf_h.atr_stop_k", float("inf")),
    ("rsi entry above exit", "s2_mr_rsi2.rsi_entry_below", 70.0),
    ("short side in v1 S2", "s2_mr_rsi2.long_only", False),
    ("single fill mode", "s2_mr_rsi2.fill_modes", ["next_open"]),
    ("unknown fill mode", "s2_mr_rsi2.fill_modes", ["next_open", "vwap"]),
    (
        "duplicate fill mode",
        "s2_mr_rsi2.fill_modes",
        ["same_close", "next_open", "next_open"],
    ),
    ("inf hard stop multiple", "s2_mr_rsi2.hard_stop_atr_mult", float("inf")),
    ("zero time stop", "s2_mr_rsi2.time_stop_bars", 0),
    ("duplicate symbols", "s2_mr_rsi2.symbols", ["M2K", "M2K"]),
    ("lowercase strategy symbol", "s2_mr_rsi2.symbols", ["m2k"]),
]


@pytest.mark.parametrize(
    ("label", "path", "value"),
    STRATEGY_MUTATIONS,
    ids=[label for label, _, _ in STRATEGY_MUTATIONS],
)
def test_strategy_mutation_rejected(
    base: dict[str, dict[str, Any]], label: str, path: str, value: Any
) -> None:
    with pytest.raises(ValidationError):
        StrategiesConfig.model_validate(mutated(base["strategies"], path, value))


# ---------------------------------------------------------------------------
# data.yaml schema invariants
# ---------------------------------------------------------------------------

DATA_MUTATIONS: list[tuple[str, str, Any]] = [
    ("pacing above IBKR limit", "ibkr.pacing.max_requests_per_10min", 120),
    ("history beyond IBKR window", "ibkr.history_years", 5),
    ("ratio adjustment forbidden", "roll.adjustment", "ratio"),
    ("unknown roll rule", "roll.rule", "open_interest"),
    ("insecure vix url", "sources.vix.url", "http://example.com/vix.csv"),
    ("unknown vendor", "sources.deep_history.provider", "yahoo"),
    ("malformed funding start", "sources.binance_funding.start", "2020/01/01"),
    ("qc criticals must block", "qc.criticals_block_promotion", False),
    ("inf outlier sigma disables QC", "qc.outlier_sigma", float("inf")),
]


@pytest.mark.parametrize(
    ("label", "path", "value"),
    DATA_MUTATIONS,
    ids=[label for label, _, _ in DATA_MUTATIONS],
)
def test_data_mutation_rejected(
    base: dict[str, dict[str, Any]], label: str, path: str, value: Any
) -> None:
    with pytest.raises(ValidationError):
        DataConfig.model_validate(mutated(base["data"], path, value))


def test_raw_equals_curated_dir_rejected(base: dict[str, dict[str, Any]]) -> None:
    bad = mutated(base["data"], "paths.curated_dir", base["data"]["paths"]["raw_dir"])
    with pytest.raises(ValidationError, match="must differ"):
        DataConfig.model_validate(bad)


# ---------------------------------------------------------------------------
# Cross-file invariants (load_all_configs)
# ---------------------------------------------------------------------------


def write_config_dir(tmp_path: Path, configs: dict[str, dict[str, Any]]) -> Path:
    for name, content in configs.items():
        (tmp_path / f"{name}.yaml").write_text(yaml.safe_dump(content), encoding="utf-8")
    return tmp_path


def test_cross_file_whitelist_symbol_unknown(
    tmp_path: Path, base: dict[str, dict[str, Any]]
) -> None:
    configs = copy.deepcopy(base)
    del configs["instruments"]["instruments"]["MES"]
    # MES stays whitelisted in risk.yaml but no longer exists as an instrument.
    with pytest.raises(ConfigError, match="MES"):
        load_all_configs(write_config_dir(tmp_path, configs))


def test_cross_file_strategy_symbol_unknown(
    tmp_path: Path, base: dict[str, dict[str, Any]]
) -> None:
    configs = copy.deepcopy(base)
    configs["strategies"]["s2_mr_rsi2"]["symbols"] = ["M2K", "MYM"]
    with pytest.raises(ConfigError, match="MYM"):
        load_all_configs(write_config_dir(tmp_path, configs))


def test_cross_file_strategy_symbol_without_risk_cap(
    tmp_path: Path, base: dict[str, dict[str, Any]]
) -> None:
    # MYM exists as an instrument and is traded by S2, but risk.yaml gives it no
    # max_contracts entry — an uncapped symbol on the money path must not load.
    configs = copy.deepcopy(base)
    configs["instruments"]["instruments"]["MYM"] = dict(
        configs["instruments"]["instruments"]["MES"]
    )
    configs["strategies"]["s2_mr_rsi2"]["symbols"] = ["M2K", "MYM"]
    with pytest.raises(ConfigError, match="max_contracts"):
        load_all_configs(write_config_dir(tmp_path, configs))


def test_cross_file_valid_configs_load(tmp_path: Path, base: dict[str, dict[str, Any]]) -> None:
    app = load_all_configs(write_config_dir(tmp_path, copy.deepcopy(base)))
    assert app.risk.mode == "paper"


def test_all_models_forbid_extra_keys() -> None:
    """Belt-and-braces: every config model must reject unknown keys."""
    models = [
        obj
        for obj in vars(schemas).values()
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel
    ]
    assert len(models) > 10  # sanity: we actually found the schema classes
    for model in models:
        assert model.model_config.get("extra") == "forbid", model.__name__
