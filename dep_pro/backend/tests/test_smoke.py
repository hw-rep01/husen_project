def test_health_endpoint_reports_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_rejects_wrong_password(client):
    response = client.post("/api/auth/login", json={"email": "student@sdp.local", "password": "wrong-pass"})
    assert response.status_code == 401


def test_login_rejects_unknown_email(client):
    response = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x" * 8})
    assert response.status_code == 401


def test_protected_route_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_invalid_token_is_rejected(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_returns_role_and_section(client, auth):
    body = client.get("/api/auth/me", headers=auth("rep")).json()
    assert body["role"] == "class_representative"
    assert body["section_id"] == 1
