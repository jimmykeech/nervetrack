from app.models.pain_instances import PainInstanceCreate
from app.services import pain_instances as pi


def _instance(db, user_id, name="Left sciatic"):
    return pi.create_instance(db, user_id, PainInstanceCreate(name=name)).id


def test_add_list_update_delete(auth_client, db, user_id):
    iid = _instance(db, user_id)
    created = auth_client.post(f"/api/v1/pain-instances/{iid}/notes",
                               json={"body": "started physio"})
    assert created.status_code == 201
    note_id = created.json()["id"]

    listed = auth_client.get(f"/api/v1/pain-instances/{iid}").json()["notes"]
    assert [n["body"] for n in listed] == ["started physio"]

    upd = auth_client.patch(f"/api/v1/condition-notes/{note_id}", json={"body": "started PT"})
    assert upd.status_code == 200 and upd.json()["body"] == "started PT"

    assert auth_client.delete(f"/api/v1/condition-notes/{note_id}").status_code == 204


def test_note_on_foreign_instance_rejected(auth_client, db, user_id, make_user):
    other = make_user()
    foreign = _instance(db, other, name="theirs")
    r = auth_client.post(f"/api/v1/pain-instances/{foreign}/notes", json={"body": "x"})
    assert r.status_code == 404


def test_notes_cascade_on_instance_delete(db, user_id):
    iid = _instance(db, user_id)
    from app.services import condition_notes as cn
    cn.add_note(db, user_id, iid, None, "n1")
    with db.cursor():
        db.execute("DELETE FROM pain_instances WHERE id = ?", [iid])
    assert db.query("SELECT id FROM condition_notes WHERE instance_id = ?", [iid]) == []
