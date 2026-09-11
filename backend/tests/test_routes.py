"""Tests for api/routes.py — REST API endpoints using FastAPI TestClient."""

import pytest
from api.routes import room_manager
from fastapi.testclient import TestClient
from api.routes import router, room_manager
from fastapi import FastAPI


@pytest.fixture(autouse=True)
def clean_rooms():
    """Clear rooms before each test."""
    room_manager._rooms.clear()
    yield
    room_manager._rooms.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    c = TestClient(app)
    c.guest_id = c.post('/api/guest', json={}).json()['id']
    return c


class TestListRooms:
    def test_empty_rooms(self, client):
        resp = client.get("/api/rooms")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_rooms_after_creation(self, client):
        client.post("/api/rooms")
        resp = client.get("/api/rooms")
        assert resp.status_code == 200
        rooms = resp.json()
        assert len(rooms) == 1
        assert "id" in rooms[0]
        assert "name" in rooms[0]


class TestCreateRoom:
    def test_create_room_success(self, client):
        resp = client.post("/api/rooms")
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["status"] == "waiting"

    def test_create_room_with_name(self, client):
        resp = client.post("/api/rooms", json={"name": "My Room"})
        assert resp.status_code == 201
        assert resp.json()["name"] == "My Room"

    def test_create_room_default_name(self, client):
        resp = client.post("/api/rooms")
        assert resp.status_code == 201
        assert resp.json()["name"].startswith("Room ")


class TestJoinRoom:
    def test_join_room_success(self, client):
        create_resp = client.post("/api/rooms")
        room_id = create_resp.json()["id"]
        resp = client.post(f"/api/rooms/{room_id}/join", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["room_id"] == room_id
        assert data["was_redirected"] is False
        assert data["player_idx"] == 0

    def test_join_nonexistent_room_404(self, client):
        resp = client.post("/api/rooms/nonexistent/join", json={})
        assert resp.status_code == 404

    def test_join_full_room_rejected(self, client):
        room_id = client.post('/api/rooms').json()['id']
        for i in range(3):
            client.cookies.clear()
            client.post('/api/guest', json={'nickname': f'朋友{i}'})
            assert client.post(f'/api/rooms/{room_id}/join', json={}).status_code == 200
        client.cookies.clear()
        client.post('/api/guest', json={})
        assert client.post(f'/api/rooms/{room_id}/join', json={}).status_code == 409
        assert len(room_manager.get_rooms()) == 1

    def test_join_room_second_player(self, client):
        room_id = client.post('/api/rooms').json()['id']
        client.cookies.clear()
        client.post('/api/guest', json={})
        response = client.post(f'/api/rooms/{room_id}/join', json={})
        assert response.status_code == 200
        assert response.json()['player_idx'] == 1


class TestStartGame:
    def test_start_game_success(self, client):
        create_resp = client.post("/api/rooms")
        room_id = create_resp.json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={})
        resp = client.post(f"/api/rooms/{room_id}/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "playing"
        assert len(data["players"]) == 4

    def test_start_nonexistent_room_404(self, client):
        resp = client.post("/api/rooms/nonexistent/start")
        assert resp.status_code == 403

    def test_start_already_started_400(self, client):
        create_resp = client.post("/api/rooms")
        room_id = create_resp.json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={})
        client.post(f"/api/rooms/{room_id}/start")
        resp = client.post(f"/api/rooms/{room_id}/start")
        assert resp.status_code == 409

    def test_start_game_has_ai_players(self, client):
        create_resp = client.post("/api/rooms")
        room_id = create_resp.json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={})
        resp = client.post(f"/api/rooms/{room_id}/start")
        data = resp.json()
        ai_players = [p for p in data["players"] if p["is_ai"]]
        assert len(ai_players) == 3
