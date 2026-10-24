"""Compare runtime-ready entries, without printing or executing catalog content."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polib

from . import __version__

DEFAULT_MAX_BYTES = 16 * 1024 * 1024
Key = tuple[str | None, str]


class CatalogError(ValueError):
    """A stable, content-free diagnostic safe for command-line reports."""

    def __init__(self, code: str, side: str = "options") -> None:
        self.code = code
        self.side = side
        super().__init__(f"{side}: {code}")


@dataclass
class Catalog:
    entries: dict[Key, Any]
    obsolete: dict[Key, Any]
    language: str
    nplurals: int | None
    summary: dict[str, Any]


def _ready(entry: Any, nplurals: int | None) -> bool:
    if entry.obsolete or "fuzzy" in entry.flags:
        return False
    if entry.msgid_plural:
        return (
            nplurals is not None
            and set(entry.msgstr_plural) == set(range(nplurals))
            and all(value != "" for value in entry.msgstr_plural.values())
        )
    return entry.msgstr != ""


def _load(path: Path, side: str, max_bytes: int) -> Catalog:
    try:
        if not path.is_file():
            raise CatalogError("not_regular_file", side)
        with path.open("rb") as handle:
            data = handle.read(max_bytes + 1)
    except OSError:
        raise CatalogError("cannot_read", side) from None
    if len(data) > max_bytes:
        raise CatalogError("size_limit", side)
    try:
        text = data.decode("utf-8-sig", errors="strict")
    except UnicodeError:
        raise CatalogError("not_utf8", side) from None
    if "\x00" in text:
        raise CatalogError("nul_byte", side)
    try:
        catalog = polib.pofile(text, encoding="utf-8")
    except (OSError, ValueError, IndexError, UnicodeError):
        # polib's exception may include a complete source/translation line.
        raise CatalogError("invalid_po", side) from None
    language = catalog.metadata.get("Language", "").strip().replace("-", "_").casefold()
    if not language or not re.fullmatch(r"[a-z0-9_@.\-]+", language):
        raise CatalogError("missing_or_invalid_language", side)
    content_type = catalog.metadata.get("Content-Type", "")
    charsets = re.findall(r"charset\s*=\s*([^\s;]+)", content_type, flags=re.I)
    if len(charsets) != 1 or charsets[0].casefold() not in {"utf-8", "utf8"}:
        raise CatalogError("utf8_header_required", side)

    active: dict[Key, Any] = {}
    obsolete: dict[Key, Any] = {}
    for entry in catalog:
        key = (entry.msgctxt, entry.msgid)
        if not entry.msgid:
            raise CatalogError("empty_message_id", side)
        target = obsolete if entry.obsolete else active
        if key in target:
            raise CatalogError("duplicate_message_identity", side)
        target[key] = entry

    nplurals = None
    plural_header = catalog.metadata.get("Plural-Forms", "")
    if plural_header:
        matches = re.findall(r"(?:^|;)\s*nplurals\s*=\s*([0-9]+)\s*(?=;)", plural_header)
        if len(matches) != 1 or len(matches[0]) > 2 or not 1 <= int(matches[0]) <= 20:
            raise CatalogError("invalid_nplurals", side)
        nplurals = int(matches[0])
        # The plural expression is metadata only: it is never evaluated.
    if any(entry.msgid_plural for entry in active.values()) and nplurals is None:
        raise CatalogError("plural_header_required", side)
    for entry in active.values():
        if entry.msgid_plural and any(
            index not in range(nplurals or 0) for index in entry.msgstr_plural
        ):
            raise CatalogError("plural_index_out_of_range", side)
        if not entry.msgid_plural and entry.msgstr_plural:
            raise CatalogError("plural_values_without_plural_source", side)

    ready = sum(_ready(entry, nplurals) for entry in active.values())
    fuzzy = sum("fuzzy" in entry.flags for entry in active.values())
    return Catalog(
        active,
        obsolete,
        language,
        nplurals,
        {
            "sha256": hashlib.sha256(data).hexdigest(),
            "active": len(active),
            "ready": ready,
            "fuzzy": fuzzy,
            "incomplete_nonfuzzy": len(active) - ready - fuzzy,
            "obsolete": len(obsolete),
        },
    )


def _identity_hash(key: Key, plural: str) -> str:
    payload = json.dumps([*key, plural], ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def compare_catalogs(
    baseline: str | Path,
    candidate: str | Path,
    *,
    allow_removed: bool = False,
    max_regressions: int = 0,
    max_findings: int = 50,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Return counts and bounded findings; never mutate input files.

    Only non-obsolete, non-fuzzy, fully translated baseline entries are protected.
    Missing/obsolete entries may be explicitly permitted. New untranslated entries
    do not erase a regression in the protected set.
    """
    if (
        type(max_regressions) is not int
        or max_regressions < 0
        or type(max_findings) is not int
        or max_findings < 0
        or type(max_bytes) is not int
        or max_bytes < 1
    ):
        raise CatalogError("invalid_limits")
    old = _load(Path(baseline), "baseline", max_bytes)
    new = _load(Path(candidate), "candidate", max_bytes)
    if old.language != new.language:
        raise CatalogError("language_mismatch", "pair")
    if old.nplurals != new.nplurals:
        raise CatalogError("nplurals_mismatch", "pair")

    protected = regressions = allowed_removed = 0
    findings: list[dict[str, Any]] = []
    for key, entry in old.entries.items():
        if not _ready(entry, old.nplurals):
            continue
        protected += 1
        other = new.entries.get(key)
        reason = None
        if other is None:
            reason = "obsolete" if key in new.obsolete else "missing"
            if allow_removed:
                allowed_removed += 1
                continue
        elif entry.msgid_plural != other.msgid_plural:
            reason = "plural_source_changed"
        elif "fuzzy" in other.flags:
            reason = "fuzzy"
        elif not _ready(other, new.nplurals):
            reason = "incomplete_translation"
        if reason is not None:
            regressions += 1
            if len(findings) < max_findings:
                visible = other if other is not None else new.obsolete.get(key)
                findings.append(
                    {
                        "reason": reason,
                        "identity_sha256": _identity_hash(key, entry.msgid_plural),
                        "baseline_line": entry.linenum,
                        "candidate_line": visible.linenum if visible is not None else None,
                    }
                )
    return {
        "schema_version": 1,
        "tool_version": __version__,
        "status": "pass" if regressions <= max_regressions else "regression",
        "baseline": old.summary,
        "candidate": new.summary,
        "protected": protected,
        "regression_count": regressions,
        "allowed_removed_count": allowed_removed,
        "budget": max_regressions,
        "findings": findings,
        "findings_truncated": regressions > len(findings),
    }
