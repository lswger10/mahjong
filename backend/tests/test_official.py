"""Actual MCP HTTP contract with synthetic platform identities, no paid models."""
import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from api.access import join
from api.routes import room_manager
from api.official import build_mcp, PLAY_LOOP
from api.websocket import _broadcast_game_state, _handle_message, ActionReceipt


@pytest.mark.asyncio
async def test_official_wait_read_act_repeat_identity_and_cancellation():
    room = room_manager.create_room('人工官端测试')
    # Jiao is dealer for a deterministic opening action; humans occupy the other seats.
    app = build_mcp(18991).streamable_http_app()
    meta = {'openai/subject': 'synthetic-owner', 'openai/session': 'synthetic-response', 'openai/organization': 'test'}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:18991') as client:
            async def call(name, args, identity=meta):
                response = await client.post('/mcp', headers={'Accept': 'application/json, text/event-stream'}, json={
                    'jsonrpc': '2.0', 'id': str(uuid4()), 'method': 'tools/call',
                    'params': {'name': name, 'arguments': args, '_meta': identity}})
                assert response.status_code == 200, response.text
                result = response.json()['result']
                if result.get('isError'):
                    return result
                return result.get('structuredContent') or json.loads(result['content'][0]['text'])

            assert (await call('join_table', {'room_code': room.id, 'instance_id': str(uuid4())}, {}))['isError']
            instance = str(uuid4())
            joined = await call('join_table', {'room_code': room.id, 'instance_id': instance})
            assert joined['next']['tool'] == 'read_turn'
            args = {'room_id': room.id, 'lease_id': joined['lease_id']}
            pid = room.human_players[0]
            for n in range(1, 4):
                join(room_manager, room.id, f'human-{uuid4()}', f'朋友{n}')
            room.owner_id = room.human_players[1]
            room_manager.start_game(room.id)
            await _broadcast_game_state(room.id)
            read = await call('read_turn', args)
            assert read['is_your_turn']
            assert all(p['hand']['hidden'] for p in read['state']['players'][1:])
            assert (await call('read_turn', args, {**meta, 'openai/subject': 'other'}))['isError']
            busy = await call('join_table', {'room_code': room.id, 'instance_id': str(uuid4())})
            assert busy['status'] == 'controller_active' and 'lease_id' not in busy
            move = next(a for a in read['legal_actions'] if a['type'] == 'discard')
            accepted = await call('submit_action', {**args, 'revision': read['revision'], 'action': move})
            assert accepted['next']['tool'] == 'wait_for_event'
            assert accepted['next']['cursor'] == accepted['last_event_id']
            assert (await call('submit_action', {**args, 'revision': read['revision'], 'action': move}))['isError']

            from api.websocket import submit
            from api.access import view
            acted = set()
            async def opponents():
                while room.status == 'playing':
                    gs = room.game_state
                    for idx in range(1, 4):
                        options = gs.get_available_actions(idx)
                        kind = 'skip' if 'skip' in options else 'discard' if 'discard' in options else None
                        if kind:
                            action = {'type': kind, 'revision': room.revision}
                            if kind == 'discard':
                                action['tile'] = gs.players[idx].hand[-1]
                                acted.add(idx)
                            await submit(room.id, room.human_players[idx], action)
                            await asyncio.sleep(.2)
                    await asyncio.sleep(.01)
            gs = room.game_state
            driver = asyncio.create_task(opponents())
            try:
                discards = 1
                waits = 0
                for _ in range(30):
                    event = await call('wait_for_event', {**args, 'cursor': accepted['cursor'], 'last_event_id': accepted['last_event_id']})
                    waits += 1
                    assert event['next']['cursor'] == event['last_event_id']
                    accepted = await call('read_turn', args)
                    actions = accepted['legal_actions']
                    if actions:
                        action = next((a for a in actions if a['type'] == 'skip'), actions[0])
                        submitted = await call('submit_action', {**args, 'revision': accepted['revision'], 'action': action})
                        if not submitted.get('isError'):
                            assert submitted['next']['tool'] == 'wait_for_event'
                            accepted = submitted
                            discards += action['type'] == 'discard'
                    else:
                        assert accepted['next']['tool'] == 'wait_for_event'
                    if discards >= 2 and acted == {1, 2, 3}:
                        break
                assert discards >= 2 and acted == {1, 2, 3} and waits >= 2
            finally:
                driver.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await driver
            # A cancelled platform request must not leave or convert the official seat.
            room.status = 'ended'
            room_manager.save_room(room)
            read = await call('read_turn', args)
            waiting = asyncio.create_task(call('wait_for_event', {**args, 'cursor': read['cursor'], 'last_event_id': read['last_event_id']}))
            await asyncio.sleep(.2)
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
            assert not room.members[pid]['left'] and not gs.players[0].is_ai
            assert (await call('read_turn', args))['next']['tool'] == 'wait_for_event'


