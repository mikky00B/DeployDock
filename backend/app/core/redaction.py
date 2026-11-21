"""Redaction of secret material from anything the control plane persists or
sends to a viewer: deployment logs, error messages, emails (audit H1).

Two layers:

- value-based: the caller supplies the deployment's actual secret values (its
  merged environment variables), and every occurrence is replaced — this is
  the canary guarantee, e.g. a failed connection string echoed by the app;
- pattern-based: credential-bearing URL userinfo, ``password=``/``token=``
  query pairs, and ``Authorization: Bearer`` headers are redacted even when
  the value is not known.
"""

import re
from collections.abc import Iterable

REDACTED = "[REDACTED]"

# user:password@ between the scheme and the host (audit H1: git error messages
# echo the repository URL, which may embed credentials).
_URL_USERINFO_RE = re.compile(r"(?<=://)[^/@\s]+:[^@\s]+(?=@)")
# password=... / token=... / api_key=... style query or log fragments.
_KEY_VALUE_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key)\s*[=:]\s*(\"[^\"]*\"|'[^']*'|\S+)"
)
# Authorization: Bearer <token> headers pasted into logs.
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)\S+")


def redact_text(text: str, secret_values: Iterable[str] = ()) -> str:
    """Return ``text`` with known secret values and credential patterns masked."""
    if not text:
        return text
    result = text
    for value in secret_values:
        if value and len(value) >= 4 and value in result:
            result = result.replace(value, REDACTED)
    result = _URL_USERINFO_RE.sub(REDACTED, result)
    result = _KEY_VALUE_RE.sub(lambda match: f"{match.group(1)}={REDACTED}", result)
    result = _BEARER_RE.sub(lambda match: f"{match.group(1)}{REDACTED}", result)
    return result


def redact_mapping(values: dict[str, str]) -> dict[str, str]:
    """The values to feed redact_text for a deployment's environment."""
    return {key: value for key, value in values.items() if value}
