# fix-regression — Lessons Learned

Distilled from the autofix run that processed issues #45–#49. 4 of 5 issues needed no code change; only #48 required a new PR. Most time was wasted re-deriving root causes that had already been found.

## Pre-flight checks (do these FIRST, in order)

1. **Grep duplicate issues by error signature.** Before any reproduction, search open + closed issues for the same traceback/error string. Issue #45 was the 4th filing of the same FP8-block MoE alignment bug (#13, #26, #34, #39), and PRs #18 and #31 had already proposed the correct fix and been closed without merge. When duplicates exist with prior AI-agent activity, the correct action is a cross-reference comment and PIC re-ping — not a fresh investigation. SKILL.md step 2.1's "skip if prior AI-agent activity" applies to duplicate issues too.

2. **Verify `FailedBranch` exists.** Run `git ls-remote origin <FailedBranch>`. The support-matrix workflow keeps filing issues against `release/0.8.0`, which does not exist — `main` is already at 0.8.0 per `pyproject.toml`. When the named branch doesn't exist, the failure is historical; the target is "whatever HEAD was before the fix landed." Don't try to check out a non-existent branch.

3. **Run `run_single_test` at HEAD as step zero.** `SupportMatrix.run_single_test(model, system, backend, version)`. If it returns `{agg: True, disagg: True}`, the fix is already on `main` — skip bisection and write a verification comment immediately. This was the whole story for #47 and #49, and most of #46.

## When investigating

- **Trust `systems/data/<sys>/<backend>/<ver>/` contents over `support_matrix.csv`.** The CSV is historical; directories get deleted (e.g., PR #886 dropped `sglang/0.5.8.post1`). If CSV and filesystem disagree, the filesystem wins.

- **Check LFS before concluding perf data is missing.** Perf files (`moe_perf.txt`, etc.) are Git-LFS-tracked. Without `git lfs pull`, they look like ~3-line pointer stubs. Run `wc -l <perf_file>` or check file size — a real perf file is large; a stub is tiny. Grep over a stub returns nothing, which is easy to misread as "the shape is missing" when it's an LFS fetch problem.

- **On a shallow single-commit snapshot, use `git ls-tree origin/main <path>` and `git log -S "<expr>" --all -- <file>`** instead of `git checkout main`. A full checkout of `main` on this 700MB+ repo takes minutes; `ls-tree` and `log -S` are instant and sufficient for provenance. Only spin up a worktree when actually executing code against `main`.

- **`run_single_test` signature varies by commit.** It became a `@staticmethod` on `main` (PR #937) but is an instance method on older snapshots. On `main`: `SupportMatrix.run_single_test(...)`. On older: `SupportMatrix(...).run_single_test(...)`.

## Patterns to mirror

- **Empty nested-defaultdict buckets → `PerfDataNotAvailableError`.** PR #884 established this for `query_custom_allreduce`; PR #50 mirrored it for `query_moe`. Pareto search already catches `PerfDataNotAvailableError` as skip-and-continue. When a sibling `query_*` method shows the same symptom, grep PR #884 and copy the shape. Add unit tests covering `{SILICON raises, HYBRID falls back, present shape works}` per backend.

## Known code landmarks

- **`_infer_quant_modes_from_raw_config` keys off `quant_algo`, not `is_moe`** (`src/aiconfigurator/sdk/models.py:70`). Dense checkpoints with `quant_algo=fp8` still go through MoE quant validation. Answers "why is MoE validation running on a dense model?" without bisecting.

- **`enumerate_parallel_config` in `src/aiconfigurator/sdk/utils.py`** does not consult `weight_block_size`, so it emits `moe_tp` candidates that `_validate_fp8_block_quantized_moe_config` (`models.py:1292`) then rejects. Root cause of the recurring FP8-block MoE log-spam issue. A pre-filter has been proposed twice (PR #18, PR #31) and closed both times without a merge decision.

## When NOT to open a PR

- The issue is a duplicate with a closed-without-merge PR → re-ping the PIC instead.
- `main` already contains the fix → comment with the verification output and fix commits.
- The gap is collected perf data, not code → comment with the `collector/collect.py --backend <b> --ops <op>` command and cc the PIC. Only add a code workaround if the error path itself aborts the whole run (like the bare `IndexError` in #48).
