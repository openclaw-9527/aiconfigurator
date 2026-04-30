# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Regression tests for issue #48.

In SILICON mode, query_moe must raise a structured PerfDataNotAvailableError
when the loaded MoE data does not contain an entry for the requested
(quant_mode, distribution, topk, num_experts, hidden_size, inter_size,
moe_tp_size, moe_ep_size) combination. Previously it leaked an IndexError
from ``token_points[-1]`` (empty defaultdict returned from the chained
lookup), which Pareto search treated as an unexpected invariant failure
instead of skipping the candidate and continuing.
"""

from collections import defaultdict

import pytest
import yaml

from aiconfigurator.sdk import common
from aiconfigurator.sdk.perf_database import PerfDatabase, PerfDataNotAvailableError


def _make_moe_data(shapes):
    """Build a MoE dataset in the same nested defaultdict shape that
    load_moe_data produces, with entries only for the requested
    (topk, num_experts, hidden_size, inter_size, moe_tp, moe_ep) tuples
    under the bfloat16 quant_mode / power_law_1.01 distribution.
    """

    def _nested():
        return defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(
                    lambda: defaultdict(
                        lambda: defaultdict(
                            lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict())))
                        )
                    )
                )
            )
        )

    data = _nested()
    for topk, num_experts, hidden_size, inter_size, moe_tp, moe_ep in shapes:
        for num_tokens in [1, 8, 64, 128, 512]:
            data[common.MoEQuantMode.bfloat16]["power_law_1.01"][topk][num_experts][hidden_size][inter_size][moe_tp][
                moe_ep
            ][num_tokens] = {"latency": 0.01 * num_tokens, "power": 0.0, "energy": 0.0}
    return data


@pytest.fixture
def _db_factory(tmp_path, monkeypatch):
    dummy_spec = {
        "data_dir": "data",
        "misc": {"nccl_version": "v1"},
        "gpu": {
            "bfloat16_tc_flops": 1_000.0,
            "fp8_tc_flops": 2_000.0,
            "fp4_tc_flops": 4_000.0,
            "mem_bw": 100.0,
            "mem_empirical_constant_latency": 1.0,
        },
        "node": {
            "inter_node_bw": 100.0,
            "intra_node_bw": 100.0,
            "num_gpus_per_node": 8,
            "p2p_latency": 0.000001,
        },
    }
    monkeypatch.setattr(yaml, "load", lambda stream, Loader=None: dummy_spec)  # noqa: N803

    def _factory(moe_data, backend="trtllm"):
        monkeypatch.setattr(
            "aiconfigurator.sdk.perf_database.load_moe_data",
            lambda path: (moe_data, None),
        )
        monkeypatch.setattr("aiconfigurator.sdk.perf_database.load_gemm_data", lambda p: {})
        monkeypatch.setattr("aiconfigurator.sdk.perf_database.load_context_attention_data", lambda p: {})
        monkeypatch.setattr("aiconfigurator.sdk.perf_database.load_generation_attention_data", lambda p: {})
        monkeypatch.setattr("aiconfigurator.sdk.perf_database.load_custom_allreduce_data", lambda p: {})
        monkeypatch.setattr("aiconfigurator.sdk.perf_database.load_nccl_data", lambda p: {})
        monkeypatch.setattr("aiconfigurator.sdk.perf_database.load_context_mla_data", lambda p: {})
        monkeypatch.setattr("aiconfigurator.sdk.perf_database.load_generation_mla_data", lambda p: {})
        monkeypatch.setattr("aiconfigurator.sdk.perf_database.load_mla_bmm_data", lambda p: {})
        monkeypatch.setattr("aiconfigurator.sdk.perf_database.load_context_dsa_module_data", lambda p: None)
        monkeypatch.setattr("aiconfigurator.sdk.perf_database.load_generation_dsa_module_data", lambda p: None)

        yaml_file = tmp_path / "sys.yaml"
        yaml_file.write_text("dummy: data")
        return PerfDatabase("sys", backend, "v1", str(tmp_path))

    return _factory


_PRESENT_SHAPE = (6, 128, 2688, 1856, 4, 2)  # (topk, num_experts, hidden, inter, moe_tp, moe_ep)


class TestMoEEmptyShape:
    """SILICON mode must surface empty MoE shape lookups as structured errors."""

    @pytest.mark.parametrize("backend", ["trtllm", "vllm", "sglang"])
    def test_silicon_raises_structured_error_when_tp_shape_missing(self, _db_factory, backend):
        """Reproduces issue #48: data has moe_tp_size in {4} only; a moe_tp_size=8
        query for the same (hidden, inter, topk, num_experts) must raise
        PerfDataNotAvailableError, not leak IndexError from ``token_points[-1]``.
        """
        db = _db_factory(_make_moe_data([_PRESENT_SHAPE]), backend=backend)

        with pytest.raises(PerfDataNotAvailableError) as excinfo:
            db.query_moe(
                num_tokens=128,
                hidden_size=2688,
                inter_size=1856,
                topk=6,
                num_experts=128,
                moe_tp_size=8,
                moe_ep_size=1,
                quant_mode=common.MoEQuantMode.bfloat16,
                workload_distribution="power_law_1.01",
                is_gated=False,
                database_mode=common.DatabaseMode.SILICON,
            )
        msg = str(excinfo.value)
        assert "hidden_size=2688" in msg
        assert "moe_tp_size=8" in msg
        assert "HYBRID" in msg

    @pytest.mark.parametrize("backend", ["trtllm", "vllm", "sglang"])
    def test_hybrid_falls_back_to_empirical_when_shape_missing(self, _db_factory, backend):
        """HYBRID mode must keep falling back cleanly on the same condition."""
        db = _db_factory(_make_moe_data([_PRESENT_SHAPE]), backend=backend)

        result = db.query_moe(
            num_tokens=128,
            hidden_size=2688,
            inter_size=1856,
            topk=6,
            num_experts=128,
            moe_tp_size=8,
            moe_ep_size=1,
            quant_mode=common.MoEQuantMode.bfloat16,
            workload_distribution="power_law_1.01",
            is_gated=False,
            database_mode=common.DatabaseMode.HYBRID,
        )
        assert float(result) > 0, "HYBRID empirical fallback should yield positive latency"

    @pytest.mark.parametrize("backend", ["trtllm", "vllm", "sglang"])
    def test_silicon_available_shape_still_works(self, _db_factory, backend):
        """Sanity check: a shape that IS present still returns an interpolated value."""
        db = _db_factory(_make_moe_data([_PRESENT_SHAPE]), backend=backend)

        result = db.query_moe(
            num_tokens=128,
            hidden_size=2688,
            inter_size=1856,
            topk=6,
            num_experts=128,
            moe_tp_size=4,
            moe_ep_size=2,
            quant_mode=common.MoEQuantMode.bfloat16,
            workload_distribution="power_law_1.01",
            is_gated=False,
            database_mode=common.DatabaseMode.SILICON,
        )
        assert float(result) > 0
