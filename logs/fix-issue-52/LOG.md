# Issue 52
Pics (based on git history): 61184708+changhuaixin@users.noreply.github.com

## Description
Support matrix (on the synthetic `release/0.8.0` branch) reports every combination
of FP8 block-quantized MoE models (`MiniMaxAI/MiniMax-M2.5`,
`Qwen/Qwen3-235B-A22B-FP8`, `Qwen/Qwen3-30B-A3B-FP8`) failing with
`ValueError: Invalid quantized MoE configuration: (moe_intermediate_size / moe_tp_size) % weight_block_size != 0`
from `_validate_fp8_block_quantized_moe_config` in `src/aiconfigurator/sdk/models.py`.
The validator was introduced in commit c7ddbd3 (PR #684) by @changhuaixin.

## Actions Done
- Verified `release/0.8.0` does not exist on the remote; reporter branch is synthetic.
- Pulled LFS data and reran all 18 failing CSV combinations via
  `SupportMatrix.run_single_test` on `main` (both agg and disagg) — every one
  returns a non-empty Pareto (0 real failures).
- Confirmed this is a duplicate of issue #26 (closed as NOT_PLANNED) with a
  corresponding pre-filter fix proposed in PR #31 (also closed, not merged).
- Posted an investigation comment on issue #52 summarizing the findings,
  referencing the prior decision, and pinging @changhuaixin in case the
  NOT_PLANNED decision should be revisited.
- No new PR opened — the underlying validator behavior was already reviewed by
  humans and left unchanged. Reopening that decision is a human call.

## Lessons Learned
- For support-matrix regression reports, always `git lfs pull` before trying to
  reproduce; missing LFS perf-data files surface as the unrelated error
  `'NoneType' object has no attribute 'query_mem_op'`, which can be
  misinterpreted as the reported bug. (My first reproduction run on trtllm
  falsely looked like a real main-branch failure until the LFS files were
  fetched.)
- "Showing last exception: …" in `RuntimeError: No results found for any
  parallel configuration.` is only the last caught exception; it is a red
  herring when most candidates fail for a different reason. Always scan the
  full "Error getting candidate workers" log when diagnosing.
- When a reported `FailedBranch` does not exist on the remote (e.g. synthetic
  `release/0.8.0`), check the most recent real release branch and `main`;
  don't assume the branch name in the issue body is authoritative.
- When a near-duplicate issue was recently closed NOT_PLANNED and the
  accompanying PR was closed-without-merge, the correct action is to point the
  new issue at the prior decision rather than reopening the fix — otherwise
  we'd churn on the same decision with every new synthetic CSV. Worth noting
  in SKILL.md that agents should grep prior issues/PRs for similar stack
  traces before coding a new fix.
