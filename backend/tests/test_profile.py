def test_profile_empty_default(auth_client):
    r = auth_client.get("/api/v1/profile")
    assert r.status_code == 200
    assert r.json()["dob"] is None


def test_profile_upsert_round_trip(auth_client):
    r = auth_client.put("/api/v1/profile", json={
        "dob": "1991-04-01", "sex": "male", "height_cm": "178.0",
        "weight_kg": "74.5", "lifestyle": "desk job, runs 3x/wk",
        "medical_history": "appendectomy 2010",
    })
    assert r.status_code == 200
    got = auth_client.get("/api/v1/profile").json()
    assert got["sex"] == "male"
    assert got["lifestyle"].startswith("desk job")
    assert got["medical_history"] == "appendectomy 2010"


def test_profile_second_put_overwrites(auth_client):
    auth_client.put("/api/v1/profile", json={"sex": "male"})
    auth_client.put("/api/v1/profile", json={"sex": "female", "weight_kg": "70.0"})
    got = auth_client.get("/api/v1/profile").json()
    assert got["sex"] == "female"
