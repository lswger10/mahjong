"""Private room routes: every player identity is derived from an HttpOnly guest session."""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from game.room_manager import RoomManager
from api.access import COOKIE, DATA_DIR, SESSION_SECONDS, guests, principal, check_origin, member, join, view

router = APIRouter()
room_manager = RoomManager(DATA_DIR / 'rooms')

class GuestBody(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    nickname: str | None = Field(default=None, min_length=1, max_length=32)

class RoomBody(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=64)
    ai_fill: bool = True

class JoinBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

@router.post('/guest')
async def guest_session(request: Request, response: Response, body: GuestBody = GuestBody()):
    check_origin(request)
    token, record = guests.issue(request.cookies.get(COOKIE), body.nickname)
    response.set_cookie(COOKIE, token, httponly=True, secure=request.url.scheme == 'https',
                        samesite='strict', max_age=SESSION_SECONDS, path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {'id': record['id'], 'nickname': record['nickname']}

@router.get('/rooms')
async def list_rooms(request: Request):
    who = principal(request)
    return [r.to_dict() for r in room_manager.get_rooms()
            if who['id'] in r.members and not r.members[who['id']]['left']]

@router.post('/rooms', status_code=201)
async def create_room(request: Request, body: RoomBody = RoomBody()):
    who = principal(request)
    room = room_manager.create_room(body.name)
    room.owner_id, room.ai_fill = who['id'], body.ai_fill
    join(room_manager, room.id, who['id'], who['nickname'])
    return room.to_dict()

@router.post('/rooms/{room_id}/join')
async def join_room(room_id: str, request: Request, body: JoinBody = JoinBody()):
    who = principal(request)
    room = join(room_manager, room_id, who['id'], who['nickname'])
    from api.websocket import _broadcast_room_update
    await _broadcast_room_update(room_id)
    return {'room_id': room.id, 'player_idx': room.human_players.index(who['id']),
            'was_redirected': False, 'room': room.to_dict()}

@router.get('/rooms/{room_id}')
async def read_room(room_id: str, request: Request):
    who = principal(request)
    if request.query_params:
        raise HTTPException(400, 'mahjong.identity_parameters_forbidden')
    return view(room_manager, room_id, who['id'])

@router.post('/rooms/{room_id}/action')
async def action(room_id: str, request: Request):
    who = principal(request)
    member(room_manager, room_id, who['id'])
    from api.websocket import submit
    return await submit(room_id, who['id'], await request.json())

@router.post('/rooms/{room_id}/start')
async def start(room_id: str, request: Request):
    who = principal(request)
    room = member(room_manager, room_id, who['id'], owner=True)
    from api.websocket import submit
    result = await submit(room_id, who['id'], {'type': 'start_game', 'revision': room.revision})
    return {**result, 'status': room.status, 'players': result['state']['players']}

@router.post('/rooms/{room_id}/leave')
async def leave(room_id: str, request: Request):
    who = principal(request)
    room = member(room_manager, room_id, who['id'])
    room.members[who['id']]['left'] = True
    room_manager.save_room(room)
    from api.websocket import _connections, _broadcast_room_update
    ws = _connections.get(room_id, {}).get(who['id'])
    if ws:
        await ws.close(code=4403)
    await _broadcast_room_update(room_id)
    return {'ok': True}

@router.post('/rooms/{room_id}/end')
async def end(room_id: str, request: Request):
    who = principal(request)
    room = member(room_manager, room_id, who['id'], owner=True)
    room.status = 'closed'
    room_manager.save_room(room)
    from api.websocket import stop_room, _broadcast_room_update
    stop_room(room_id)
    await _broadcast_room_update(room_id)
    return {'ok': True}
