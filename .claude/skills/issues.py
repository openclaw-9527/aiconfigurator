"""Generic GitHub-issue helpers backed by the `gh` CLI.

This module is intentionally schema-agnostic: it knows how to load, list,
and save issues, but does not parse the body into structured fields.
Issue types with a templated body should subclass `Issue` and override
the `_parse_body`, `_render_body`, and `validate` hooks (see
`categorize-issues/regression_issue.py` for an example).
"""

import json
import subprocess
import sys
from typing import ClassVar


class IssueNotFoundError(Exception):
    """Raised when an issue cannot be fetched from GitHub (missing or no access)."""


class MalformedIssueError(Exception):
    """Raised when an issue body does not match its expected schema."""


class GhCommandError(Exception):
    """Raised when a `gh` CLI invocation fails. Wraps the gh stderr message
    without dumping the (often huge) command arguments into the traceback.
    """


def _run_gh(cmd: list[str]) -> str:
    """Run a `gh` command and return stdout.

    Raises `GhCommandError` with a short, readable message instead of the
    default `subprocess.CalledProcessError`, which would echo the full
    `--body` argument (potentially many KB of issue text) into the traceback.
    Raises `IssueNotFoundError` when `gh` itself is missing.
    """
    try:
        result = subprocess.run(
            cmd,
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as e:
        raise IssueNotFoundError("The `gh` CLI is not installed or not on PATH.") from e

    if result.returncode != 0:
        # Show only the first ~5 cmd args so the body argument never appears.
        head = " ".join(cmd[: min(5, len(cmd))])
        stderr = (result.stderr or "").strip() or "(no stderr)"
        raise GhCommandError(f"`{head} ...` exited {result.returncode}: {stderr}")
    return result.stdout


class Issue:
    """A GitHub issue, decoupled from any particular body schema.

    Subclasses customize body handling by overriding three hooks:

    - `_parse_body(self)` — populate structured fields from `self.body`.
      Called automatically at the end of `__init__`.
    - `_render_body(self) -> str` — produce the body string used by
      `save()`. Defaults to returning `self.body` unchanged.
    - `validate(self) -> None` — raise `MalformedIssueError` when `self.body`
      doesn't match the subclass's schema. Defaults to a no-op. Called
      automatically by `from_id`.
    """

    def __init__(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
        issue_id: int | None = None,
        repo: str | None = None,
    ):
        self.issue_id = issue_id
        self.title = title
        self.labels = list(labels or [])
        self.body = body
        # GitHub repo this issue lives in (or should be created in).
        # When None, `gh` falls back to `gh repo set-default` / GH_REPO env.
        self.repo = repo
        self._parse_body()

    # ---- hooks for subclasses -----------------------------------------------

    def _parse_body(self) -> None:
        """Populate structured fields from `self.body`. Default no-op."""

    def _render_body(self) -> str:
        """Return the body string written to GitHub by `save()`. Default: `self.body`."""
        return self.body

    def validate(self) -> None:
        """Raise MalformedIssueError if `self.body` doesn't match the schema. Default no-op."""

    # ---- generic helpers ----------------------------------------------------

    def __repr__(self) -> str:
        issue_ref = f"#{self.issue_id}" if self.issue_id is not None else "<unsaved>"
        return f"{type(self).__name__}({issue_ref}, title={self.title!r})"

    def to_dict(self) -> dict:
        """Return a JSON/YAML-serializable representation of the issue.

        Subclasses with structured fields should override and merge in
        their extras (e.g. `return {**super().to_dict(), "failed_cases": ...}`).
        """
        return {
            "issue_id": self.issue_id,
            "repo": self.repo,
            "title": self.title,
            "labels": list(self.labels),
            "body": self.body,
        }

    # ---- gh CLI integration -------------------------------------------------

    @classmethod
    def from_id(cls, issue_id: int, repo: str | None = None) -> "Issue":
        """Load an existing GitHub issue by number via the `gh` CLI.

        Raises:
            IssueNotFoundError: if `gh` cannot fetch the issue.
            MalformedIssueError: if the subclass's `validate()` rejects the body.
        """
        cmd = [
            "gh",
            "issue",
            "view",
            str(issue_id),
            "--json",
            "number,title,body,labels",
        ]
        if repo:
            cmd.extend(["--repo", repo])

        try:
            raw = _run_gh(cmd)
        except GhCommandError as e:
            raise IssueNotFoundError(
                f"Could not fetch issue #{issue_id}" + (f" from {repo}" if repo else "") + f": {e}"
            ) from e

        try:
            item = json.loads(raw)
        except json.JSONDecodeError as e:
            raise MalformedIssueError(f"Issue #{issue_id} returned non-JSON payload from `gh`: {raw[:200]!r}") from e

        labels = [lbl["name"] for lbl in item.get("labels", []) or []]
        instance = cls(
            title=item["title"],
            body=item.get("body") or "",
            labels=labels,
            issue_id=item["number"],
            repo=repo,
        )
        instance.validate()
        return instance

    @classmethod
    def list_all(
        cls,
        label: str | None = None,
        state: str = "open",
        limit: int = 1000,
        repo: str | None = None,
    ) -> list["Issue"]:
        """Return all matching issues from GitHub via the `gh` CLI.

        Note: results are NOT validated. Callers that need a strict view
        should call `instance.validate()` themselves (or filter to keep
        only the well-formed ones).
        """
        cmd = [
            "gh",
            "issue",
            "list",
            "--state",
            state,
            "--limit",
            str(limit),
            "--json",
            "number,title,body,labels",
        ]
        if label:
            cmd.extend(["--label", label])
        if repo:
            cmd.extend(["--repo", repo])

        raw = _run_gh(cmd)
        items = json.loads(raw)

        issues: list[Issue] = []
        for item in items:
            labels = [lbl["name"] for lbl in item.get("labels", []) or []]
            issues.append(
                cls(
                    title=item["title"],
                    body=item.get("body") or "",
                    labels=labels,
                    issue_id=item["number"],
                    repo=repo,
                )
            )
        return issues

    # ---- label helpers ------------------------------------------------------

    # Per-process cache: { repo_key: set_of_label_names }. `repo_key` is the
    # explicit `target_repo` string, or the sentinel "" when None (i.e. let
    # gh resolve via GH_REPO / `gh repo set-default`).
    _label_cache: ClassVar[dict[str, set[str]]] = {}

    @classmethod
    def _existing_labels(cls, repo: str | None) -> set[str]:
        """Return the set of label names that exist on `repo`.

        Cached per-process so multiple `save()` calls in a row don't re-query.
        Returns an empty set on `gh` failure (caller treats that as "skip the
        existence check rather than block all labels").
        """
        key = repo or ""
        if key in cls._label_cache:
            return cls._label_cache[key]

        cmd = ["gh", "label", "list", "--limit", "1000", "--json", "name"]
        if repo:
            cmd.extend(["--repo", repo])
        try:
            raw = _run_gh(cmd)
            names = {item["name"] for item in json.loads(raw)}
        except (GhCommandError, json.JSONDecodeError) as exc:
            print(
                f"warning: could not list labels for {repo or '<gh default>'}: {exc}; skipping label-existence check",
                file=sys.stderr,
            )
            names = set()  # caller will treat this as "no filter"

        cls._label_cache[key] = names
        return names

    def _filter_labels(self, repo: str | None) -> list[str]:
        """Return `self.labels` with non-existent labels dropped + a warning.

        When the existence query failed (empty cache entry), returns
        `self.labels` unchanged so the user still sees gh's own error rather
        than silently losing labels.
        """
        existing = self._existing_labels(repo)
        if not existing:
            return list(self.labels)

        keep: list[str] = []
        for lbl in self.labels:
            if lbl in existing:
                keep.append(lbl)
            else:
                issue_ref = f"#{self.issue_id}" if self.issue_id is not None else "<new>"
                print(
                    f"warning: label {lbl!r} does not exist on "
                    f"{repo or '<gh default>'}; skipping for issue {issue_ref} "
                    f"({self.title!r})",
                    file=sys.stderr,
                )
        return keep

    def save(self, repo: str | None = None) -> int:
        """Persist this issue to GitHub via the `gh` CLI.

        - `issue_id is None`  → `gh issue create` (assigns and stores a new id).
        - `issue_id is int`   → `gh issue edit <id>` (updates title/body/labels).

        Labels in `self.labels` that don't exist on the target repo are
        skipped with a stderr warning; `self.labels` itself is left untouched.

        Args:
            repo: "owner/name" override. When None, falls back to `self.repo`,
                then to whatever `gh` resolves. An explicit value also updates
                `self.repo` so subsequent `save()` calls reuse it.
        """
        body = self._render_body()
        target_repo = repo or self.repo
        applicable_labels = self._filter_labels(target_repo)

        if self.issue_id is None:
            cmd = [
                "gh",
                "issue",
                "create",
                "--title",
                self.title,
                "--body",
                body,
            ]
            for lbl in applicable_labels:
                cmd.extend(["--label", lbl])
            if target_repo:
                cmd.extend(["--repo", target_repo])

            out = _run_gh(cmd).strip()
            # `gh issue create` prints the issue URL on the last line.
            url = out.splitlines()[-1]
            try:
                self.issue_id = int(url.rsplit("/", 1)[-1])
            except ValueError as e:
                raise RuntimeError(f"Could not parse issue number from gh output: {out!r}") from e
            self.repo = target_repo
            return self.issue_id

        cmd = [
            "gh",
            "issue",
            "edit",
            str(self.issue_id),
            "--title",
            self.title,
            "--body",
            body,
        ]
        # `gh issue edit` does not replace labels wholesale; it only adds/removes.
        # We add every label in self.labels (idempotent on the server side).
        for lbl in applicable_labels:
            cmd.extend(["--add-label", lbl])
        if target_repo:
            cmd.extend(["--repo", target_repo])

        _run_gh(cmd)
        self.repo = target_repo
        return self.issue_id

    def close(
        self,
        comment: str | None = None,
        reason: str | None = None,
        repo: str | None = None,
    ) -> None:
        """Close this issue on GitHub via the `gh` CLI.

        Args:
            comment: Optional text posted as a closing comment.
            reason: Optional `gh issue close --reason` value (e.g. "completed",
                "not_planned"). Omitted when `None`.
            repo: "owner/name" override; falls back to `self.repo`.

        Raises:
            ValueError: if the issue has not been saved (no `issue_id`).
        """
        if self.issue_id is None:
            raise ValueError("Cannot close an issue that has no issue_id (never saved).")

        cmd = ["gh", "issue", "close", str(self.issue_id)]
        if comment:
            cmd.extend(["--comment", comment])
        if reason:
            cmd.extend(["--reason", reason])
        target_repo = repo or self.repo
        if target_repo:
            cmd.extend(["--repo", target_repo])
        _run_gh(cmd)
        self.repo = target_repo
