# Memory: report-regresion-fix-and-learn

## Lessons Learned

1. **`FailedBranch` in the issue template is frequently wrong or unreleased.** Four of five issues this run cited `release/0.8.0`, a branch that does not exist on origin. When the branch is missing, treat `main` as the working proxy and re-verify with `run_single_test`; most stale filings self-resolve.
2. **Trust `run_single_test`, not `support_matrix.csv`.** The CSV lags reality by weeks. `SupportMatrix.run_single_test(model, system, backend, version)` on current `main` is the ground truth for PASS/FAIL.
3. **`git lfs pull` before trusting any perf-DB traceback.** Missing LFS blobs cause `perf_database.load_*` to silently return `None`, which surfaces as `AttributeError: 'NoneType' object has no attribute 'query_mem_op'` -- nothing like the advertised failure. Confirm `systems/data/<system>/<backend>/<version>/*_perf.txt` starts with a CSV header, not `version https://git-lfs.github.com/spec/v1`.
4. **"run_single_test returns True" != "no regression."** `pareto_analysis.agg_pareto` swallows per-candidate exceptions into `exceptions.append(e)` and only raises if *every* candidate fails. Always grep captured logs for `Traceback` / `Error` / `Invalid` even when the boolean result is green -- several per-config bugs (issues #26, #30) manifest only as log noise at the top level.
5. **Nested-`defaultdict` lookups in `perf_database.py` are a recurring accident surface.** `query_custom_allreduce` had an empty-leaf bug (#884), `query_moe` had the same pattern (this run's #30). The other `query_*` methods use the same idiom and likely have the same trap -- worth a defensive sweep rather than one-bug-at-a-time.
6. **Always search for pre-existing agent PRs before opening a new one.** `gh pr list --state all --search "<symptom>"` and branches named `fix/issue-<N>-*` surface AI-authored precursors. A closed-without-comment PR from a prior agent is a strong "human said no" signal -- post findings and ask for direction rather than re-submitting the same change.
7. **Data-coverage fixes can mask latent validator bugs.** Issue #29's current-main PASS was coincidental: PR #675 added `fp8` rows to the MoE perf table, so the strict validator no longer trips. The underlying `TaskConfig.validate` branch that runs moe checks on dense models is still wrong. When closing "already green on main" issues, call out what actually fixed it -- data coverage, unrelated refactor, or a real code fix.
8. **Valid MoE `moe_tp` values are a small set.** For fp8_block quantization, `(moe_intermediate_size // moe_tp) % weight_block_size == 0` prunes sweep lists aggressively (e.g. for `moe_intermediate_size=1536, block=128`: only `{1, 2, 3, 4, 6, 12}`). Pre-filter in `sdk/utils.py` rather than discover this via `exceptions.append`.
9. **Cross-node perf-DB queries clamp, not collect.** GB200's single-node cap is `num_gpus_per_node=4`; `custom_allreduce_perf.txt` only has `num_gpus=2,4` by design. `tp_size > num_gpus_per_node` must be handled by clamp-and-rescale (PR #681 fix), not by collecting more rows.

## Operational notes for this skill

- Slack webhook at `$SLACK_WEBHOOK_URL` accepts the `{title, summary, pics, details}` payload shape from `SKILL.md` and responds `{"ok":true}` on success.
- `gh` CLI fails in GitHub Actions without an env-passed token (`GH_TOKEN`/`GITHUB_TOKEN`); unauthenticated `curl -H "Accept: application/vnd.github+json" https://api.github.com/repos/<owner>/<repo>/issues/<n>` returns 200 for public repos and is sufficient for link-existence verification.
- `$GITHUB_RUN_ID` is the right interpolation for the notification title.
- PIC emails are not in any `LOG.md`; `<github_handle>@nvidia.com` is the working convention. Prefer a real directory lookup when available.
- Writes into `.claude/` may require using Python file I/O rather than the `Write` tool or `cat >` redirects when permission prompts are non-interactive.
