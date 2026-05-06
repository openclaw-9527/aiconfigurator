# fix-regression — Lessons Learned

Concise notes from prior autofix runs. Read before starting.

## Diagnosing perf-data regressions (most common failure class)

1. **Trust the LFS blob size, not the pointer diff.** Perf files look
   identical in `git diff` because only pointers are tracked. Run
   `git log -p -- <perf_file>` and scan the `-size` line; a sudden
   MB-scale shrink (e.g. 8.4 MB -> 1.5 MB) is the regression.
2. **First diagnostic = coverage diff across adjacent versions.** Before
   reading any validator code, run
   `awk '{print $8,$9,$10,$11}' moe_perf.txt | sort -u` (or
   `awk -F',' 'NR>1 {print $6}' *_perf.txt | sort -u` for dtype set) on
   the old vs new version. If the failing shape / dtype is absent, it
   is a data gap, not a code bug. The validator traceback already lists
   the supported set - compare against that.
3. **LFS must be pulled before reproducing.** A bare `pip install -e .`
   leaves LFS pointers in place; `PerfDatabase.__init__` swallows load
   failures in `validate()`'s `try`, hiding the real bug behind
   downstream `NoneType.query_*` errors. Always run
   `git lfs pull --include=src/aiconfigurator/systems/data/<sys>/<backend>/<ver>/`
   for the failing cell before trusting the repro.
4. **LFS history is recoverable by commit hash.** For bot-overwritten
   perf files, the prior content is addressable via
   `git show <sha>:<path>` + `git lfs pull`. Prefer surgical row
   extraction (`awk -F',' 'NR==1 || $6=="..."' old > subset; cat subset >> current`)
   to a full revert - keeps newly-added rows intact and produces a
   tiny LFS blob.

## Branch / cross-reference checks

5. **When only one branch is failing, look for a drifted cherry-pick on
   `main`.** A "clean up outdated data" commit on `main` that isn't on
   the release branch is a strong signal the release branch is still
   exposed. Check `git log main -- <path>` for recent cleanups first.

## PIC assignment (fork repos)

6. **Bot-authored regressing commits still need a human PIC.** For
   `dynamo-ops`-authored commits, fall back to: (a) author of the last
   human commit touching the file, (b) author of the equivalent
   cleanup on `main`, (c) author who introduced the now-missing rows.
7. **`gh issue edit --add-assignee` silently no-ops for
   non-collaborators on forks.** Exit status is 0 and the URL is
   returned, but `.assignees` stays empty. Always re-fetch
   (`gh issue view <n> --json assignees`) after assigning and fall back
   to @-mentioning the PIC in the issue comment body - that is the
   reliable notification channel on forks.

## When not to open a PR

8. **Pure data regressions (silicon coverage missing) cannot be patched
   in code.** If the fix requires hardware re-collection, post the
   exact collector command (e.g.
   `python collector/collect.py --backend trtllm --version <v> --ops moe`)
   in the issue comment and hand off to the PIC. Do not fabricate
   data or suppress the error as a "fix".

## Re-runs on already-addressed issues

9. **If the prior run opened a PR that is still awaiting review, do
   NOT re-diagnose or re-post the root cause** — it just adds noise.
   The only productive action is a terse re-ping in the comment body
   on the most-recent-activity thread.
10. **Check PR comments, not just issue comments, for the latest human
    activity.** The issue thread can be stale while the PR thread is
    live. Fastest lookup:
    `gh pr view <n> --json comments --jq '.comments | sort_by(.createdAt) | last'`.
11. **Re-ping comments should include a one-paragraph context recap**
    naming the open reviewer questions, so the reviewer can resolve
    the thread in place without scrolling back through the history.
12. **`wontfix` + "close when branch X exists" is a full short-circuit.**
    If the prior `LOG.md` records an explicit human skip directive
    (e.g. @Harrilee's *"do not fix here, close once `release/0.9.0`
    exists"*), the entire next run collapses to: `gh api
    repos/.../branches/release/X.Y.Z` → expect 404 → log and stop.
    No re-diagnosis, no new comment, no re-ping, no re-assignment.
    Only the gating condition matters; everything else is noise.
13. **Open the run by reading prior `LOG.md` before touching code.**
    Paused issues on re-runs should cite the prior conclusion (PR
    number, directive verbatim, gate) and just re-verify the gate —
    do not re-trace LFS history or re-run validator reproductions
    that were already recorded.
14. **An AI-authored acknowledgement of a human skip directive
    (e.g. "Acknowledged, @X — skipping per your directive") is itself
    the paused state.** Do NOT treat it as stale autofix activity
    needing a re-ping. The thread is correctly parked on human action
    (e.g. cutting `release/0.9.0`); additional automated comments add
    noise and confuse the thread.