@pytest.mark.asyncio
async def test_tool_descriptions_all_include_next_hop():
    tools = await build_mcp(18991).list_tools()
    descriptions = {tool.name: tool.description for tool in tools}
    assert len(tools) == 5
    for name in ('join_table', 'read_turn', 'wait_for_event', 'submit_action'):
        assert PLAY_LOOP in descriptions[name]
        assert 'wait_for_event' in descriptions[name]


def test_room_and_session_restart_roundtrip(tmp_path):
    from api.access import Guests
    from game.room_manager import RoomManager
    sessions = Guests(tmp_path)
    token, who = sessions.issue(None, '恢复测试')
    manager = RoomManager(tmp_path / 'rooms')
    first = manager.create_room('房间一')
    second = manager.create_room('房间二')
    join(manager, first.id, who['id'], who['nickname'])
    manager.start_game(first.id)
    manager.save_room(first)
    manager.save_room(second)
    before = first.game_state.to_dict(0)
    restored = RoomManager(tmp_path / 'rooms')
    assert Guests(tmp_path).get(token)['id'] == who['id']
    assert restored.get_room(first.id).game_state.to_dict(0) == before
    assert restored.get_room(first.id).human_players == [who['id']]
    assert restored.get_room(second.id).status == 'waiting'
    assert restored.get_room(second.id).game_state is None


@pytest.mark.asyncio
async def test_local_ai_rooms_complete_independently_and_closed_tasks_cannot_revive(monkeypatch):
    from api import websocket as driver
    from api.websocket import submit, stop_room
    monkeypatch.setattr(driver.random, 'uniform', lambda a, b: .001)
    monkeypatch.setattr(driver, 'CLAIM_TIMEOUT', .05)
    rooms = []
    for n in range(2):
        room = room_manager.create_room(f'Local AI {n}')
        room.owner_id = str(uuid4())
        join(room_manager, room.id, room.owner_id, '人工牌手')
        await submit(room.id, room.owner_id, {'type': 'start_game', 'revision': room.revision})
        rooms.append(room)
    untouched = rooms[1].game_state.to_dict(0)
    await submit(rooms[0].id, rooms[0].owner_id, {'type': 'discard', 'tile': rooms[0].game_state.players[0].hand[0], 'revision': rooms[0].revision})
    await asyncio.sleep(.015)
    assert rooms[1].game_state.to_dict(0) == untouched
    for _ in range(3000):
        for room in rooms:
            gs = room.game_state
            if room.status != 'playing':
                continue
            actions = gs.get_available_actions(0)
            kind = next((a for a in ('win', 'skip', 'discard') if a in actions), None)
            if kind:
                action = {'type': kind, 'revision': room.revision}
                if kind == 'discard':
                    action['tile'] = gs.players[0].hand[-1]
                await submit(room.id, room.owner_id, action)
        if all(room.status == 'ended' for room in rooms):
            break
        await asyncio.sleep(.005)
    assert all(room.status == 'ended' for room in rooms)
    assert all(sum(room.cumulative_scores.values()) == 4000 for room in rooms)
    room = rooms[0]
    await submit(room.id, room.owner_id, {'type': 'restart_game', 'revision': room.revision})
    if 'discard' in room.game_state.get_available_actions(0):
        await submit(room.id, room.owner_id, {'type': 'discard', 'tile': room.game_state.players[0].hand[0], 'revision': room.revision})
    await asyncio.sleep(.002)
    room.status = 'closed'
    room_manager.save_room(room)
    stop_room(room.id)
    frozen = room.game_state.to_dict(0)
    await asyncio.sleep(.03)
    assert room.status == 'closed' and room.game_state.to_dict(0) == frozen


@pytest.mark.asyncio
async def test_cancelled_submit_keeps_committed_continuation(monkeypatch):
    from api import websocket as driver
    room = room_manager.create_room('取消请求测试')
    for n in range(4):
        join(room_manager, room.id, f'cancel-{n}', f'朋友{n}')
    room.owner_id = room.human_players[0]
    room_manager.start_game(room.id)
    entered, release, continued = asyncio.Event(), asyncio.Event(), asyncio.Event()
    class BlockedSocket:
        async def send_json(self, payload):
            entered.set()
            await release.wait()
    async def continuation(rid):
        assert rid == room.id
        continued.set()
    monkeypatch.setattr(driver, '_handle_claim_window', continuation)
    driver._connections[room.id] = {room.owner_id: BlockedSocket()}
    request = asyncio.create_task(driver.submit(room.id, room.owner_id, {
        'type': 'discard', 'tile': room.game_state.players[0].hand[0], 'revision': room.revision}))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        await asyncio.wait_for(continued.wait(), 1)
        assert room.game_state.phase == 'claiming'
        assert not room.members[room.owner_id]['left']
    finally:
        release.set()
        driver._connections.pop(room.id, None)


