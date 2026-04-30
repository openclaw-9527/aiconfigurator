# Issue 55

Pics (based on git history):
- jasonzho@nvidia.com (introduced `_supported_or_raise` in #183 / commit `e996997`)
- 49143331+tianhaox@users.noreply.github.com (introduced quant inference from model config in #338 / commit `ae7ece3`)

## Description
`TaskConfig.validate` rejects `nvidia/Llama-3.1-70B-Instruct-FP8` on `(b60, vllm, 0.12.0)` with `Unsupported moe quant mode 'fp8'` even though the model is dense and never exercises the MoE op. `_apply_model_quant_defaults` / `_infer_quant_modes_from_raw_config` infers `moe_quant_mode=fp8` from the HF `quant_algo`, and `_supported_or_raise("moe", ...)` then compares it against the moe perf table for that backend/version. When the moe perf table lacks `fp8` rows (as in the reported state of `b60/vllm/0.12.0`), the validator raises.

## Actions Done
- Opened PR #57 against `main` (branch `fix/issue-55-dense-fp8-moe-validation`): gate the MoE branch of `_validate_worker_config` on `check_is_moe(self.model_path)` so dense models skip MoE quant-mode validation entirely. MoE models still hit the full check (including sglang `deepep_moe` / `wideep_*` branches).
- Added two unit tests in `tests/unit/sdk/task/test_task.py`:
  - `test_taskconfig_skips_moe_validation_for_dense_model` — dense fp8 Llama with `moe: [bfloat16]` validates cleanly.
  - `test_taskconfig_still_validates_moe_for_moe_model` — MoE model with unsupported `fp8` moe dtype still raises.
- Verified locally: 42/42 unit tests pass; `SupportMatrix.run_single_test('nvidia/Llama-3.1-70B-Instruct-FP8', 'b60', 'vllm', '0.12.0')` returns `agg=True, disagg=True`.
- Posted a root-cause + action summary on issue #55, cc'ing the PICs.

## Lessons Learned
- A previous AI-authored PR (#25, for the now-deleted issue #24) carried the identical fix but was closed without review. When the issue resurfaces under a new number, re-submit the same fix with a reference to the prior PR rather than re-deriving from scratch. The SKILL instruction "do not do redundant analysis again" applies across issue renumbering too.
- The issue's `FailedBranch: release/0.8.0` did not correspond to any actual git branch; the current working branch (`agentic-workflow`, `pyproject.toml` version 0.8.0) is the repo's surrogate for that release. Worth checking `pyproject.toml` version rather than assuming a `release/x.y.z` branch always exists.
- `_supported_or_raise` silently no-ops when the system's perf DB fails to load (returns an empty `supported_quant_mode`). Reproduction required `git lfs pull` for the `systems/data/b60/vllm/0.12.0/*` files; without them the validator never raises and the repro looks unrelated. Good to remember to `git lfs pull` for any validation-path repro that hits `get_database`.
- The underlying regression was a two-PR composition (#183 validation + #338 inference), each correct in isolation. When reporting, cc both authors rather than hunting for "the" introducing commit.
