from app.models.pain_instances import PainInstanceCreate, PainInstancePatch
from app.models.records import PatientProfileIn
from app.services import pain_instances as pi
from app.services import profile as profile_service
from app.services import records_context


def test_empty_when_nothing_set(db, user_id):
    assert records_context.build(db, user_id) == ""


def test_includes_profile_and_conditions(db, user_id):
    profile_service.save_profile(
        db, user_id, PatientProfileIn(sex="male", lifestyle="desk job"),
    )
    inst = pi.create_instance(db, user_id, PainInstanceCreate(name="Left sciatic"))
    pi.patch_instance(db, user_id, inst.id, PainInstancePatch(background="L5-S1 disc bulge"))

    ctx = records_context.build(db, user_id)
    assert "PATIENT BACKGROUND" in ctx
    assert "desk job" in ctx
    assert "Left sciatic" in ctx
    assert "L5-S1 disc bulge" in ctx
