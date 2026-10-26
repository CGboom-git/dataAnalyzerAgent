"""Start and stop the loopback CLI with synthetic config; never attach to an existing port."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with socket.socket() as probe:
    if probe.connect_ex(("127.0.0.1", 8765)) == 0:
        raise SystemExit("Port 8765 is occupied; existing process was not touched.")
env = dict(os.environ)
env.update(AGENT_MODEL_BASE_URL="", AGENT_MODEL_NAME="", FACE_ANALYTICS_BASE_URL="",
           AGENT_REQUIRE_TOOL_APPROVAL="false", AGENT_CHECKPOINT_DB="", AGENT_MEMORY_DB="")
log = tempfile.TemporaryFile(mode="w+b")
process = subprocess.Popen(
    [sys.executable, "-m", "easyaiot_face_agent"], cwd=root, env=env,
    stdout=log, stderr=subprocess.STDOUT,
)
try:
    ready = False
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("CLI exited before becoming ready")
        try:
            with opener.open("http://127.0.0.1:8765/v1/health", timeout=1) as response:
                assert json.load(response)["model"] == "offline-demo"
            ready = True
            break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
    if not ready:
        raise RuntimeError("CLI readiness timeout")
    request = urllib.request.Request(
        "http://127.0.0.1:8765/v1/chat",
        data=json.dumps({"message": "overview"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with opener.open(request, timeout=10) as response:
        body = json.load(response)
    assert body["status"] == "completed"
    assert body["analysis_report"]["metrics"]["get_face_overview"]["face_records"] == 51
    print("loopback CLI startup + health + chat: PASS")
finally:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    log.seek(0)
    if sys.exc_info()[0] is not None:
        print(log.read().decode(errors="replace")[-4000:], file=sys.stderr)
    log.close()
