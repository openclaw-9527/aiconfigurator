# Issue 56
Pics (based on git history): kimiz@nvidia.com (commit b5369e1, PR #537 introduced the `token_points[-1]` call that crashes on the empty-leaf case)

## Description
`tools/support_matrix/support_matrix.py` on `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16` / `h100_sxm` for both `trtllm 1.2.0rc5` and `vllm 0.14.0` (agg + disagg) logs `IndexError: list index out of range` inside `PerfDatabase.query_moe → get_silicon`. The nested `moe_data` defaultdict returns an empty leaf for the requested `(hidden=2688, inter=1856, topk=6, experts=128, moe_tp=8, moe_ep=1)` — that shape is collected for `moe_tp ∈ {1,2,4}` but not `moe_tp=8`. The MFU overflow extrapolator added in #537 calls `sorted(moe_dict.keys())[-1]` on that empty dict and raises `IndexError` instead of a structured `PerfDataNotAvailableError`. On current `main` (v0.8.0) the Pareto sweep still returns `{agg: True, disagg: True}` because other parallel configs carry it; the `IndexError` surfaces only as noisy tracebacks.

## Actions Done
No PR opened this round. This issue is the 4th recurrence of the same failure: #30, #43, #48 were all closed as `NOT_PLANNED` on 2026-04-30, and the four code-hardening PRs (#19, #32, #44, #50) were all closed without merge. Per skill guidance ("do not redo analysis when a prior AI fix is pending human review"), I posted a triage comment on #56 ([link](https://github.com/openclaw-9527/aiconfigurator/issues/56#issuecomment-4351142337)) that:
- Summarizes root cause and links the prior closed issues/PRs
- Shows the current `main` reproduction result (test passes with noisy tracebacks after `git lfs pull`)
- Flags that the preferred direction is ambiguous (code hardening vs. data collection) and needs a human call
- Pings @kimiz-nv (author of the offending commit) and @harrli (added an equivalent empty-leaf guard for the nvfp4 low-latency path in 507f0fb, regular path still missing it)
- Provides the `collector/collect.py --backend {trtllm,vllm} --ops moe` command for the data-side path

## Lessons Learned
- Before writing a fix, check `gh pr list --state all --search <topic>` for prior attempts. I would have filed a fifth duplicate PR without that check. The issue template (auto-filed regressions) doesn't link to prior duplicates — the AI has to find them.
- `stateReason: NOT_PLANNED` on an auto-filed regression issue is a strong "maintainers explicitly chose not to merge this class of fix" signal, not a "nobody looked at it" signal. Pattern: filer is `github-actions`, closer is human, no comments → maintainer has seen and declined. Treat as a hard stop.
- Data-dependent tests (LFS-backed perf CSVs) will silently misbehave if `git lfs pull` hasn't run — the data files look valid as text but are pointer stubs. My first repro attempt hit `KeyError: 'quant_dtype'` from `load_compute_scale_data` because `computescale_perf.txt` was a 3-line LFS pointer. Worth adding to the skill: run `git lfs pull --include="src/aiconfigurator/systems/data/<system>/**"` before any reproduction attempt, or at least `head -2` the relevant CSVs to check for `version https://git-lfs.github.com/spec/v1`.
- Reported `FailedBranch` values ending in a version tag that isn't in the remote (here `release/0.8.0`) are usually aliases for `main` at that version — `pyproject.toml` `version` is the ground truth. Checking `git ls-remote --heads origin | grep release` first saves a fetch.
