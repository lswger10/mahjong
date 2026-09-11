"""Guest credentials are server-issued; display names never authorize a seat."""
import hashlib
from dataclasses import replace
import json
import os
from pathlib import Path
import secrets
import time
import uuid

from fastapi import HTTPException

COOKIE = 'mahjong_guest'
DATA_DIR = Path(os.environ.get('MAHJONG_DATA_DIR', 'data'))
SESSION_SECONDS = 30 * 24 * 3600


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, default=lambda v: sorted(v) if isinstance(v, set) else v.isoformat())
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class Guests:
    def __init__(self, directory):
        self.path = directory / 'guests.json'
        self.records = json.loads(self.path.read_text('utf-8')) if self.path.exists() else {}

    def get(self, token):
        record = self.records.get(digest(token)) if token else None
        return record if record and record['expires'] > time.time() else None

    def issue(self, token, nickname):
        record = self.get(token)
        if not record:
            token = secrets.token_urlsafe(32)
            record = {'id': str(uuid.uuid4()), 'nickname': nickname or '朋友', 'expires': 0}
        record = {**record, 'expires': time.time() + SESSION_SECONDS}
        if nickname is not None:
            record['nickname'] = nickname
        candidate = {k: v for k, v in self.records.items() if v['expires'] > time.time()}
        candidate[digest(token)] = record
        atomic_json(self.path, candidate)
        self.records = candidate
        return token, record


guests = Guests(DATA_DIR)


def check_origin(request):
    origin = request.headers.get('origin')
    if origin and origin != f'{request.url.scheme.replace("ws", "http")}://{request.headers.get("host")}':
        raise HTTPException(403, 'mahjong.origin_denied')


def principal(request):
    check_origin(request)
    record = guests.get(request.cookies.get(COOKIE))
    if not record:
        raise HTTPException(401, 'mahjong.session_required')
    return record


def member(manager, room_id, player_id, *, owner=False):
    room = manager.get_room(room_id)
    if not room or player_id not in room.members or room.members[player_id]['left']:
        raise HTTPException(403, 'mahjong.room_access_denied')
    if owner and room.owner_id != player_id:
        raise HTTPException(403, 'mahjong.owner_required')
    if room.status == 'storage_error':
        raise HTTPException(503, 'mahjong.storage_unavailable')
    return room


def join(manager, room_id, player_id, nickname, kind='human', *, official=None):
    room = manager.get_room(room_id)
    if not room or room.status in ('closed', 'storage_error'):
        raise HTTPException(404, 'mahjong.invitation_unavailable')
    if player_id not in room.members:
        if room.status != 'waiting' or room.is_full:
            raise HTTPException(409, 'mahjong.seat_unavailable')
    # Publish a new permission only after its membership record is durable.
    candidate = replace(room, members=dict(room.members), human_players=list(room.human_players))
    if player_id not in candidate.human_players:
        candidate.human_players.append(player_id)
    candidate.members[player_id] = {'nickname': nickname, 'kind': kind, 'left': False}
    if official is not None:
        candidate.official = official
    manager.save_room(candidate)
    room.members, room.human_players, room.revision = candidate.members, candidate.human_players, candidate.revision
    room.official = candidate.official
    return room


def view(manager, room_id, player_id):
    room = member(manager, room_id, player_id)
    idx = room.human_players.index(player_id)
    if room.game_state and room.game_state.players[idx].id != player_id:
        raise HTTPException(409, 'mahjong.seat_unavailable')
    state = room.game_state.to_dict(idx) if room.game_state else None
    if state:
        # Even after settlement a private transport never returns another hand.
        for i, player in enumerate(state['players']):
            player['nickname'] = room.members.get(player['id'], {}).get('nickname', f'Local AI {i + 1}')
            if i != idx:
                player['hand'] = {'hidden': True, 'count': len(room.game_state.players[i].hand)}
        state.update(cumulative_scores=dict(room.cumulative_scores), round_number=room.round_number,
                     revision=room.revision, room_status=room.status,
                     drawn_tile=room.game_state.last_drawn_tile if room.game_state.current_turn == idx else None)
    return {'room_id': room.id, 'room': room.to_dict(), 'self_player_id': player_id, 'player_idx': idx,
            'is_owner': room.owner_id == player_id, 'state': state, 'revision': room.revision,
            'seats': [{'seat': i, **room.members[pid]} for i, pid in enumerate(room.human_players)],
            'ai_fill': room.ai_fill}
