"""Tests for the dataset adapter — ADR-003 / Security sign-off 2026-05-12.

Covers all conditions enumerated in the Security Reviewer sign-off:
  Q2 — FTS5 simple-query mode + bad-input corpus
  Q3 — internal:// URL grammar
  Q4 — SANITIZED_FIELDS schema introspection
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from forkit.dataset.adapter import (
    MAX_QUERY_CHARS,
    MAX_QUERY_TOKENS,
    DatasetAdapter,
    _build_match_expression,
    parse_internal_dataset_url,
)
from forkit.dataset.db import (
    ALL_TEXT_COLUMNS,
    EXEMPT_FIELDS,
    SANITIZED_FIELDS,
    init_schema,
    open_writable,
    set_meta,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_corpus(tmp_path: Path, rows: list[dict]) -> Path:
    """Build a temp dataset DB seeded with the given rows."""
    db_path = tmp_path / "forkit_dataset.db"
    conn = open_writable(db_path)
    try:
        init_schema(conn)
        for i, r in enumerate(rows, start=1):
            conn.execute(
                """
                INSERT INTO recipes (row_id, source_name, source_url, title,
                                     description, ingredients, instructions,
                                     tags, minutes, servings, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    i,
                    r.get("source_name", "foodcom"),
                    r.get("source_url"),
                    r["title"],
                    r.get("description"),
                    r.get("ingredients"),
                    r.get("instructions"),
                    r.get("tags"),
                    r.get("minutes"),
                    r.get("servings"),
                    r.get("image_url"),
                ),
            )
        set_meta(conn, "source_license", "CC-BY-SA-3.0")
        conn.commit()
    finally:
        conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Q2.1 / Q2.2 — _build_match_expression simple-query mode
# ---------------------------------------------------------------------------


class TestBuildMatchExpression:
    def test_plain_query_is_quoted(self):
        assert _build_match_expression("chicken") == '"chicken"'

    def test_multi_word_query(self):
        assert _build_match_expression("tomato sauce") == '"tomato sauce"'

    def test_quote_injection_is_escaped(self):
        # Q2.2: a bare `"` must be doubled.
        assert _build_match_expression('foo"bar') == '"foo""bar"'

    def test_double_quote_payload(self):
        # Attempt to break out: `evil"` -> the trailing quote is doubled.
        assert _build_match_expression('"evil"') == '"""evil"""'

    def test_fts_operator_or_is_neutralized(self):
        # OR/AND/NOT in user input must NOT be interpreted as operators.
        assert _build_match_expression("chicken OR pizza") == '"chicken OR pizza"'

    def test_fts_operator_and_is_neutralized(self):
        assert _build_match_expression("a AND b") == '"a AND b"'

    def test_fts_operator_not_is_neutralized(self):
        assert _build_match_expression("a NOT b") == '"a NOT b"'

    def test_wildcard_star_is_neutralized(self):
        assert _build_match_expression("chick*") == '"chick*"'

    def test_empty_string(self):
        assert _build_match_expression("") == '""'

    def test_whitespace_only(self):
        assert _build_match_expression("    ") == '""'

    def test_max_length_truncation(self):
        long = "a" * 1000
        out = _build_match_expression(long)
        # The whole quoted form must fit MAX_QUERY_CHARS for the inner content.
        inner = out[1:-1]
        assert len(inner) <= MAX_QUERY_CHARS

    def test_token_cap_truncates_to_16(self):
        # 17 tokens should be truncated to 16.
        tokens = [f"t{i}" for i in range(17)]
        out = _build_match_expression(" ".join(tokens))
        inner = out[1:-1]
        assert len(inner.split()) == MAX_QUERY_TOKENS

    def test_nul_byte(self):
        # NUL byte must be quoted, never raise.
        out = _build_match_expression("foo\x00bar")
        assert out.startswith('"') and out.endswith('"')

    def test_unicode_rtl(self):
        out = _build_match_expression("مرحبا chicken")
        assert out.startswith('"') and out.endswith('"')

    def test_emoji(self):
        out = _build_match_expression("pizza 🍕 sauce")
        assert out.startswith('"') and out.endswith('"')

    def test_sql_injection_shaped_payload(self):
        # SQL injection shape can't escape parameterized binding; FTS5 just
        # sees a literal string.
        out = _build_match_expression("'; DROP TABLE recipes;--")
        assert out.startswith('"') and out.endswith('"')


# ---------------------------------------------------------------------------
# Q2.4 / Q2.5 — adapter.search never raises, returns [] on bad input
# ---------------------------------------------------------------------------


