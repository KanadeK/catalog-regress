from __future__ import annotations

import gettext
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import polib

from catalog_regress import CatalogError, compare_catalogs
from catalog_regress.cli import main


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, entries, **metadata):
        po = polib.POFile()
        po.metadata = {
            "Language": "fr",
            "Content-Type": "text/plain; charset=UTF-8",
            "Plural-Forms": "nplurals=2; plural=(n > 1);",
        }
        po.metadata.update(metadata)
        for item in entries:
            po.append(polib.POEntry(**item))
        path = self.root / name
        po.save(path)
        return path

    def pair(self, old, new, **options):
        return compare_catalogs(self.write("old.po", old), self.write("new.po", new), **options)

    def test_ready_remains_ready_when_translation_changes(self):
        result = self.pair(
            [dict(msgid="Hello", msgstr="Bonjour")], [dict(msgid="Hello", msgstr="Salut")]
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["protected"], 1)

    def test_fuzzy_is_a_real_runtime_regression(self):
        old = self.write("old.po", [dict(msgid="Hello", msgstr="Bonjour")])
        new = self.write("new.po", [dict(msgid="Hello", msgstr="Bonjour", flags=["fuzzy"])])
        before = gettext.GNUTranslations(io.BytesIO(polib.pofile(str(old)).to_binary()))
        after = gettext.GNUTranslations(io.BytesIO(polib.pofile(str(new)).to_binary()))
        self.assertEqual(before.gettext("Hello"), "Bonjour")
        self.assertEqual(after.gettext("Hello"), "Hello")
        result = compare_catalogs(old, new)
        self.assertEqual(result["findings"][0]["reason"], "fuzzy")

    def test_empty_translation(self):
        result = self.pair(
            [dict(msgid="Hello", msgstr="Bonjour")], [dict(msgid="Hello", msgstr="")]
        )
        self.assertEqual(result["findings"][0]["reason"], "incomplete_translation")

    def test_missing_and_obsolete(self):
        for entries, reason in [
            ([], "missing"),
            ([dict(msgid="Hello", msgstr="Bonjour", obsolete=True)], "obsolete"),
        ]:
            with self.subTest(reason=reason):
                result = self.pair([dict(msgid="Hello", msgstr="Bonjour")], entries)
                self.assertEqual(result["findings"][0]["reason"], reason)
                self.assertEqual(
                    self.pair([dict(msgid="Hello", msgstr="Bonjour")], entries, allow_removed=True)[
                        "status"
                    ],
                    "pass",
                )

    def test_allow_removed_does_not_allow_fuzzy(self):
        result = self.pair(
            [dict(msgid="x", msgstr="y")],
            [dict(msgid="x", msgstr="y", flags=["fuzzy"])],
            allow_removed=True,
        )
        self.assertEqual(result["status"], "regression")

    def test_context_identity(self):
        result = self.pair(
            [dict(msgid="Open", msgctxt="verb", msgstr="Ouvrir")],
            [dict(msgid="Open", msgctxt="adjective", msgstr="Ouvert")],
        )
        self.assertEqual(result["regression_count"], 1)

    def test_baseline_fuzzy_and_empty_are_not_protected(self):
        result = self.pair(
            [dict(msgid="a", msgstr="x", flags=["fuzzy"]), dict(msgid="b", msgstr="")], []
        )
        self.assertEqual(result["protected"], 0)

    def test_complete_plurals(self):
        entry = dict(msgid="apple", msgid_plural="apples", msgstr_plural={0: "p", 1: "ps"})
        result = self.pair([entry], [entry])
        self.assertEqual(result["protected"], 1)
        self.assertEqual(result["status"], "pass")

    def test_partial_plural_regresses(self):
        old = dict(msgid="a", msgid_plural="as", msgstr_plural={0: "b", 1: "bs"})
        new = dict(msgid="a", msgid_plural="as", msgstr_plural={0: "b", 1: ""})
        self.assertEqual(self.pair([old], [new])["regression_count"], 1)

    def test_plural_source_changes(self):
        old = dict(msgid="a", msgid_plural="as", msgstr_plural={0: "b", 1: "bs"})
        new = dict(msgid="a", msgid_plural="others", msgstr_plural={0: "b", 1: "bs"})
        self.assertEqual(self.pair([old], [new])["findings"][0]["reason"], "plural_source_changed")

    def test_singular_becomes_plural(self):
        old = dict(msgid="a", msgstr="b")
        new = dict(msgid="a", msgid_plural="as", msgstr_plural={0: "b", 1: "bs"})
        self.assertEqual(self.pair([old], [new])["regression_count"], 1)

    def test_partial_baseline_not_protected(self):
        old = dict(msgid="a", msgid_plural="as", msgstr_plural={0: "b"})
        self.assertEqual(self.pair([old], [])["protected"], 0)

    def test_new_translation_does_not_cancel_loss(self):
        result = self.pair([dict(msgid="a", msgstr="b")], [dict(msgid="c", msgstr="d")])
        self.assertEqual(result["baseline"]["ready"], result["candidate"]["ready"])
        self.assertEqual(result["regression_count"], 1)

    def test_duplicate_active_identity_rejected(self):
        path = self.write("dup.po", [dict(msgid="a", msgstr="b"), dict(msgid="a", msgstr="c")])
        with self.assertRaisesRegex(CatalogError, "duplicate_message_identity"):
            compare_catalogs(path, path)

    def test_active_and_obsolete_same_identity(self):
        entries = [dict(msgid="a", msgstr="b"), dict(msgid="a", msgstr="x", obsolete=True)]
        self.assertEqual(self.pair(entries, entries)["status"], "pass")

    def test_locale_mismatch(self):
        old = self.write("old.po", [], Language="fr")
        new = self.write("new.po", [], Language="de")
        with self.assertRaisesRegex(CatalogError, "language_mismatch"):
            compare_catalogs(old, new)

    def test_missing_locale(self):
        path = self.write("bad.po", [], Language="")
        with self.assertRaisesRegex(CatalogError, "missing_or_invalid_language"):
            compare_catalogs(path, path)

    def test_plural_header_is_not_executed(self):
        path = self.write(
            "meta.po", [], **{"Plural-Forms": "nplurals=2; plural=__import__('os').abort();"}
        )
        self.assertEqual(compare_catalogs(path, path)["status"], "pass")

    def test_plural_metadata_mismatch(self):
        old = self.write("old.po", [])
        new = self.write("new.po", [], **{"Plural-Forms": "nplurals=3; plural=0;"})
        with self.assertRaisesRegex(CatalogError, "nplurals_mismatch"):
            compare_catalogs(old, new)

    def test_invalid_plural_headers(self):
        for header in [
            "nplurals=0;",
            "nplurals=21;",
            "nplurals=-1;",
            "plural=n;",
            "nplurals=2; nplurals=3;",
            "nplurals=" + "9" * 500 + ";",
        ]:
            with self.subTest(header=header[:30]):
                path = self.write("bad.po", [], **{"Plural-Forms": header})
                with self.assertRaisesRegex(CatalogError, "invalid_nplurals"):
                    compare_catalogs(path, path)

    def test_plural_requires_header(self):
        path = self.write(
            "bad.po",
            [dict(msgid="a", msgid_plural="as", msgstr_plural={0: "b"})],
            **{"Plural-Forms": ""},
        )
        with self.assertRaisesRegex(CatalogError, "plural_header_required"):
            compare_catalogs(path, path)

    def test_plural_index_range(self):
        path = self.write(
            "bad.po", [dict(msgid="a", msgid_plural="as", msgstr_plural={0: "b", 7: "bs"})]
        )
        with self.assertRaisesRegex(CatalogError, "plural_index_out_of_range"):
            compare_catalogs(path, path)

    def test_whitespace_is_a_usable_translation(self):
        result = self.pair([dict(msgid=" ", msgstr=" ")], [dict(msgid=" ", msgstr=" ")])
        self.assertEqual(result["protected"], 1)

    def test_no_translation_text_in_report(self):
        result = self.pair([dict(msgid="SECRET-SOURCE", msgstr="SECRET-TARGET")], [])
        serialized = json.dumps(result)
        self.assertNotIn("SECRET", serialized)
        self.assertEqual(len(result["findings"][0]["identity_sha256"]), 64)

    def test_budget_and_findings_bound(self):
        entries = [dict(msgid=str(i), msgstr="x") for i in range(30)]
        result = self.pair(entries, [], max_findings=2, max_regressions=29)
        self.assertEqual(result["regression_count"], 30)
        self.assertEqual(len(result["findings"]), 2)
        self.assertTrue(result["findings_truncated"])
        self.assertEqual(self.pair(entries, [], max_regressions=30)["status"], "pass")

    def test_invalid_options(self):
        for options in [
            dict(max_bytes=0),
            dict(max_findings=-1),
            dict(max_regressions=-1),
            dict(max_regressions=True),
        ]:
            with self.subTest(options=options), self.assertRaises(CatalogError):
                self.pair([], [], **options)

    def test_invalid_file_and_size(self):
        old = self.write("old.po", [])
        for path, code in [
            (self.root / "absent.po", "not_regular_file"),
            (self.root, "not_regular_file"),
        ]:
            with self.assertRaisesRegex(CatalogError, code):
                compare_catalogs(old, path)
        with self.assertRaisesRegex(CatalogError, "size_limit"):
            compare_catalogs(old, old, max_bytes=10)

    def test_bad_encoding_nul_and_syntax(self):
        good = self.write("good.po", [])
        for content, code in [
            (b"\xff", "not_utf8"),
            (b"\x00", "nul_byte"),
            (b'msgid "unclosed\nSECRET', "invalid_po"),
        ]:
            path = self.root / "bad.po"
            path.write_bytes(content)
            with self.assertRaisesRegex(CatalogError, code):
                compare_catalogs(good, path)

    def test_wrong_declared_charset(self):
        path = self.write("bad.po", [], **{"Content-Type": "text/plain; charset=ISO-8859-1"})
        with self.assertRaisesRegex(CatalogError, "utf8_header_required"):
            compare_catalogs(path, path)

    def test_utf8_bom_and_multiline(self):
        path = self.write("good.po", [dict(msgid="long\n文本", msgstr="Texte\nlong")])
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        self.assertEqual(compare_catalogs(path, path)["protected"], 1)

    def test_cli_and_unchanged_inputs(self):
        old = self.write("old.po", [dict(msgid="hidden-source", msgstr="hidden-target")])
        new = self.write("new.po", [])
        before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (old, new)]
        for args, expected in [
            ([str(old), str(old)], 0),
            ([str(old), str(new)], 1),
            ([str(old), "missing.po"], 2),
        ]:
            run = subprocess.run(
                [sys.executable, "-m", "catalog_regress", *args, "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, expected, run.stderr)
            self.assertIn(json.loads(run.stdout)["status"], ["pass", "regression", "error"])
            self.assertNotIn("hidden-source", run.stdout + run.stderr)
        after = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (old, new)]
        self.assertEqual(before, after)

    def test_text_cli(self):
        import contextlib

        old = self.write("old.po", [dict(msgid="a", msgstr="b")])
        new = self.write("new.po", [])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main([str(old), str(new), "--max-findings", "0"]), 1)
        self.assertIn("omitted", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main([str(old), "missing.po"]), 2)
        self.assertIn("ERROR", out.getvalue())


if __name__ == "__main__":
    unittest.main()
