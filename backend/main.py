"""
main.py - FastAPI application entry point for the Mahjong game.

Run with:
  cd backend
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import sys
import os
import asyncio
from contextlib import asynccontextmanager, nullcontext
import uvicorn

# Ensure the backend directory is on the Python path so that
# `from game.xxx import ...` and `from api.xxx import ...` work correctly.
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.routes import router as rest_router
from api.websocket import router as ws_router

@asynccontextmanager
async def lifespan(app):
    from api.routes import room_manager
    from api.websocket import _run_ai_turn, _handle_claim_window, _room_jobs
    server = task = None
    try:
        port = int(os.environ.get('MAHJONG_MCP_PORT', '0'))
        if port:
            if not 1024 <= port <= 65535:
                raise ValueError('Invalid MAHJONG_MCP_PORT')
            from api.official import build_mcp
            mcp_app = build_mcp(port).streamable_http_app()
            @mcp_app.middleware('http')
            async def local_tunnel_only(request, call_next):
                from starlette.responses import Response
                if request.headers.get('host') != f'127.0.0.1:{port}' or request.headers.get('origin'):
                    return Response(status_code=403)
                if request.url.path != '/mcp':
                    return Response(status_code=404)
                if request.method != 'POST':
                    return Response(status_code=405)
                return await call_next(request)
            server = uvicorn.Server(uvicorn.Config(mcp_app, host='127.0.0.1', port=port, access_log=False))
            server.capture_signals = nullcontext
            task = asyncio.create_task(server.serve())
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError('Mahjong MCP listener failed')
                await asyncio.sleep(.02)
        for room in room_manager.get_rooms():
            if room.status == 'playing' and room.game_state:
                fn = _handle_claim_window if room.game_state.phase == 'claiming' else _run_ai_turn
                asyncio.create_task(fn(room.id))
        yield
    finally:
        jobs = set(_room_jobs.values())
        for job in jobs:
            job.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        if server:
            server.should_exit = True
            try:
                await asyncio.wait_for(task, 5)
            except asyncio.TimeoutError:
                task.cancel()

app = FastAPI(title="Mahjong Game", lifespan=lifespan)

@app.middleware('http')
async def private_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response

@app.get('/healthz')
async def health():
    return {'ok': True, 'game': 'mahjong'}

# ---------------------------------------------------------------------------
# REST API routes  →  /api/...
# ---------------------------------------------------------------------------
app.include_router(rest_router, prefix="/api")

# ---------------------------------------------------------------------------
# WebSocket routes  →  /ws/...
# ---------------------------------------------------------------------------
app.include_router(ws_router)

# ---------------------------------------------------------------------------
# Serve frontend static files  →  /
# ---------------------------------------------------------------------------
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend_dir):
    app.mount(
        "/",
        StaticFiles(directory=_frontend_dir, html=True),
        name="frontend",
    )
