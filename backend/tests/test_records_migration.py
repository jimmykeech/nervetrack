def test_records_tables_exist(db, user_id):
    tables = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"patient_profile", "condition_notes", "documents"} <= tables


def test_blob_round_trips(db, user_id):
    db.execute(
        "INSERT INTO documents (user_id, owner_type, title, content) VALUES (?, 'profile', 't', ?)",
        [user_id, b"\x89PNG\x00bytes"],
    )
    row = db.query_one("SELECT content FROM documents WHERE user_id = ?", [user_id])
    assert row["content"] == b"\x89PNG\x00bytes"
