from decimal import Decimal

from app.models.records import DocumentMeta, PatientProfile


def test_profile_all_optional():
    p = PatientProfile()
    assert p.dob is None and p.height_cm is None


def test_profile_accepts_decimal():
    p = PatientProfile(height_cm=Decimal("178.0"), weight_kg=Decimal("74.5"))
    assert p.height_cm == 178.0
    assert isinstance(p.height_cm, float)


def test_document_meta_has_no_content_field():
    fields = set(DocumentMeta.model_fields)
    assert "content" not in fields
    assert {"id", "owner_type", "title", "filename", "mime_type", "size_bytes"} <= fields
