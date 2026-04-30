# Issue 54
Pics (based on git history): simonec@nvidia.com, yimingl@nvidia.com

## Description
Issue #54 reports that Llama-3.1-405B on GB200 fails on `release/0.8.0` for sglang 0.5.9 and vllm 0.14.0 (both agg and disagg) with:
```
AssertionError: values is None or len(values) < 2 Failed to query custom allreduce data for quant_mode=CommQuantMode.half, tp_size=16, size=2097152.0
```
Root cause is the pre-`eba0c74` `query_custom_allreduce` hard-coded `min(tp_size, 8)`. For GB200 (`num_gpus_per_node=4`), the perf CSVs have only `num_gpus=2,4` by design, so tp=16 collapsed to `[quant_mode][8]["AUTO"]` which is an empty `defaultdict`, tripping the assertion in `_nearest_1d_point_helper`.

This is the fifth duplicate of the same problem (prior issues #28, #36, #41, #47 all closed with the same diagnosis).

## Actions Done
No code change made. Verified:
- `release/0.8.0` does not exist on origin (`git ls-remote --heads origin` has no such ref; latest release is `release/0.7.0-post.1`).
- `main` (at `b886aad`) already contains both relevant fixes:
  - `eba0c74` — PR #681 by @simonec, replaces hard-coded `8` with `num_gpus_per_node` in `query_custom_allreduce`.
  - `a8b0934` — PR #884 by @Yimingl, raises `PerfDataNotAvailableError` instead of `AssertionError` when the bucket is empty.
- `git branch --contains eba0c74 -a` and `git branch --contains a8b0934 -a` → only `main` / `origin/main`.
- Ran `SupportMatrix.run_single_test(...)` for all four failing rows on `main`; all return `{'agg': True, 'disagg': True}`.

Left a comment on issue #54 summarizing the situation, pinning @simonec and @Yimingl, and recommending the issue stay open only as a tracker until `release/0.8.0` is actually cut (at which point it will inherit the fix automatically as long as it's branched from post-`a8b0934` main).

No PR needed — no branch exists to cherry-pick into, and `main` is already fixed.

## Lessons Learned
- Always check first whether the `FailedBranch` in the issue body actually exists on origin. Issues #28/#36/#41/#47/#54 all cited `release/0.8.0` which has never existed — that single check short-circuits the entire investigation.
- When the skill runs on a worker branch (`agentic-workflow`) with very few remote refs fetched, `git branch --contains <sha>` returns a misleadingly narrow answer. `git fetch origin main:main` + fetching specific release branches before using `git branch --contains -a` is the quickest way to get a trustworthy picture of which branches still need a fix.
- Before re-analyzing, grep issue titles for the same error signature (`gh issue list --search ...`) to find prior duplicates — their accepted diagnosis usually saves the full repro+bisect cycle. Issue #47's comment already contained the answer for #54.
- `run_single_test` on `main` takes ~30-60s per (model, system, backend, version) quadruple; a 300s timeout is adequate for two backends back-to-back.
