---
name: report-regresion-fix-and-learn
description: Given a set of LOG.md from previous fixes, summarize the file in to a REPORT and notification.json
input: Log.md
output: REPORT.md, notification.json, SKILLS.md
---

# Goal

Before this task, there was a huge amount of effort that was done in fixing the regression issues. All the previous efforts are present in `LOG.md`. Your task is to generate a `REPORT.md` for a summary from all the `LOG.md`, a Slack notification for PICs to review, and update `MEMORY.md` for each task based on the feedback from the previous logs.

# Steps

1. If a `MEMORY.md` file exists in the same folder of this `SKILL.md`, read that memory first.
2. Read through all `LOG.md` presented.
3. Generate a structured Slack notification file at `notification.json`.

Required environment variables:
- `SLACK_BOT_TOKEN`: Slack bot token used in the `Authorization: Bearer` header.
- `SLACK_CHANNEL_ID`: Slack channel ID to post into.

Use this exact payload structure for `notification.json`:
```json
{
    "title": "Autofix Run [<value of GITHUB_RUN_ID>]",
    "description": "<one line summary>",
    "issues": [
        {
            "title": "<issue title>",
            "description": "<issue-specific summary>",
            "issue": "<GitHub issue URL, or empty string if none>",
            "pr": "<GitHub PR URL, or empty string if none>",
            "pic": "<PIC email(s), such as 'person_a@nvidia.com, person_b@nvidia.com'>"
        }
    ]
}
```

Do not write the literal string `${GITHUB_RUN_ID}` into `notification.json`. Use the actual workflow run ID from the `GITHUB_RUN_ID` environment variable.

Example:
```json
{
    "title": "Autofix Run [123456789]",
    "description": "2 issues updated, 2 issues created, 1 PR created, 2 issues closed, 5 issues was not responded",
    "issues": [
        {
            "title": "FP8 MoE quant mode rejected",
            "description": "b60/vllm/0.12.0 rejects FP8 MoE quant mode (supported modes: ['float16']).",
            "issue": "https://github.com/openclaw-9527/aiconfigurator/issues/10",
            "pr": "https://github.com/openclaw-9527/aiconfigurator/pull/11",
            "pic": "person_a@nvidia.com, person_b@nvidia.com"
        },
        {
            "title": "Missing custom allreduce perf data",
            "description": "Custom allreduce perf data missing for tp_size=16 on gb200 (Llama-3.1-405B).",
            "issue": "https://github.com/openclaw-9527/aiconfigurator/issues/10",
            "pr": "",
            "pic": "person_a@nvidia.com, person_c@nvidia.com"
        }
    ]
}
```

4. Make sure that all issue and PR links above exist. If a link does not exist, remove or correct it before sending. Keep the payload structure exactly as shown above.
5. Validate the JSON with `--dry-run`:
```bash
python .claude/skills/report-regresion-fix-and-learn/slack_notification.py notification.json --dry-run
```
6. Send the notification to Slack with `slack_notification.py` (if no issue/pr updates, do not send it):
```bash
python .claude/skills/report-regresion-fix-and-learn/slack_notification.py notification.json
```
The script posts `title` and `description` as the parent message, then posts each entry in `issues` as a separate threaded reply. Each issue reply renders the issue `title` in bold, the issue `description` in italic, and the `issue` URL as a `#<issue_id>` link. It resolves each `pic` email to a Slack mention when possible.
When `title` contains `[${GITHUB_RUN_ID}]`, the script links that bracketed run ID to the GitHub Actions workflow run using `GITHUB_REPOSITORY`.
7. Generate a `REPORT.md` based on the following template
```markdown
# Autofix Run Report

## Summary

* regressions-processed: <#>
* issues-updated: <#>
* issues-created: <#>
* issues-closed: <#>
* prs-created: <#>


## How Can I Do Better
<!--
This part is your wishlist.
For example, can you further resolve the problem if given a auto-collector pipeline, or you are given a GPU machine?
Please briefly list your "wishlist" and a short justification. We will try to provide you with more resources next time.
-->

## Lessons Learned
<!--
Illustrate what are the lessons you learned that could benefit you if you run the workflow again. For example,
1. if you spent too much time on how to install the pkg or run one particular experiment, this should be recorded
2. if you find some util scipt useful, record it
-->
```
8. Make sure the REPORT.md is present
9. For each skills used in `.claude/skills`, create or update a `MEMORY.md` file with the "## Lessons Learned" section you wrote. Create a PR to `agentic-workflow` with these changes. The memories should be concise, only include the most important information that you believe that will be helpful for a run next time.