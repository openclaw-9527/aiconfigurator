---
name: fix-regression
description: Given a GitHub issue link, investigate, fix, and send PR to the main branch or update GitHub issue
input: GitHub Issue
output: Issue update (and PR), Log.md
---



## Goal
In this project, while engineers commit to the repo, we have identified some regressions – some test cases passed before, but fails now. You have been assigned one issue to work on. The goals are:

1. Identify the fix if the issue hasn't been addressed
2. Create a PR if necessary
3. No matter wheher a PR is created, update the issue
4. Record the actions into LOG.md

## Steps

1. If a `MEMORY.md` file exists in the same folder of this `SKILL.md`, read that memory first.
2. Read and understand the given issue from GitHub, including the conversation/threads under that issue, have an overall idea of the problem.
    1. If the issue was addressed by AI Agent (you), but hasn't been commented/updated by human engineer. Pin the PIC for this issue again in the thread. Do not do redundant analysis again.
    2. If a PR already exists in the issue thread, you should check that PR as well
3. Traverse the git history, find out which commit has introduced this regression (note: you should not trust `support_matrix.csv` in any commit, as the file is highly likely outdated). Instead, you should try the test case (with util script at `tools/support_matrix/support_matrix.py`, function `run_single_test`) and find out the cause.
4. Compare the ToT main or release branch (depends on which branch has regression, prioritize main), suggest a fix if possible
    1. If a fix is possible, compose a fix and submit a PR to the main branch. In the PR, @(mention) the people whose commit has introduced this regression, and mention the issue in the PR
    2. If a fix is not possible due to the following reason:
        1. If the performance database (txt file) is broken, mention that in the oringal github issue, @(mention) the people whose commit has introduced this regression. Note: you should specify what ops (in `--ops` param for `collector/collect.py`) for which backend/version/hardware is needed; also, you may need to draft a PR if the collector itself needs to be modified.
        2. If the problem is too complicated, mentioned that why this issue cannot be fixed, or mention that some critical decisions should be made by human engineer in the original issue
5. Craete a `LOG.md` file with the following tempalate
```markdown
# Issue <!-- issue_id -->
## Description
<!-- summary of the issue -->
## Actions Done
<!-- summary of the fix proposed (PR), or mention that why the issue cannot be fixed by you  -->
## Lessons Learned
<!-- only include the ideas you think that would benefit you to fix the problem faster next time, what you want to change/update about the current SKILLS.md, you may include the lessons learned from human input on the issue/PR feedback -->
```
6. Verify the workflow has suceeded by
    1. `LOG.md` is present
    2. GitHub isseue is updated (no matter the previous commment was replied by human or not)
    3. GitHub PR is updated (only if you have applied a fix)
    Then, end the workflow

## Notes
1. You may want to do `pip install -e .` so that you can use the same workspace while checking out to different commits
2. The only allowed labels are: `regression` and `bug`. Do not create additional labels.
3. If a regression only happens in release branch but not main branch. It suggests that a fix may already be available. You should mention in the issue that which commit to cherry-pick (you may test it locally to make sure it works.)