class TestAdapterSearchSafety:
    @pytest.fixture
    def adapter(self, tmp_path: Path) -> DatasetAdapter:
        db_path = _make_corpus(
            tmp_path,
            [
                {"title": "Chicken Soup", "ingredients": "chicken broth salt"},
                {"title": "Tomato Sauce", "ingredients": "tomato olive oil garlic"},
            ],
        )
        return DatasetAdapter(db_path)

    def _run(self, coro):
        return asyncio.run(coro)

    def test_plain_query_returns_results(self, adapter):
        results = self._run(adapter.search("chicken"))
        assert len(results) >= 1
        assert results[0].title == "Chicken Soup"

    def test_empty_query_returns_empty(self, adapter):
        # An empty-quote MATCH may either parse-error or return nothing;
        # either way the contract is [] without exception.
        results = self._run(adapter.search(""))
        assert results == []

    def test_only_punctuation(self, adapter):
        results = self._run(adapter.search("!!!"))
        assert isinstance(results, list)

    def test_unbalanced_quote_payload(self, adapter):
        # The escaper doubles the trailing `"`, so FTS5 sees a well-formed
        # quoted phrase. Should never raise.
        results = self._run(adapter.search('chicken"'))
        assert isinstance(results, list)

    def test_fts_operator_names(self, adapter):
        # All four operator-shaped inputs must not raise.
        for q in ["AND", "OR", "NOT", "NEAR"]:
            results = self._run(adapter.search(q))
            assert isinstance(results, list)

    def test_huge_input_returns_safely(self, adapter):
        big = "a" * 10_000
        results = self._run(adapter.search(big))
        assert isinstance(results, list)

    def test_nul_byte_input(self, adapter):
        results = self._run(adapter.search("foo\x00bar"))
        assert isinstance(results, list)

    def test_emoji_input(self, adapter):
        results = self._run(adapter.search("🍕"))
        assert isinstance(results, list)

    def test_sql_injection_shaped(self, adapter):
        results = self._run(adapter.search("'; DROP TABLE recipes;--"))
        assert isinstance(results, list)

    def test_unicode_rtl(self, adapter):
        results = self._run(adapter.search("مرحبا"))
        assert isinstance(results, list)

    def test_missing_db_returns_empty(self, tmp_path):
        adapter = DatasetAdapter(tmp_path / "does-not-exist.db")
        assert adapter.is_available() is False
        results = self._run(adapter.search("anything"))
        assert results == []


# ---------------------------------------------------------------------------
# Q3.2 — internal://dataset/<row_id> grammar
# ---------------------------------------------------------------------------


