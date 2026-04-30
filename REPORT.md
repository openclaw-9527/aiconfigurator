# Autofix Run Report

## Summary

* regressions-processed: 5
* issues-updated: 5
* issues-created: 0
* issues-closed: 0
* prs-created: 1

| Issue | Outcome | PR |
|---|---|---|
| #52 FP8 block-quant MoE validator rejects MiniMax/Qwen3 | Triage comment; duplicate of #26 (NOT_PLANNED) — human call required | — |
| #53 h100_sxm/sglang/0.5.9 perf data missing on release/0.8.0 | Triage comment; fixed on `main`, `release/0.8.0` not on origin (no cherry-pick target) | — |
| #54 Llama-3.1-405B GB200 custom-allreduce AssertionError | Triage comment; fixed on `main` by PRs #681 + #884, no cherry-pick target | — |
| #55 Dense FP8 Llama rejected by MoE quant validator | Fix opened | [#57](https://github.com/openclaw-9527/aiconfigurator/pull/57) |
| #56 MoE MFU extrapolator IndexError on empty leaf | Triage comment; 4th recurrence, prior PRs #19/#32/#44/#50 closed without merge — human call | — |

## How Can I Do Better

- **Precomputed duplicate-issue index.** 4 of 5 issues this run were duplicates of prior issues (#26 → #52, #40/#46 → #53, #28/#36/#41/#47 → #54, #30/#43/#48 → #56). A pre-built map from error signature → prior issue/PR/decision would cut investigation to a single lookup. Today I re-derived it with `gh issue list --search` per run.
- **Branch existence preflight.** Every issue cited `FailedBranch: release/0.8.0` which does not exist on origin. A one-shot preflight (`git ls-remote --heads origin | grep release`) at the start of the matrix, with results attached to every child issue, would save a per-child check.
- **LFS fetch baked into the runner.** Two separate LOGs (#52, #56) report that missing LFS perf files silently produced misleading errors (`'NoneType' object has no attribute 'query_mem_op'`, `KeyError: 'quant_dtype'`). A guaranteed `git lfs pull --include="src/aiconfigurator/systems/data/<system>/**"` before any reproduction attempt would eliminate that entire class of red-herring.
- **GitHub token in the skill env.** `gh` was not authenticated in this run (no `GH_TOKEN`/`GITHUB_TOKEN` exposed), so I could not verify issue/PR titles, prior comments, or `stateReason` via the API before replying. Everything had to be inferred from the LOGs. A scoped token would let me trust-but-verify before commenting.
- **GPU access for data-side regressions.** Issue #56 needs the `collector/collect.py --ops moe` run for the `(hidden=2688, inter=1856, topk=6, experts=128, moe_tp=8, moe_ep=1)` shape to close the loop. Without a GPU, the best I can do is flag it for humans. A GPU slot tied to the autofix matrix would let me close data-gap regressions end-to-end.
- **Sticky "NOT_PLANNED policy" memory.** The same error signature keeps getting re-filed and the accompanying PRs keep getting closed without merge (issue #56: 4 iterations; issue #52: 2). Persisting the maintainer decision in a durable, per-skill memory would stop the churn on the AI side.

## Lessons Learned

1. **Duplicate check is mandatory before any repro/coding.** `gh issue list --state all --search "<error signature>"` and `gh pr list --state all --search "<topic>"` before touching code. 4 of 5 issues this run had a prior AI-authored fix or decision; re-deriving the analysis wasted cycles on #52/#53/#54/#56. `stateReason: NOT_PLANNED` on an auto-filed regression is a hard stop — maintainer has explicitly declined that class of fix.
2. **Always verify the `FailedBranch` exists on origin before planning a cherry-pick.** `git ls-remote --heads origin | grep release/` or `gh api repos/<owner>/<repo>/branches`. Every single issue this run cited `release/0.8.0` which does not exist on origin; the repo's surrogate for that release is the current `agentic-workflow` / `main` branch (ground truth: `pyproject.toml` `version`). Catching this first short-circuits the whole investigation.
3. **`git lfs pull` before any reproduction.** LFS pointer stubs masquerade as valid files and produce misleading errors (`'NoneType' object has no attribute 'query_mem_op'`, `KeyError: 'quant_dtype'`, `KeyError: 256`). Run `git lfs pull --include="src/aiconfigurator/systems/data/<system>/**"` first, or `head -2` the CSVs to check for `version https://git-lfs.github.com/spec/v1`.
4. **`run_single_test` is an instance method** — use `SupportMatrix().run_single_test(model, system, backend, version)`. Takes ~30-60s per quadruple; 300s timeout covers both backends.
5. **Don't fixate on "Showing last exception" in `RuntimeError: No results found for any parallel configuration.`** — it's the last caught exception, a red herring when most candidates fail for another reason. Scan the full "Error getting candidate workers" log.
6. **Regressions can be two-PR compositions** (e.g. #55: validator PR #183 + inference PR #338, each correct in isolation). Cc both authors rather than hunting for "the" introducing commit.
7. **For data-only regressions that reproduce only on a release branch, the fix is branch sync (cherry-pick), not collector re-runs.** Call this out in the comment so reviewers don't waste a GPU slot on `collector/collect.py` when the data already exists on `main`.
