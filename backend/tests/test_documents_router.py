from app.models.pain_instances import PainInstanceCreate
from app.services import pain_instances as pi


def _upload(auth_client, **form):
    data = {"title": "Bloods", "owner_type": "profile"}
    data.update({k: v for k, v in form.items() if k != "file"})
    files = {"file": form.get("file", ("b.pdf", b"%PDF-1.4 x", "application/pdf"))}
    return auth_client.post("/api/v1/documents", data=data, files=files)


def test_upload_list_download_delete(auth_client):
    r = _upload(auth_client, notes="normal")
    assert r.status_code == 201
    doc_id = r.json()["id"]
    assert "content" not in r.json()

    listed = auth_client.get("/api/v1/documents?owner_type=profile").json()
    assert any(d["id"] == doc_id for d in listed)

    dl = auth_client.get(f"/api/v1/documents/{doc_id}/download")
    assert dl.status_code == 200 and dl.content == b"%PDF-1.4 x"
    assert dl.headers["content-type"].startswith("application/pdf")

    assert auth_client.delete(f"/api/v1/documents/{doc_id}").status_code == 204


def test_upload_bad_mime_rejected(auth_client):
    r = _upload(auth_client, file=("m.exe", b"MZ", "application/x-msdownload"))
    assert r.status_code == 400


def test_condition_detail_aggregate(auth_client, db, user_id):
    iid = pi.create_instance(db, user_id, PainInstanceCreate(name="Left sciatic")).id
    auth_client.post(f"/api/v1/pain-instances/{iid}/notes", json={"body": "started PT"})
    _upload(auth_client, owner_type="condition", instance_id=str(iid), title="MRI")

    detail = auth_client.get(f"/api/v1/pain-instances/{iid}").json()
    assert detail["instance"]["name"] == "Left sciatic"
    assert [n["body"] for n in detail["notes"]] == ["started PT"]
    assert [d["title"] for d in detail["documents"]] == ["MRI"]


def test_download_isolation(auth_client, db, make_user):
    other = make_user()
    from app.services import documents as docs
    meta = docs.create_document(
        db, other, owner_type="profile", instance_id=None, title="theirs",
        notes=None, filename="x.pdf", mime_type="application/pdf", content=b"secret",
    )
    assert auth_client.get(f"/api/v1/documents/{meta.id}/download").status_code == 404