class TestInternalUrlParser:
    def test_valid_row_id(self):
        assert parse_internal_dataset_url("internal://dataset/1") == 1
        assert parse_internal_dataset_url("internal://dataset/42") == 42
        assert parse_internal_dataset_url("internal://dataset/1234567890") == 1234567890

    def test_zero_rejected(self):
        with pytest.raises(ValueError):
            parse_internal_dataset_url("internal://dataset/0")

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            parse_internal_dataset_url("internal://dataset/-1")

    def test_leading_zero_rejected(self):
        with pytest.raises(ValueError):
            parse_internal_dataset_url("internal://dataset/01")

    def test_float_rejected(self):
        with pytest.raises(ValueError):
            parse_internal_dataset_url("internal://dataset/1.5")

    def test_path_traversal_attempt(self):
        with pytest.raises(ValueError):
            parse_internal_dataset_url("internal://dataset/../etc/passwd")
        with pytest.raises(ValueError):
            parse_internal_dataset_url("internal://dataset/1/../foo")

    def test_scheme_mismatch(self):
        with pytest.raises(ValueError):
            parse_internal_dataset_url("http://dataset/1")
        with pytest.raises(ValueError):
            parse_internal_dataset_url("file:///etc/passwd")
        with pytest.raises(ValueError):
            parse_internal_dataset_url("javascript:alert(1)")

    def test_wrong_namespace(self):
        with pytest.raises(ValueError):
            parse_internal_dataset_url("internal://other/1")
        with pytest.raises(ValueError):
            parse_internal_dataset_url("internal://1")

    def test_query_string_rejected(self):
        with pytest.raises(ValueError):
            parse_internal_dataset_url("internal://dataset/1?x=1")

    def test_fragment_rejected(self):
        with pytest.raises(ValueError):
            parse_internal_dataset_url("internal://dataset/1#frag")

    def test_oversized_row_id(self):
        # 11-digit number is rejected by the regex.
        with pytest.raises(ValueError):
            parse_internal_dataset_url("internal://dataset/99999999999")

    def test_non_integer_payload(self):
        with pytest.raises(ValueError):
            parse_internal_dataset_url("internal://dataset/abc")

    def test_non_string_input(self):
        with pytest.raises(ValueError):
            parse_internal_dataset_url(None)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            parse_internal_dataset_url(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Q4.3 — SANITIZED_FIELDS schema introspection
# ---------------------------------------------------------------------------


class TestSanitizedFieldsCoverage:
    def test_every_text_column_is_categorized(self, tmp_path):
        """Q4.3: every TEXT column in `recipes` must be in either
        SANITIZED_FIELDS or EXEMPT_FIELDS. New TEXT columns fail CI until
        explicitly categorized.
        """
        db_path = _make_corpus(tmp_path, [])
        conn = sqlite3.connect(db_path)
        try:
            cols = conn.execute("PRAGMA table_info(recipes)").fetchall()
        finally:
            conn.close()

        text_columns = {row[1] for row in cols if str(row[2]).upper() == "TEXT"}
        categorized = set(SANITIZED_FIELDS) | set(EXEMPT_FIELDS)

        uncategorized = text_columns - categorized
        assert not uncategorized, (
            f"TEXT columns missing from SANITIZED_FIELDS / EXEMPT_FIELDS: "
            f"{uncategorized}. Categorize them in dataset/db.py."
        )

    def test_sanitized_and_exempt_dont_overlap(self):
        assert not (set(SANITIZED_FIELDS) & set(EXEMPT_FIELDS))

    def test_all_text_columns_constant_matches_union(self):
        assert set(ALL_TEXT_COLUMNS) == set(SANITIZED_FIELDS) | set(EXEMPT_FIELDS)

    def test_adapter_published_fields_match_db(self):
        # DatasetAdapter.SANITIZED_FIELDS should mirror dataset.db.SANITIZED_FIELDS.
        assert tuple(DatasetAdapter.SANITIZED_FIELDS) == tuple(SANITIZED_FIELDS)


# ---------------------------------------------------------------------------
# Q4.4 — dataset_meta records bleach_version + sanitizer_config_hash
# ---------------------------------------------------------------------------


class TestImporterMeta:
    def test_importer_writes_required_meta(self, tmp_path):
        """The importer must record license, bleach version, and config hash."""
        import csv

        from forkit.dataset.db import get_meta, open_readonly
        from forkit.dataset.importer import import_foodcom

        csv_path = tmp_path / "RAW_recipes.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "name",
                    "minutes",
                    "n_servings",
                    "tags",
                    "description",
                    "ingredients",
                    "steps",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "name": "Test Recipe",
                    "minutes": "30",
                    "n_servings": "4",
                    "tags": "['dinner','easy']",
                    "description": "A simple test.",
                    "ingredients": "['chicken','salt']",
                    "steps": "['cook','serve']",
                }
            )

        db_path = tmp_path / "out.db"
        result = import_foodcom(
            data_path=csv_path,
            db_path=db_path,
            accept_license=True,
        )
        assert result["row_count"] == 1

        conn = open_readonly(db_path)
        try:
            assert get_meta(conn, "source_license") == "CC-BY-SA-3.0"
            assert get_meta(conn, "source_name") == "foodcom"
            assert get_meta(conn, "bleach_version") is not None
            sh = get_meta(conn, "sanitizer_config_hash")
            assert sh and len(sh) == 64  # SHA-256 hex
            assert get_meta(conn, "kaggle_terms_acknowledged_at") is not None
        finally:
            conn.close()

    def test_importer_requires_accept_license(self, tmp_path):
        from forkit.dataset.importer import LicenseNotAcceptedError, import_foodcom

        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("name,ingredients\n")

        with pytest.raises(LicenseNotAcceptedError):
            import_foodcom(
                data_path=csv_path,
                db_path=tmp_path / "x.db",
                accept_license=False,
            )


# ---------------------------------------------------------------------------
# Q3.5 — read-only handle blocks writes
# ---------------------------------------------------------------------------


class TestReadOnlyHandle:
    def test_readonly_handle_cannot_write(self, tmp_path):
        """The ?mode=ro&immutable=1 handle MUST refuse writes."""
        from forkit.dataset.db import open_readonly

        db_path = _make_corpus(tmp_path, [{"title": "X", "ingredients": "y"}])
        conn = open_readonly(db_path)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO recipes(row_id, source_name, title) VALUES (99, 'x', 'y')")
        conn.close()


# ---------------------------------------------------------------------------
# Registry — adapter_kind allowlist includes "dataset"
# ---------------------------------------------------------------------------


def test_registry_allowlist_contains_dataset():
    from forkit.discovery.registry import ALLOWED_ADAPTER_KINDS

    assert "dataset" in ALLOWED_ADAPTER_KINDS
