"""`RegressionIssue` — schema-bound subclass of `Issue` for support-matrix regressions.

The body of a regression issue is templated:

    # Issue Description

    <human-editable description above the workflow start marker>

    <!-- Do not modify the following section as they are used by Claude Code workflow -->

    # Failed Cases
    ```csv
    HuggingFaceID,Architecture,System,Backend,Version,Mode,FailedBranch
    ...
    ```

    # Example ErrMsg
    ```
    <traceback>
    ```

    <!-- End of Claude Code Workflow Metadata -->

    <human-editable description below the workflow end marker>

This module isolates everything specific to that schema; the generic
GitHub-issue plumbing lives in `.claude/skills/issues.py`.
"""

import csv
import re
import sys
from io import StringIO
from pathlib import Path

import yaml

# `.claude/skills/issues.py` lives one directory up. Inject that on sys.path
# so this file can be used both as a module and as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from issues import Issue, MalformedIssueError


class _EscapedNewlineDumper(yaml.SafeDumper):
    """SafeDumper variant that emits multi-line strings with literal `\\n`
    escapes (double-quoted style) instead of YAML block scalars."""


def _represent_str(dumper: yaml.SafeDumper, data: str):
    style = '"' if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_EscapedNewlineDumper.add_representer(str, _represent_str)


_TBD_RE = re.compile(r"^TBD_\d+$")

DEFAULT_CLOSE_COMMENT = (
    "Auto-closed by the support-matrix-autofix workflow: this regression no "
    "longer appears in the latest support matrix run, so all of its failed "
    "cases have been resolved."
)


def _dump_yaml(payload) -> str:
    return yaml.dump(
        payload,
        Dumper=_EscapedNewlineDumper,
        default_flow_style=False,
        sort_keys=False,
        width=10**6,
        allow_unicode=True,
    )


def _split_issue_id(raw) -> tuple[int | None, str | None]:
    """Normalize a YAML `issue_id` value into (numeric_id, placeholder_id).

    Returns ``(int, None)`` for real ids, ``(None, "TBD_<n>")`` for placeholders,
    and ``(None, None)`` for missing/blank values.
    """
    if raw is None:
        return None, None
    if isinstance(raw, int):
        return raw, None
    s = str(raw).strip()
    if not s:
        return None, None
    if s.isdigit():
        return int(s), None
    if _TBD_RE.match(s):
        return None, s
    raise ValueError(f"Unrecognized issue_id {raw!r}: expected an integer or 'TBD_<digits>'.")


