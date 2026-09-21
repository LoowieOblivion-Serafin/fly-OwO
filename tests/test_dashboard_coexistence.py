"""The two game adapters must serve dashboards matching their own protocols."""
import json
from pathlib import Path
from urllib.request import urlopen

from fly64 import main as mario
from flysonic import main as sonic

ROOT = Path(__file__).resolve().parents[1]


def fetch(server, path):
    with urlopen(f"http://127.0.0.1:{server.server_port}{path}", timeout=5) as response:
        return response.read()


def test_dashboard_servers_keep_documents_metadata_and_assets_separate():
    sonic_server = sonic.start_http(ROOT, sonic.FlyModel(demo=True), 0, 9876)
    try:
        mario_server = mario.start_http(ROOT, mario.FlyModel(demo=True), 0, 9878)
        try:
            sonic_html = fetch(sonic_server, "/")
            mario_html = fetch(mario_server, "/")
            assert sonic_html == (ROOT / "web/sonic/index.html").read_bytes()
            assert mario_html == (ROOT / "web/index.html").read_bytes()
            assert b"Fly Sonic Neural Observatory" in sonic_html
            assert b"'FLYS'" in sonic_html
            assert b'dashboard.js' in mario_html
            assert fetch(mario_server, "/dashboard.js") == (ROOT / "web/dashboard.js").read_bytes()
            assert fetch(mario_server, "/dashboard.css") == (ROOT / "web/dashboard.css").read_bytes()
            sonic_meta = json.loads(fetch(sonic_server, "/metadata.json"))
            mario_meta = json.loads(fetch(mario_server, "/metadata.json"))
            assert sonic_meta["ws"] == 9876
            assert mario_meta["ws"] == 9878
            assert "retina" not in sonic_meta
            assert "retina" in mario_meta
            # Starting Fly64 after Sonic must not replace Sonic's document.
            assert fetch(sonic_server, "/index.html") == sonic_html
        finally:
            mario_server.shutdown()
            mario_server.server_close()
    finally:
        sonic_server.shutdown()
        sonic_server.server_close()
