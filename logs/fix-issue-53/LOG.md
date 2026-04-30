# Issue 53
Pics (based on git history): harrli@nvidia.com, 49143331+tianhaox@users.noreply.github.com, 170655669+dynamo-ops@users.noreply.github.com

## Description
Support-matrix runs for `h100_sxm / sglang / 0.5.9` on `release/0.8.0` fail with `KeyError: 256` that surfaces as `Error loading silicon data for op PerfDataFilename.gemm: File does not exist ...`. The reporter concluded that the `src/aiconfigurator/systems/data/h100_sxm/sglang/0.5.9/` directory is absent on `release/0.8.0`. Affects a large matrix of Qwen3 / Llama-3.1 / MiMo / Nemotron agg+disagg cases.

## Actions Done
- Confirmed the 13 required perf files all exist on `main` (b886aad) under `src/aiconfigurator/systems/data/h100_sxm/sglang/0.5.9/`.
- Ran `SupportMatrix().run_single_test('Qwen/Qwen3-0.6B', 'h100_sxm', 'sglang', '0.5.9')` on `main` and got `{'agg': True, 'disagg': True}` — the failure does not reproduce on main.
- Traced the data provenance on main to PRs #629 (collector data), #738 (QWEN 3.5 SILICON), #757 (KIMI K-2.5 SILICON), and #895 (bfloat16 rename) — i.e., the same commits flagged by the closed duplicates #46 and #40.
- Confirmed via `gh api repos/openclaw-9527/aiconfigurator/branches` that **`release/0.8.0` does not exist on origin** (release branches stop at `release/0.7.0-post.1`). Therefore no cherry-pick PR is possible at this time.
- Posted a summary/root-cause/next-step comment on issue #53 mentioning @Harrilee and @tianhaox, pointing them at the cherry-pick plan once `release/0.8.0` is cut, and asking them to verify whether the support-matrix CI is targeting a branch that is not visible on the public remote.
- No PR opened on `main` (already fixed) and no cherry-pick PR (target branch missing).

## Lessons Learned
- Issues #40, #46 and #53 all describe the same `h100_sxm/sglang/0.5.9` perf-data gap against `release/0.8.0`. Before diving in, check the issue list for recent duplicates (`gh issue list ... --state all`) — the earlier triage notes can be reused almost verbatim and save a full re-analysis.
- Always verify the target branch actually exists on the remote (`gh api .../branches`) before planning a cherry-pick. The issue body can reference a branch that hasn't been cut yet; the SKILL.md's cherry-pick path assumes the branch exists.
- `run_single_test` is an instance method (`SupportMatrix().run_single_test(...)`), not a staticmethod/classmethod as PR #937 suggested for future work. Use `sm = SupportMatrix(); sm.run_single_test(...)` in reproducers.
- When data-only regressions reproduce only on a release branch, the fix is branch sync (cherry-pick), not collector re-runs — explicitly call this out in the comment so reviewers don't waste a GPU slot on `collector/collect.py`.