class RegressionIssue(Issue):
    # ---- Body schema (overridable per subclass) -----------------------------
    DESCRIPTION_HEADING = "# Issue Description"
    FAILED_CASES_HEADING = "# Failed Cases"
    ERR_MSG_HEADING = "# Example ErrMsg"

    WORKFLOW_START_MARKER = "<!-- Do not modify the following section as they are used by Claude Code workflow -->"
    WORKFLOW_END_MARKER = "<!-- End of Claude Code Workflow Metadata -->"

    FAILED_CASES_FIELDS = (
        "HuggingFaceID",
        "Architecture",
        "System",
        "Backend",
        "Version",
        "Mode",
        "FailedBranch",
    )

    LABEL = "regression"

    # ---- structured-field initialization ------------------------------------

    def _parse_body(self) -> None:
        # Initialize structured fields up-front so attribute access is safe
        # even if parsing fails partway through.
        self.description_pre = ""
        self.description_post = ""
        self.failed_cases: list[dict] = []
        self.err_msg = ""

        text = self.body

        if self.WORKFLOW_START_MARKER in text:
            description_pre = text.split(self.WORKFLOW_START_MARKER, 1)[0]
        else:
            description_pre = text
        self.description_pre = description_pre.strip()

        if self.WORKFLOW_END_MARKER in text:
            description_post = text.split(self.WORKFLOW_END_MARKER, 1)[1]
        else:
            description_post = ""
        self.description_post = description_post.strip()

        failed_cases_section = self._extract_section(text, self.FAILED_CASES_HEADING)
        csv_text = self._extract_fenced_block(failed_cases_section, language="csv")
        if csv_text:
            reader = csv.DictReader(StringIO(csv_text))
            for row in reader:
                self.failed_cases.append({field: row.get(field, "") for field in self.FAILED_CASES_FIELDS})

        err_msg_section = self._extract_section(text, self.ERR_MSG_HEADING)
        self.err_msg = self._extract_fenced_block(err_msg_section)

    def _render_body(self) -> str:
        """Inverse of `_parse_body`: assemble the structured fields back into markdown."""
        csv_buf = StringIO()
        writer = csv.DictWriter(csv_buf, fieldnames=list(self.FAILED_CASES_FIELDS))
        writer.writeheader()
        for row in self.failed_cases:
            writer.writerow({field: row.get(field, "") for field in self.FAILED_CASES_FIELDS})
        # csv module writes \r\n by default; normalize to \n for markdown.
        failed_cases_csv = csv_buf.getvalue().replace("\r\n", "\n").rstrip("\n")

        sections: list[str] = []

        if self.description_pre:
            sections.append(self.description_pre.strip())
        else:
            sections.append(self.DESCRIPTION_HEADING)

        sections.append(self.WORKFLOW_START_MARKER)
        sections.append(f"{self.FAILED_CASES_HEADING}\n```csv\n{failed_cases_csv}\n```")
        sections.append(f"{self.ERR_MSG_HEADING}\n```\n{self.err_msg.rstrip()}\n```")
        sections.append(self.WORKFLOW_END_MARKER)

        if self.description_post:
            sections.append(self.description_post.strip())

        return "\n\n".join(sections) + "\n"

    def validate(self) -> None:
        problems: list[str] = []
        if self.WORKFLOW_START_MARKER not in self.body:
            problems.append("missing WORKFLOW_START_MARKER")
        if self.WORKFLOW_END_MARKER not in self.body:
            problems.append("missing WORKFLOW_END_MARKER")
        if not self.failed_cases:
            problems.append(f"missing or empty `{self.FAILED_CASES_HEADING}` CSV block")
        if not self.err_msg:
            problems.append(f"missing or empty `{self.ERR_MSG_HEADING}` code block")

        if problems:
            issue_ref = f"#{self.issue_id}" if self.issue_id is not None else "<unsaved>"
            raise MalformedIssueError(f"Issue {issue_ref} ({self.title!r}) is malformed: " + "; ".join(problems))

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "description_pre": self.description_pre,
            "description_post": self.description_post,
            "failed_cases": [dict(case) for case in self.failed_cases],
            "err_msg": self.err_msg,
        }

    # ---- regression-only convenience APIs -----------------------------------

    @classmethod
    def list_as_yaml(
        cls,
        state: str = "open",
        limit: int = 1000,
        repo: str | None = None,
    ) -> str:
        """Return all `regression`-tagged issues serialized as YAML."""
        issues = cls.list_all(label=cls.LABEL, state=state, limit=limit, repo=repo)
        payload = [issue.to_dict() for issue in issues]
        return _dump_yaml(payload)

    @classmethod
    def from_dict(cls, data: dict) -> "RegressionIssue":
        """Build a `RegressionIssue` from a dict produced by `to_dict()` / YAML.

        Accepts both real numeric `issue_id`s and placeholder strings like
        ``"TBD_1"``. For placeholders, the instance is created with
        `issue_id = None` so that `save()` will create a new GitHub issue.
        Use `is_new_placeholder` / `placeholder_id` on the returned instance
        to recover the original placeholder.
        """
        raw_id = data.get("issue_id")
        issue_id, placeholder = _split_issue_id(raw_id)

        instance = cls(
            title=data.get("title", "") or "",
            body="",  # overridden below via _render_body()
            labels=list(data.get("labels") or []),
            issue_id=issue_id,
            repo=data.get("repo"),
        )
        instance.placeholder_id = placeholder
        instance.description_pre = data.get("description_pre", "") or ""
        instance.description_post = data.get("description_post", "") or ""
        instance.failed_cases = [dict(c) for c in (data.get("failed_cases") or [])]
        instance.err_msg = data.get("err_msg", "") or ""
        instance.body = instance._render_body()
        return instance

    @property
    def is_new_placeholder(self) -> bool:
        """True when this issue came from a `TBD_<n>` placeholder id."""
        return getattr(self, "placeholder_id", None) is not None and self.issue_id is None

    # ---- internal helpers ---------------------------------------------------

    @staticmethod
    def _extract_section(body: str, heading: str) -> str:
        """Return the text following `heading` up to the next top-level `# ` heading."""
        pattern = re.compile(
            rf"^{re.escape(heading)}\s*\n(?P<content>.*?)(?=^# |\Z)",
            re.MULTILINE | re.DOTALL,
        )
        m = pattern.search(body)
        return m.group("content").strip() if m else ""

    @staticmethod
    def _extract_fenced_block(text: str, language: str | None = None) -> str:
        """Return the contents of the first fenced code block in `text`."""
        if language:
            pattern = re.compile(
                rf"```{re.escape(language)}\s*\n(?P<content>.*?)```",
                re.DOTALL,
            )
        else:
            pattern = re.compile(r"```[^\n]*\n(?P<content>.*?)```", re.DOTALL)
        m = pattern.search(text)
        return m.group("content").rstrip("\n") if m else ""


