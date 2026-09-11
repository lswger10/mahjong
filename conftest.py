"""All tests use disposable storage, never the application's data directory."""
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent / 'backend'))
_storage = tempfile.TemporaryDirectory(prefix='mahjong-pytest-')
os.environ['MAHJONG_DATA_DIR'] = _storage.name
os.environ.pop('MAHJONG_MCP_PORT', None)


def pytest_sessionfinish(session, exitstatus):
    _storage.cleanup()
