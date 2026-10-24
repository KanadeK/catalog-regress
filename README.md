# catalog-regress

Keep a catalog update from silently disabling translations that already worked.
A local CLI compares two gettext PO files and gates regressions in the **previously
usable message set**, even when the overall translated count stays the same.

[简体中文](README.zh-CN.md) · [MIT](LICENSE) · Python 3.11+ · No service or API keys

For example, making `Hello → Bonjour` fuzzy leaves valid PO syntax but makes
gettext fall back to `Hello`. `catalog-regress` reports that specific loss.
It also catches emptied translations, missing/obsolete entries, incomplete
plural forms and changed plural source strings.

## Install

```sh
git clone https://github.com/KanadeK/catalog-regress.git
cd catalog-regress
python -m venv .venv
```

Activate the environment with `source .venv/bin/activate` on Linux/macOS or
`.\.venv\Scripts\Activate.ps1` in PowerShell, then run:

```sh
python -m pip install .
catalog-regress --version
```

The only runtime dependency is [polib 1.2.0](https://pypi.org/project/polib/1.2.0/)
(MIT). No GNU gettext installation is required for this gate.

## Run the included workflow

```sh
catalog-regress examples/before.po examples/after.po --json
# Expected exit 1: one previously usable translation became fuzzy.
catalog-regress examples/before.po examples/fixed.po --json
# Expected exit 0: the protected translations are usable again.
```

Inputs are never edited. JSON and text output contain counts, file SHA-256 values,
message identity hashes and PO entry line numbers, without source strings,
translations, metadata values or input paths. Line numbers locate entries, not
necessarily their msgid line. Hashes can still reveal guessed low-entropy content.

## Acceptance contract

An active baseline entry is protected when it is not fuzzy and has a nonempty
translation. For plurals, **every index from 0 through nplurals−1** must be present
and nonempty. Whitespace-only translations are intentionally nonempty, matching
gettext's empty-string distinction.

Matching uses `(msgctxt, msgid)`, preserving the distinction between no context
and an explicitly empty context. A changed `msgid_plural` is a regression even
if translations remain filled. A changed singular msgid is a removed identity
plus a new one; source renames are never guessed. New untranslated messages do
not count as regressions and new ready messages cannot cancel old losses.

Both catalogs need a UTF-8 Content-Type header and the same normalized Language
and nplurals values. Plural expressions are never evaluated. An incomplete plural
translation can be a legitimate work in progress; it is simply not ready.
Duplicate active identities and out-of-range plural indices are input errors.

```sh
# Explicitly permit source entries removed or made obsolete by a source update.
catalog-regress old.po new.po --allow-removed
# Permit at most two remaining regressions; still report their actual count.
catalog-regress old.po new.po --max-regressions 2 --max-findings 20 --json
```

Default policy permits zero regressions. `--allow-removed` never permits fuzzy,
empty or plural-source-changed entries. `--max-findings 0` suppresses details,
not detection. Default input size limit is 16 MiB per file, adjustable with
`--max-bytes N`. Limits must be nonnegative (byte limit must be positive).

| Exit | Meaning |
| --- | --- |
| 0 | Policy accepted; actual count is within the explicit budget |
| 1 | Regression count exceeds the budget |
| 2 | Invalid options, unreadable/malformed input or incompatible catalog metadata |

In CI, obtain a baseline from the revision you intend to protect, then invoke
the same command. This tool does not run Git, select a merge base or download
files. Avoid treating an empty or unrelated baseline as release evidence.

## Scope and alternatives

This is a regression gate, not a translation editor, semantic translation-quality
judge or complete PO/format-string validator. Keep `msgfmt --check` for GNU gettext
syntax/format checks. [Weblate](https://weblate.org/) is a better fit for collaborative
translation management; `msgcmp` and `git-po-helper` serve their own catalog/Git
workflows. This tool supplies a standalone protected-set policy and bounded
content-free receipts. It accepts UTF-8 PO only, not MO, POT-only headers or other
localization formats. Catalogs are parsed in memory; the byte limit is not an OS
memory or CPU sandbox. Passing this gate does not prove translations are correct
or that arbitrary plural expressions are valid.

See [GNU gettext's fuzzy-entry behavior](https://www.gnu.org/software/gettext/manual/html_node/Fuzzy-Entries.html)
and [Godot's gettext guidance](https://docs.godotengine.org/en/stable/tutorials/i18n/localization_using_gettext.html)
for the underlying runtime distinction.

## Development and cleanup

See [CONTRIBUTING.md](CONTRIBUTING.md) for tests, lint, coverage, build and an
isolated wheel-install smoke check. CI runs on Linux, Windows and macOS and never
commits code. [Security reports](SECURITY.md) should use private reporting.

Uninstall with `python -m pip uninstall catalog-regress polib` if this environment
was dedicated to the tool. Deactivate and remove the dedicated `.venv` directory
to remove its dependencies as well. There is no cache, daemon or user-data folder.