@pytest.mark.asyncio
async def test_official_membership_and_lease_commit_together(tmp_path, monkeypatch):
    from api import access, official
    from game.room_manager import RoomManager
    manager = RoomManager(tmp_path)
    room = manager.create_room('原子入座')
    join(manager, room.id, 'owner', '房主')
    monkeypatch.setattr(official, 'room_manager', manager)
    original = access.atomic_json
    writes = []
    def counted(path, value):
        writes.append(value)
        if len(writes) == 2:
            raise OSError('synthetic second write failure')
        original(path, value)
    monkeypatch.setattr(access, 'atomic_json', counted)
    class Meta:
        def model_dump(self):
            return {'openai/subject': 'test', 'openai/session': 'test'}
    from types import SimpleNamespace
    ctx = SimpleNamespace(request_context=SimpleNamespace(meta=Meta()))
    mcp = build_mcp(18991)
    tool = mcp._tool_manager.get_tool('join_table')
    result = await tool.fn(room.id, str(uuid4()), ctx)
    assert result['lease_id'] and len(writes) == 1
    restored = RoomManager(tmp_path).get_room(room.id)
    assert restored.official['player_id'] == restored.human_players[1]
    assert restored.members[restored.official['player_id']]['kind'] == 'external_agent'


@pytest.mark.asyncio
@pytest.mark.parametrize('old_timeout', [False, True])
async def test_pung_then_immediate_discard_starts_distinct_ai_claim_window(monkeypatch, old_timeout):
    from api import websocket as driver
    room = room_manager.create_room('连续响应窗回归')
    pid = str(uuid4())
    join(room_manager, room.id, pid, '人工牌手')
    room_manager.start_game(room.id)
    gs = room.game_state
    gs.players[0].hand = ['BAMBOO_1', 'BAMBOO_1', 'CIRCLES_7', 'CIRCLES_2']
    gs.players[1].hand = ['CHARACTERS_8']
    gs.players[2].hand = ['CIRCLES_7', 'CIRCLES_7', 'CIRCLES_7', 'CHARACTERS_8']
    gs.players[3].hand = ['CHARACTERS_9']
    gs.discards[3] = ['BAMBOO_1']
    gs.last_discard, gs.last_discard_player = 'BAMBOO_1', 3
    gs.current_turn, gs.phase = 3, 'claiming'
    gs._pending_claims, gs._skipped_claims, gs._best_claim = {0, 1, 2}, set(), None
    room_manager.save_room(room)
    waiting, next_ai_decision = asyncio.Event(), asyncio.Event()
    original_wait = driver._wait_for_claim_window
    original_decide = driver._ai.decide_claim

    async def observed_wait(*args):
        waiting.set()
        await original_wait(*args)
        if old_timeout:
            raise asyncio.TimeoutError

    def observed_decide(hand, melds, tile, kind):
        if tile == 'CIRCLES_7':
            next_ai_decision.set()
        return original_decide(hand, melds, tile, kind)

    monkeypatch.setattr(driver, '_wait_for_claim_window', observed_wait)
    monkeypatch.setattr(driver._ai, 'decide_claim', observed_decide)
    monkeypatch.setattr(driver.random, 'uniform', lambda a, b: .001)
    first = asyncio.create_task(driver._handle_claim_window(room.id))
    try:
        await asyncio.wait_for(waiting.wait(), 1)
        # Both actions arrive before the old window's 100 ms poll wakes up.
        await driver.submit(room.id, pid, {'type': 'pung', 'revision': room.revision})
        assert gs.phase == 'discarding'
        await driver.submit(room.id, pid, {
            'type': 'discard', 'tile': 'CIRCLES_7', 'revision': room.revision})
        await asyncio.wait_for(next_ai_decision.wait(), 1)
    finally:
        driver.stop_room(room.id)
        jobs = {first, *(task for (rid, _), task in driver._room_jobs.items() if rid == room.id)}
        await asyncio.gather(*jobs, return_exceptions=True)


@pytest.mark.asyncio
async def test_membership_broadcast_does_not_touch_another_room():
    from api import websocket as driver
    rooms = [room_manager.create_room('广播隔离') for _ in range(2)]
    messages = [[], []]
    class Socket:
        def __init__(self, output):
            self.output = output
        async def send_json(self, value):
            self.output.append(value)
    for n, room in enumerate(rooms):
        pid = str(uuid4())
        join(room_manager, room.id, pid, '朋友')
        driver._connections[room.id] = {pid: Socket(messages[n])}
    try:
        await driver._broadcast_room_update(rooms[0].id)
        assert len(messages[0]) == 1 and not messages[1]
    finally:
        for room in rooms:
            driver._connections.pop(room.id, None)
