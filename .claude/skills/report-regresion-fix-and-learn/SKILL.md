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
3. Generate a Slack incoming-webhook JSON body. Create a `notification.json` file that Slack can post directly.
Use this exact payload structure:
```json
{
    "title": "Autofix Run Notification [${GITHUB_RUN_ID}]",
    "summary": "<one line summary>",
    "pics": "<list all the emails of PIC, such as 'person_a@nvidia.com, person_b@nvidia.com'>",
    "details": "<a full multiline paragraph to summarize the issues and PRs, see example below>"
}
```
Example for details:
```plaintext
1. Issue #11: b60/vllm/0.12.0 rejects FP8 MoE quant mode (supported modes: ['float16']).\n
· Issue: https://github.com/openclaw-9527/aiconfigurator/issues/10\n
· PR: https://github.com/openclaw-9527/aiconfigurator/pull/11
cc person_a@nvidia.com person_b@nvidia.com\n
\n\n
2. Issue #10
· Custom allreduce perf data missing for tp_size=16 on gb200 (Llama-3.1-405B)
· Issue: https://github.com/openclaw-9527/aiconfigurator/issues/10
cc person_a@nvidia.com person_c@nvidia.com
```
4. Make sure that all the links above exist. If a link does not exist, remove or correct it before sending. Keep the payload structure exactly as shown above.
5. Send the json payload to `SLACK_WEBHOOK_URL` env var (if no issue/pr updates, do not send it)
6. Generate a `REPORT.md` based on the following template
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
7. Make sure the REPORT.md is present
8. For each skills used in `.claude/skills`, create or update a `MEMORY.md` file with the "## Lessons Learned" section you wrote. Create a PR to `agentic-workflow` with these changes.