---
name: match-or-create-issue
description: Given a csv of issues with their error trace, categorize these csvs, and either match or suggest new issues
input: regression.csv, github repo, issues.yaml
output: regression.csv (inplace), actions.csv
---



## Goal
In this project, while engineers commit to the repo, we have identified some regressions – some test cases passed before, but fails now. You have been assigned a file `regression.csv` to work on. The goal is to either match the regression with existing issue in the given repo, or suggest that a new issue should be created.

## Steps

1. If a `MEMORY.md` file exists in the same folder of this `SKILL.md`, read that memory first.
2. Read and understand all the existing issues in `issues.yaml` – these issues are already created. You will be able to see the issue description and the failed cases that these issues are associated to.
3. Read the new regressions in `regressions.csv`. Your task is to update the `regressions.csv` and `issues.yaml`. You should look into the `aiconfigurator` code base in the current directory if needed. For each line in the `regressions.csv`
    1. If it is already in `issues.yaml`, verify that the line in `regressions.csv` still match the issue description in `issues.yaml`, if the body or title does not match the current status, update it.
    2. If it is not in `issues.yaml`
        1. If you can find a match to an existing issue, add it to the issue. Update the `issue_id` field (create a new column if needed) in the csv and update the `failed_cases` field of the yaml.
        2. If you cannot find a match to an existing issue, create a new issue with `issue_id`: `TBD_<#>` where <#> is a temporary number incremental from 0, e.g, TBD_1. Note `issues.yaml` is constantly updating throughtout the current workflow. You should not create distinct numbers for the same issue. Add label `regression` to the issue label. You can add a sample err_msg from csv to yaml if not exist
4. Read through `issues.yaml` to make sure all description, title, failed_cases looks good, and there is no duplication of the issues with the same cause.
5. Read through `issues.yaml`. Focus on each `failed_cases`: if the case is no longer in `regressions.csv`, remove it.
6. Run `test_issues_regressions.py` to check you have successfully completed this task. If test fail, fix your yaml and csv instead of fixing the test file.

## Notes
1. Definition of the "same issue": it may have different error trace, but the root cause should be the same. A.k.a, a single fix PR can apply to all the failed cases in the issue.
2. You may want to checkout to different branches to view the issue (if needed)
3. You should focus on both the main branch and the targeted release branch (as mentioned in `regressions.csv`)
4. Only consider open issues, do not read closed or not planner issues.