from forkit.readiness import check_readiness


def test_ready_requires_real_schema_and_storage(db_engine, tmp_path):
    assert check_readiness(db_engine.url.database, str(tmp_path)) == {"status": "ok"}
    assert check_readiness(str(tmp_path / "missing.db"), str(tmp_path)) == {"status": "unavailable"}
    assert not (tmp_path / "missing.db").exists()
    assert check_readiness(db_engine.url.database, str(tmp_path / "missing")) == {
        "status": "unavailable"
    }


def test_ready_rejects_empty_database(tmp_path):
    import sqlite3

    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    assert check_readiness(str(path), str(tmp_path)) == {"status": "unavailable"}
