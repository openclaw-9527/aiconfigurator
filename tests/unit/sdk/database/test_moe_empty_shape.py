# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Regression tests for issue #30.

When query_moe hits a (quant_mode, workload_distribution, topk, num_experts,
hidden_size, inter_size, moe_tp_size, moe_ep_size) tuple that has no rows in
moe_perf.txt, the nested defaultdict returns an empty leaf dict. The MFU-based
overflow extrapolator (added in PR #537) then indexes ``token_points[-1]`` on
that empty dict and raises IndexError: list index out of range — leaking an
internal error that Pareto search cannot distinguish from real invariant
failures. This test pins the expected structured PerfDataNotAvailableError.
"""

from collections import defaultdict

import pytest
import yaml

from aiconfigurator.sdk import common
from aiconfigurator.sdk.perf_database import PerfDatabase, PerfDataNotAvailableError


def _make_moe_dataset(covered_tp_ep_pairs):
    """
    Build a MoE dataset in the same 8-deep defaultdict shape that load_moe_data
    produces. Only the (moe_tp, moe_ep) pairs listed are populated; all other
    leaves remain empty defaultdicts that silently materialize on access.
    """

    def _deep():
        return defaultdict(_deep)

    data = _deep()
    quant = common.MoEQuantMode.bfloat16
    dist = "power_law_1.01"
    topk = 6
    num_experts = 128
    hidden_size = 2688
    inter_size = 1856
    for moe_tp, moe_ep in covered_tp_ep_pairs:
        for tokens in [1, 2, 4, 8, 16, 32, 64, 128]:
            data[quant][dist][topk][num_experts][hidden_size][inter_size][moe_tp][moe_ep][tokens] = {
                "latency": 0.01 * tokens,
                "power": 0.0,
                "energy": 0.0,
            }
    return data


@pytest.fixture
def _db_factory(tmp_path, monkeypatch):
    dummy_spec = {
        "data_dir": "data",
        "misc": {"nccl_version": "v1"},
        "gpu": {
            "bfloat16_tc_flops": 1_000.0,
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

    def _factory(moe_data, backend):
        monkeypatch.setattr(
            "aiconfigurator.sdk.perf_database.load_moe_data",
            lambda p: (moe_data, {}),
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


@pytest.mark.parametrize("backend", ["trtllm", "vllm", "sglang"])
def test_silicon_raises_structured_error_when_moe_shape_missing(_db_factory, backend):
    """
    Reproduces issue #30: data exists only for (moe_tp=4, moe_ep=2); a query at
    (moe_tp=8, moe_ep=1) must raise PerfDataNotAvailableError rather than
    IndexError: list index out of range from token_points[-1].
    """
    data = _make_moe_dataset([(4, 2)])
    db = _db_factory(data, backend)

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
            database_mode=common.DatabaseMode.SILICON,
        )

    msg = str(excinfo.value)
    assert "moe_tp_size=8" in msg
    assert "moe_ep_size=1" in msg
    assert "HYBRID" in msg, "error message should point users at the HYBRID workaround"


@pytest.mark.parametrize("backend", ["trtllm", "vllm", "sglang"])
def test_hybrid_falls_back_to_empirical_when_moe_shape_missing(_db_factory, backend):
    """HYBRID mode keeps falling back cleanly on the same condition."""
    data = _make_moe_dataset([(4, 2)])
    db = _db_factory(data, backend)

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
        database_mode=common.DatabaseMode.HYBRID,
    )
    assert float(result) > 0, "HYBRID empirical fallback should yield positive latency"
