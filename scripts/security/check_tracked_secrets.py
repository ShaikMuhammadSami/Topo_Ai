"""Fail on a small set of high-confidence secrets in Git-tracked text files."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    category: str


class ScanError(RuntimeError):
    """Raised when the tracked tree cannot be inspected safely."""


GITHUB_CREDENTIAL = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{50,255})"
    r"(?![A-Za-z0-9_])"
)
AWS_ACCESS_KEY_ID = re.compile(
    r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"
)
PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
)
BEARER_CREDENTIAL = re.compile(
    r"(?i)\bBearer\s+(?P<token>[A-Za-z0-9._~+/=-]{20,})"
)
BASIC_CREDENTIAL = re.compile(
    r"(?i)\bBasic\s+(?P<token>[A-Za-z0-9+/=]{20,})"
)
OPENAI_CREDENTIAL = re.compile(
    r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,255}(?![A-Za-z0-9_])"
)
GROQ_CREDENTIAL = re.compile(
    r"(?<![A-Za-z0-9_])gsk_[A-Za-z0-9_-]{20,255}(?![A-Za-z0-9_])"
)
TOPO_CREDENTIAL = re.compile(
    r"(?<![A-Za-z0-9_])topo_(?:api|agent|enroll)_[A-Za-z0-9._~-]{20,255}"
)
DATABASE_URL_CREDENTIAL = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|mysql(?:\+[a-z0-9]+)?)://[^\s/:]+:"
    r"(?P<password>[^\s/@]+)@"
)

SENSITIVE_ASSIGNMENT_NAMES = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AZURE_CLIENT_SECRET",
        "DATADOG_API_KEY",
        "DATADOG_APP_KEY",
        "GCP_SERVICE_ACCOUNT_KEY",
        "GITHUB_TOKEN",
        "GROQ_API_KEY",
        "GITLAB_TOKEN",
        "GOOGLE_API_KEY",
        "JENKINS_TOKEN",
        "NEW_RELIC_LICENSE_KEY",
        "OPENAI_API_KEY",
        "PAGERDUTY_API_KEY",
        "SLACK_BOT_TOKEN",
        "TERRAFORM_TOKEN",
        "TOPO_AGENT_ENROLLMENT_TOKEN",
        "TOPO_AGENT_TOKEN",
        "TOPO_API_TOKEN",
        "TOPO_GITHUB_TOKEN",
    }
)
ASSIGNMENT = re.compile(
    r"(?im)^[ \t]*(?:export[ \t]+)?[\"']?"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)[\"']?[ \t]*[:=][ \t]*"
    r"(?P<value>[^#\r\n]*)"
)
PLACEHOLDER = re.compile(
    r"(?i)^(?:"
    r"example(?:[-_ ].*)?|"
    r"replace(?:[-_ ](?:me|with(?:[-_ ].*)?))?|"
    r"change(?:[-_ ]?me)|"
    r"redacted|"
    r"dummy(?:[-_ ].*)?|"
    r"test[-_ ]?only(?:[-_ ].*)?|"
    r"your(?:[-_ ].*)?|"
    r"not[-_ ]set|password|"
    r"none|"
    r"null"
    r")$"
)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _literal_value(raw_value: str) -> str:
    value = raw_value.strip().rstrip(",").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'", "`"}:
        value = value[1:-1].strip()
    return value


def is_placeholder_or_reference(raw_value: str) -> bool:
    value = _literal_value(raw_value)
    if not value:
        return True
    lowered = value.lower()
    if re.fullmatch(r"<[^>\r\n]+>", value):
        return True
    if value.startswith("${") or value.startswith("{{"):
        return True
    if lowered.startswith(
        (
            "env(",
            "getenv(",
            "os.environ",
            "process.env",
            "secretstr(",
            "secrets.",
            "settings.",
        )
    ):
        return True
    return PLACEHOLDER.fullmatch(value) is not None


def _is_unquoted_code_reference(path: str, raw_value: str) -> bool:
    if Path(path).suffix.lower() not in {".js", ".jsx", ".py", ".ts", ".tsx"}:
        return False
    value = raw_value.strip()
    return bool(value) and value[0] not in {"\"", "'", "`"}


def scan_text(path: str, text: str) -> list[Finding]:
    findings: set[Finding] = set()
    fixed_patterns = (
        ("GitHub credential candidate", GITHUB_CREDENTIAL),
        ("AWS access-key ID candidate", AWS_ACCESS_KEY_ID),
        ("Private-key block", PRIVATE_KEY_BLOCK),
        ("OpenAI credential candidate", OPENAI_CREDENTIAL),
        ("Groq credential candidate", GROQ_CREDENTIAL),
        ("Topo credential candidate", TOPO_CREDENTIAL),
    )
    for category, pattern in fixed_patterns:
        for match in pattern.finditer(text):
            findings.add(Finding(path, _line_number(text, match.start()), category))

    for match in DATABASE_URL_CREDENTIAL.finditer(text):
        if not is_placeholder_or_reference(match.group("password")):
            findings.add(
                Finding(
                    path,
                    _line_number(text, match.start()),
                    "Credential-bearing database URL",
                )
            )

    for match in BEARER_CREDENTIAL.finditer(text):
        if not is_placeholder_or_reference(match.group("token")):
            findings.add(
                Finding(
                    path,
                    _line_number(text, match.start()),
                    "Literal bearer credential",
                )
            )

    for match in BASIC_CREDENTIAL.finditer(text):
        if not is_placeholder_or_reference(match.group("token")):
            findings.add(
                Finding(path, _line_number(text, match.start()), "Literal basic credential")
            )

    for match in ASSIGNMENT.finditer(text):
        name = match.group("name").upper()
        if name not in SENSITIVE_ASSIGNMENT_NAMES:
            continue
        if _is_unquoted_code_reference(path, match.group("value")):
            continue
        if is_placeholder_or_reference(match.group("value")):
            continue
        findings.add(
            Finding(
                path,
                _line_number(text, match.start()),
                "Literal provider credential assignment",
            )
        )

    return sorted(findings)


def scan_bytes(path: str, content: bytes) -> list[Finding]:
    if b"\x00" in content:
        return []
    return scan_text(path, content.decode("utf-8", errors="replace"))


def _run_git(repo_root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", os.fspath(repo_root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        command = args[0] if args else "command"
        raise ScanError(f"Git {command} failed; tracked-tree scan was not completed.")
    return result.stdout


def get_tracked_paths(repo_root: Path) -> tuple[str, ...]:
    output = _run_git(repo_root, "ls-files", "--cached", "-z")
    return tuple(
        os.fsdecode(raw_path)
        for raw_path in output.split(b"\x00")
        if raw_path
    )


def _unstaged_paths(repo_root: Path) -> set[str]:
    output = _run_git(
        repo_root,
        "diff",
        "--name-only",
        "--diff-filter=ACMRTUXB",
        "-z",
        "--",
    )
    return {
        os.fsdecode(raw_path)
        for raw_path in output.split(b"\x00")
        if raw_path
    }


def _read_tracked_file(
    repo_root: Path,
    relative_path: str,
    unstaged_paths: set[str],
) -> bytes | None:
    path = repo_root / relative_path
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink():
        return os.fsencode(os.readlink(path))
    try:
        return path.read_bytes()
    except PermissionError as exc:
        if relative_path in unstaged_paths:
            raise ScanError(
                f"Tracked file could not be read from the working tree: {relative_path}"
            ) from exc
        return _run_git(repo_root, "show", f":{relative_path}")


def scan_repository(repo_root: Path) -> list[Finding]:
    root = repo_root.resolve()
    unstaged = _unstaged_paths(root)
    findings: list[Finding] = []
    for relative_path in get_tracked_paths(root):
        try:
            content = _read_tracked_file(root, relative_path, unstaged)
        except OSError as exc:
            raise ScanError(
                f"Tracked file could not be inspected: {relative_path}"
            ) from exc
        if content is not None:
            findings.extend(scan_bytes(relative_path, content))
    return sorted(set(findings))


def render_findings(findings: Iterable[Finding]) -> str:
    return "\n".join(
        "SECRET_PATTERN "
        f"category={finding.category} path={finding.path} line={finding.line}"
        for finding in findings
    )


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    try:
        findings = scan_repository(repository_root())
    except ScanError as exc:
        print(f"SECRET_SCAN_ERROR {exc}", file=sys.stderr)
        return 2
    if findings:
        print(render_findings(findings))
        print(
            "Tracked-tree secret hygiene check failed; values are intentionally redacted.",
            file=sys.stderr,
        )
        return 1
    print("Tracked-tree secret hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
