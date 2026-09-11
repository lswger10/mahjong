"""Permanent HTTP/WS regression: server identity, private seats and room isolation."""
import pytest
from fastapi.testclient import TestClient
from main import app
from api.routes import room_manager


def guest(client, nickname='朋友'):
    response = client.post('/api/guest', json={'nickname': nickname})
    assert response.status_code == 200
    return response.json()


def test_sessions_private_views_reconnect_and_cross_identity():
    with TestClient(app) as a:
        b, outsider = TestClient(app), TestClient(app)
        ga, gb = guest(a, '同名'), guest(b, '同名')
        assert ga['id'] != gb['id']
        room = a.post('/api/rooms', json={'name': '人工隔离测试'}).json()
        rid = room['id']
        assert b.post(f'/api/rooms/{rid}/join', json={}).status_code == 200
        assert outsider.get(f'/api/rooms/{rid}').status_code == 401
        guest(outsider)
        assert outsider.get(f'/api/rooms/{rid}').status_code == 403
        assert b.post(f'/api/rooms/{rid}/start').status_code == 403
        assert a.post(f'/api/rooms/{rid}/start').status_code == 200
        va, vb = a.get(f'/api/rooms/{rid}').json(), b.get(f'/api/rooms/{rid}').json()
        assert va['self_player_id'] == ga['id']
        assert vb['self_player_id'] == gb['id']
        assert va['state']['players'][0]['hand']['hidden'] is False
        assert va['state']['players'][1]['hand']['hidden'] is True
        assert vb['state']['players'][0]['hand']['hidden'] is True
        assert vb['state']['players'][1]['hand']['hidden'] is False
        assert a.get(f'/api/rooms/{rid}?player_id={gb["id"]}').status_code == 400
        attack = {'type': 'discard', 'tile': va['state']['players'][0]['hand']['tiles'][0],
                  'revision': va['revision'], 'player_id': ga['id']}
        assert b.post(f'/api/rooms/{rid}/action', json=attack).status_code == 400
        attack.pop('player_id')
        assert b.post(f'/api/rooms/{rid}/action', json=attack).status_code == 409
        with a.websocket_connect(f'/ws/{rid}') as ws:
            welcome = ws.receive_json()
            assert welcome['self_player_id'] == ga['id']
        assert a.get(f'/api/rooms/{rid}').json()['self_player_id'] == ga['id']
        assert b.get(f'/api/rooms/{rid}').json()['room']['status'] == 'playing'
        other = outsider.post('/api/rooms', json={}).json()['id']
        assert a.get(f'/api/rooms/{other}').status_code == 403
        assert a.post(f'/api/rooms/{other}/action', json=attack).status_code == 403
        assert b.post(f'/api/rooms/{rid}/leave').status_code == 200
        assert a.get(f'/api/rooms/{rid}').json()['room']['status'] == 'playing'
        assert b.get(f'/api/rooms/{rid}').status_code == 403
        assert b.post(f'/api/rooms/{rid}/join', json={}).json()['player_idx'] == 1
        assert b.post(f'/api/rooms/{rid}/end').status_code == 403
        assert a.post(f'/api/rooms/{rid}/end').status_code == 200
        assert outsider.get(f'/api/rooms/{other}').json()['room']['status'] == 'waiting'


def test_session_cannot_be_chosen_and_cross_origin_is_rejected():
    with TestClient(app) as c:
        assert c.post('/api/guest', json={'player_id': 'owner'}).status_code == 422
        assert c.post('/api/guest', json={}, headers={'Origin': 'https://evil.invalid'}).status_code == 403
        guest(c)
        assert 'httponly' in c.post('/api/guest', json={}).headers.get('set-cookie', '').lower()
        assert c.post('/api/rooms', json={'player_id': 'owner'}).status_code == 422


def test_failed_membership_write_never_grants_access(tmp_path, monkeypatch):
    from api import access
    from game.room_manager import RoomManager
    from fastapi import HTTPException
    manager = RoomManager(tmp_path)
    room = manager.create_room()
    access.join(manager, room.id, 'original', '原玩家')
    def disk_full(*args):
        raise OSError('synthetic disk full')
    monkeypatch.setattr(access, 'atomic_json', disk_full)
    with pytest.raises(OSError):
        access.join(manager, room.id, 'candidate', '新玩家')
    assert 'candidate' not in room.members and 'candidate' not in room.human_players
    with pytest.raises(HTTPException):
        access.view(manager, room.id, 'candidate')
    with pytest.raises(HTTPException) as error:
        access.view(manager, room.id, 'original')
    assert error.value.status_code == 503


def test_new_members_cannot_inherit_previous_ai_hand(tmp_path):
    from api import access
    from game.room_manager import RoomManager
    from fastapi import HTTPException
    manager = RoomManager(tmp_path)
    room = manager.create_room()
    access.join(manager, room.id, 'original', '原玩家')
    manager.start_game(room.id)
    room.status = 'ended'
    for kind in ('human', 'external_agent'):
        with pytest.raises(HTTPException) as error:
            access.join(manager, room.id, 'late', '后来者', kind)
        assert error.value.status_code == 409
    assert access.view(manager, room.id, 'original')['player_idx'] == 0
    # A corrupt/old binding must also fail closed at the private-view boundary.
    room.human_players.append('late')
    room.members['late'] = {'nickname': '后来者', 'kind': 'human', 'left': False}
    with pytest.raises(HTTPException):
        access.view(manager, room.id, 'late')
