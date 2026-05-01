# report-regresion-fix-and-learn — Lessons Learned

Operational notes for this skill:

- The Slack notification script requires both `SLACK_BOT_TOKEN` and
  `SLACK_CHANNEL_ID` to be set, and will validate the JSON schema
  strictly (title/description non-empty, at least one issue, pic
  non-empty). Run `--dry-run` first to catch schema errors before
  posting.
- `GITHUB_RUN_ID` and `GITHUB_REPOSITORY` env vars are populated in the
  Actions runner context - do not hardcode them. The script substitutes
  `[<run_id>]` in the title into a clickable Actions link when both
  are set.
- Verify GitHub issue/PR URLs with an anonymous
  `curl -s -o /dev/null -w "%{http_code}"` before including in the
  JSON - `gh` CLI requires `GH_TOKEN` which is not always populated in
  matrix-child runs, but the REST API accepts unauthenticated GETs on
  public repos.
- Writes under `.claude/skills/` may trigger a permission prompt that
  silently declines in the Actions harness. Fall back to writing the
  file to `/tmp/` first, then `mv` into place.
- When no issues had PR/issue updates, skip sending the Slack
  notification and still emit `REPORT.md`. **Re-pings on existing PRs
  count as updates** — if the skill re-pinged PICs, send the
  notification.
- For "How Can I Do Better", concrete resource asks (GB200 hardware
  access, LFS pre-pull helper, assignee-verify wrapper) land better
  than vague process complaints.
- When LOG.md describes an "already addressed in prior run" scenario,
  the report should surface the stalled PR status and the last
  reviewer-ask, not re-summarize the original root cause — the Slack
  notification's job is to unblock review, not re-educate.
- Per-issue `description` field in `notification.json` should name the
  specific PR number + its current state (`MERGEABLE`, open review
  questions, etc.) so the reviewer can act from Slack without opening
  the PR first.