def _cmd_pull(args) -> int:
    """`pull` subcommand: dump regression issues from GitHub to YAML."""
    yaml_text = RegressionIssue.list_as_yaml(state=args.state, limit=args.limit, repo=args.repo)
    Path(args.output).write_text(yaml_text)
    src = args.repo or "<gh default repo>"
    print(f"Wrote regression issues from {src} to {args.output}", file=sys.stderr)
    return 0


def _cmd_push(args) -> int:
    """`push` subcommand: create / update / close regression issues from YAML.

    Per-entry semantics, driven by the YAML state:

    - ``issue_id`` is numeric and ``failed_cases`` is non-empty
        -> ``gh issue edit`` (update title/body/labels in place).
    - ``issue_id`` is numeric and ``failed_cases`` is empty
        -> ``gh issue close`` with `--reason completed` and a comment.
    - ``issue_id`` looks like ``TBD_<n>`` and ``failed_cases`` is non-empty
        -> ``gh issue create`` (real id is allocated by GitHub).
    - ``issue_id`` looks like ``TBD_<n>`` and ``failed_cases`` is empty
        -> skipped (nothing to file an issue about).

    When ``--update-input`` is set, the YAML file is rewritten with newly
    allocated ids substituted in place of their ``TBD_<n>`` placeholders.
    """
    input_path = Path(args.input)
    raw = yaml.safe_load(input_path.read_text())
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        print(f"{input_path}: expected a top-level YAML list", file=sys.stderr)
        return 2

    n_created = n_updated = n_closed = n_skipped = 0
    out_entries: list[dict] = []

    for entry in raw:
        if not isinstance(entry, dict):
            print(f"Skipping non-dict entry: {entry!r}", file=sys.stderr)
            n_skipped += 1
            out_entries.append(entry)
            continue

        try:
            issue = RegressionIssue.from_dict(entry)
        except ValueError as exc:
            print(f"Skipping malformed entry {entry.get('issue_id')!r}: {exc}", file=sys.stderr)
            n_skipped += 1
            out_entries.append(entry)
            continue

        target_repo = args.repo or issue.repo
        out_entry = dict(entry)

        if not issue.failed_cases:
            if issue.issue_id is not None:
                issue.close(
                    comment=args.close_comment,
                    reason="completed",
                    repo=target_repo,
                )
                n_closed += 1
                print(f"closed #{issue.issue_id}: {issue.title!r}", file=sys.stderr)
            else:
                print(
                    f"skip {entry.get('issue_id')!r}: placeholder with no failed_cases",
                    file=sys.stderr,
                )
                n_skipped += 1
            out_entries.append(out_entry)
            continue

        if issue.is_new_placeholder:
            new_id = issue.save(repo=target_repo)
            n_created += 1
            out_entry["issue_id"] = new_id
            print(
                f"created #{new_id} (was {entry.get('issue_id')!r}): {issue.title!r}",
                file=sys.stderr,
            )
        else:
            issue.save(repo=target_repo)
            n_updated += 1
            print(f"updated #{issue.issue_id}: {issue.title!r}", file=sys.stderr)

        out_entries.append(out_entry)

    if args.update_input:
        input_path.write_text(_dump_yaml(out_entries))
        print(f"Wrote updated YAML back to {input_path}", file=sys.stderr)

    print(
        f"Push complete: created={n_created}, updated={n_updated}, closed={n_closed}, skipped={n_skipped}",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    """CLI: pull regression issues from GitHub or push a YAML back to GitHub."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    pull = sub.add_parser(
        "pull",
        help="Dump all regression-tagged issues to a YAML file.",
    )
    pull.add_argument(
        "-o",
        "--output",
        default="issues.yaml",
        help="Path to write the YAML dump (default: issues.yaml).",
    )
    pull.add_argument(
        "--repo",
        default=None,
        help='Source repo as "owner/name". Defaults to GH_REPO / gh default.',
    )
    pull.add_argument(
        "--state",
        default="open",
        choices=("open", "closed", "all"),
        help="Issue state to include (default: open).",
    )
    pull.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Max number of issues to fetch (default: 1000).",
    )
    pull.set_defaults(func=_cmd_pull)

    push = sub.add_parser(
        "push",
        help="Create / update / close regression issues from a YAML file.",
    )
    push.add_argument(
        "-i",
        "--input",
        default="issues.yaml",
        help="Path to the YAML file to push (default: issues.yaml).",
    )
    push.add_argument(
        "--repo",
        default=None,
        help='Target repo as "owner/name". Defaults to per-issue `repo` field, then GH_REPO / gh default.',
    )
    push.add_argument(
        "--close-comment",
        default=DEFAULT_CLOSE_COMMENT,
        help="Comment posted when closing an issue with no remaining failed_cases.",
    )
    push.add_argument(
        "--update-input",
        action="store_true",
        help="Rewrite the input YAML in place, substituting newly created issue ids for their TBD_<n> placeholders.",
    )
    push.set_defaults(func=_cmd_push)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
