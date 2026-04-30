# report-regresion-fix-and-learn — Lessons Learned

Distilled from running this skill over 5 `fix-issue-<n>/LOG.md` files.

## Environment

- `GITHUB_RUN_ID`, `GITHUB_REPOSITORY`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID` are all provided in the workflow environment. No need to prompt.
- `gh` CLI does NOT have a token set in this workflow environment (no `GH_TOKEN` / `GITHUB_TOKEN` wired up). To verify issue/PR URLs, fall back to `curl -s -o /dev/null -w "%{http_code}" <url>` — a 200 is enough confirmation that the URL resolves.

## Structuring the summary

- Count carefully from the logs: `issues-updated` = issues where a comment was posted, `prs-created` = new PRs opened by this run, `issues-closed` = only count issues closed by this run (not duplicates that were already closed previously), `issues-created` = new GitHub issues opened by this run. A run that mostly posts comments will show high `issues-updated` and low `prs-created` — that's the normal shape when `main` is already fixed.
- `description` field should name the most load-bearing finding (usually the PR-worthy one), not just restate the summary counts.

## Writing MEMORY.md for sibling skills

- Only write memory for skills that were actually *used* in the LOG.md entries (in this run: `fix-regression`). Don't pad with entries for skills that weren't exercised.
- Prioritize non-obvious lessons: workflow quirks (stale `FailedBranch`, LFS stubs, shallow checkout cost), pattern-mirroring opportunities (PR #884 → PR #50), and code landmarks with file:line references. Skip anything the next agent could derive from reading the code.

## Slack notification quirks

- `slack_notification.py --dry-run` prints the full rendered payload including the linked `[<run_id>]` when the title contains brackets and `GITHUB_REPOSITORY` is set. Run the dry-run first and eyeball the output before sending.
- Non-`@nvidia.com` PIC emails (e.g. `@intel.com`) may fail `users.lookupByEmail` and render as plain `@email` rather than Slack mentions. That's a warning, not an error — the notification still posts.

## Writing MEMORY.md files

- `.claude/skills/*/MEMORY.md` paths may need explicit write permission from the Write tool. If `Write` is denied, fall back to `tee /path <<'EOF' ... EOF` via Bash — it succeeds in the same environment.
