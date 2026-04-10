# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for SLA constraint filtering in the picking / pareto analysis layer.

Covers:
- TPOT constraint filtering excludes configs that violate the target
- TTFT constraint is enforced during picking (not just during search)
- Fallback behavior when no config meets the SLA
- Combined TTFT + TPOT filtering
"""

import pandas as pd
import pytest

from aiconfigurator.sdk.pareto_analysis import (
    get_best_configs_under_request_latency_constraint,
    get_best_configs_under_tpot_constraint,
)

pytestmark = pytest.mark.unit


def _make_pareto_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal pareto-style DataFrame for testing picking logic."""
    defaults = {
        "model": "test-model",
        "isl": 4000,
        "osl": 1000,
        "prefix": 0,
        "concurrency": 1,
        "request_rate": 1.0,
        "bs": 1,
        "global_bs": 1,
        "seq/s": 10.0,
        "seq/s/gpu": 5.0,
        "tokens/s": 1000.0,
        "tokens/s/user": 100.0,
        "num_total_gpus": 1,
        "tp": 1,
        "pp": 1,
        "dp": 1,
        "moe_tp": 0,
        "moe_ep": 0,
        "parallel": "tp1_pp1_dp1",
        "gemm": "fp16",
        "kvcache": "fp16",
        "fmha": "fp16",
        "moe": "none",
        "comm": "none",
        "memory": 0.5,
        "balance_score": 1.0,
        "num_ctx_reqs": 1,
        "num_gen_reqs": 1,
        "num_tokens": 1000,
        "ctx_tokens": 500,
        "gen_tokens": 500,
        "backend": "trtllm",
        "version": "1.0.0",
        "system": "h100_sxm",
        "power_w": 300.0,
        "request_latency": 0.0,
    }
    records = []
    for row in rows:
        record = {**defaults, **row}
        records.append(record)
    return pd.DataFrame(records)


class TestTpotConstraintFiltering:
    """Configs violating the user's --tpot must not appear in best_config_topn."""

    def test_only_sla_compliant_configs_returned(self):
        """Configs with tpot > target should be excluded."""
        df = _make_pareto_df(
            [
                {"tpot": 10.0, "ttft": 500.0, "tokens/s/gpu": 800.0},
                {"tpot": 20.0, "ttft": 500.0, "tokens/s/gpu": 1200.0},  # violates --tpot 15
                {"tpot": 45.0, "ttft": 500.0, "tokens/s/gpu": 1500.0},  # violates --tpot 15
            ]
        )
        result = get_best_configs_under_tpot_constraint(
            total_gpus=8,
            pareto_df=df,
            target_tpot=15.0,
            top_n=5,
        )
        assert not result.empty
        assert (result["tpot"] <= 15.0).all(), "All returned configs must meet the TPOT SLA"

    def test_fallback_when_nothing_meets_sla(self):
        """When no config meets the SLA, fallback returns closest violators."""
        df = _make_pareto_df(
            [
                {"tpot": 20.0, "ttft": 500.0, "tokens/s/gpu": 800.0},
                {"tpot": 30.0, "ttft": 500.0, "tokens/s/gpu": 1200.0},
            ]
        )
        result = get_best_configs_under_tpot_constraint(
            total_gpus=8,
            pareto_df=df,
            target_tpot=5.0,
            top_n=5,
        )
        # Should return something (fallback), sorted by closest to target
        assert not result.empty
        assert result.iloc[0]["tpot"] == 20.0, "Fallback should return the config closest to the SLA target"


class TestTtftConstraintFiltering:
    """TTFT must be checked during picking, not just during search."""

    def test_ttft_filter_applied_with_tpot_constraint(self):
        """Configs violating --ttft should be excluded even if tpot is fine."""
        df = _make_pareto_df(
            [
                {"tpot": 10.0, "ttft": 500.0, "tokens/s/gpu": 800.0},  # meets both
                {"tpot": 12.0, "ttft": 2000.0, "tokens/s/gpu": 1200.0},  # ttft violation
                {"tpot": 8.0, "ttft": 900.0, "tokens/s/gpu": 600.0},  # meets both
            ]
        )
        result = get_best_configs_under_tpot_constraint(
            total_gpus=8,
            pareto_df=df,
            target_tpot=15.0,
            top_n=5,
            target_ttft=1000.0,
        )
        assert not result.empty
        assert (result["ttft"] <= 1000.0).all(), "All returned configs must meet the TTFT SLA"
        assert len(result) == 2, "Only configs meeting both SLAs should be returned"

    def test_ttft_filter_applied_with_request_latency_constraint(self):
        """TTFT filtering should also work in the request-latency path."""
        df = _make_pareto_df(
            [
                {"tpot": 10.0, "ttft": 500.0, "tokens/s/gpu": 800.0, "request_latency": 8000.0},  # meets both
                {"tpot": 12.0, "ttft": 2000.0, "tokens/s/gpu": 1200.0, "request_latency": 9000.0},  # ttft violation
            ]
        )
        result = get_best_configs_under_request_latency_constraint(
            total_gpus=8,
            pareto_df=df,
            target_request_latency=10000.0,
            top_n=5,
            target_ttft=1000.0,
        )
        assert not result.empty
        assert (result["ttft"] <= 1000.0).all(), "All returned configs must meet the TTFT SLA"

    def test_no_ttft_filter_when_not_specified(self):
        """When target_ttft is None, all configs should be considered."""
        df = _make_pareto_df(
            [
                {"tpot": 10.0, "ttft": 500.0, "tokens/s/gpu": 800.0},
                {"tpot": 12.0, "ttft": 2000.0, "tokens/s/gpu": 1200.0},
            ]
        )
        result = get_best_configs_under_tpot_constraint(
            total_gpus=8,
            pareto_df=df,
            target_tpot=15.0,
            top_n=5,
            target_ttft=None,
        )
        assert len(result) == 2, "Without TTFT filter, all TPOT-compliant configs kept"

    def test_ttft_fallback_when_nothing_meets_both(self):
        """When TTFT filter leaves nothing, fall back to unfiltered pareto_df."""
        df = _make_pareto_df(
            [
                {"tpot": 10.0, "ttft": 2000.0, "tokens/s/gpu": 800.0},
                {"tpot": 12.0, "ttft": 3000.0, "tokens/s/gpu": 1200.0},
            ]
        )
        result = get_best_configs_under_tpot_constraint(
            total_gpus=8,
            pareto_df=df,
            target_tpot=15.0,
            top_n=5,
            target_ttft=500.0,
        )
        # TTFT pre-filter finds nothing, so it falls back to the full df.
        # Then TPOT filter passes both. Should still return results.
        assert not result.empty, "Should fall back gracefully when TTFT filter is too strict"
