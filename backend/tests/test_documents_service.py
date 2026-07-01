import pytest

from app.models.pain_instances import PainInstanceCreate
from app.models.records import DocumentPatch
from app.services import documents as docs
from app.services import pain_instances as pi


def _mk(db, user_id, **kw):
    defaults = dict(owner_type="profile", instance_id=None, title="Bloods",
                    notes="normal", filename="b.pdf", mime_type="application/pdf",
                    content=b"%PDF-1.4 data")
    defaults.update(kw)
    return docs.create_document(db, user_id, **defaults)


def test_create_list_download(db, user_id):
    meta = _mk(db, user_id)
    assert meta.size_bytes == len(b"%PDF-1.4 data")

    listed = docs.list_documents(db, user_id)
    assert [m.title for m in listed] == ["Bloods"]
    assert not hasattr(listed[0], "content")

    blob, mime, fname = docs.get_document_blob(db, user_id, meta.id)
    assert blob == b"%PDF-1.4 data" and mime == "application/pdf" and fname == "b.pdf"


def test_reject_oversize_and_bad_mime(db, user_id):
    with pytest.raises(ValueError, match="too large"):
        _mk(db, user_id, content=b"x" * (docs.MAX_BYTES + 1))
    with pytest.raises(ValueError, match="type"):
        _mk(db, user_id, mime_type="application/x-msdownload")


def test_condition_owner_validates_instance(db, user_id, make_user):
    other = make_user()
    foreign = pi.create_instance(db, other, PainInstanceCreate(name="theirs")).id
    with pytest.raises(ValueError, match="pain instance"):
        _mk(db, user_id, owner_type="condition", instance_id=foreign)


def test_filter_and_isolation(db, user_id, make_user):
    iid = pi.create_instance(db, user_id, PainInstanceCreate(name="mine")).id
    _mk(db, user_id, owner_type="condition", instance_id=iid, title="MRI")
    _mk(db, user_id, title="General")
    assert {m.title for m in docs.list_documents(db, user_id, instance_id=iid)} == {"MRI"}
    assert {m.title for m in docs.list_documents(db, user_id, owner_type="profile")} == {"General"}

    other = make_user()
    assert docs.list_documents(db, other) == []


def test_update_and_delete(db, user_id):
    meta = _mk(db, user_id)
    upd = docs.update_document(db, user_id, meta.id, DocumentPatch(title="Blood panel"))
    assert upd.title == "Blood panel"
    assert docs.delete_document(db, user_id, meta.id) is True
    assert docs.get_document_blob(db, user_id, meta.id) is None
