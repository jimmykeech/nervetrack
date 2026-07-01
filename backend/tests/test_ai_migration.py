def test_ai_tables_exist(db, user_id):
    tables = {
        r["name"]
        for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"llm_settings", "conversations", "messages"} <= tables

    # Cascade delete: messages go when their conversation goes.
    conv = db.query_one(
        "INSERT INTO conversations (user_id, title) VALUES (?, 'x') RETURNING id",
        [user_id],
    )
    db.execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (?, 'user', 'hi')",
        [conv["id"]],
    )
    with db.cursor():
        db.execute("DELETE FROM conversations WHERE id = ?", [conv["id"]])
    assert db.query("SELECT id FROM messages WHERE conversation_id = ?", [conv["id"]]) == []
