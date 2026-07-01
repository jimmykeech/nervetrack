from app.services import conversations as conv


def test_create_list_get(db, user_id):
    c = conv.create_conversation(db, user_id, title="First")
    conv.add_message(db, c.id, "user", "hi")
    conv.add_message(db, c.id, "assistant", "hello")

    listed = conv.list_conversations(db, user_id)
    assert [x.id for x in listed] == [c.id]

    detail = conv.get_conversation(db, user_id, c.id)
    assert [m.content for m in detail.messages] == ["hi", "hello"]

    assert conv.history_for_llm(db, c.id) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_isolation_and_delete(db, user_id, make_user):
    other = make_user()
    c = conv.create_conversation(db, user_id)
    assert conv.get_conversation(db, other, c.id) is None
    assert conv.owns(db, other, c.id) is False
    assert conv.delete_conversation(db, other, c.id) is False
    assert conv.delete_conversation(db, user_id, c.id) is True
    assert conv.get_conversation(db, user_id, c.id) is None
