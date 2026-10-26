"""Install a wheel to a temporary target; load its package/resources, not source."""
import pathlib
import subprocess
import sys
import tempfile

wheel = pathlib.Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix="face-agent-wheel-") as folder:
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps",
                    "--target", folder, str(wheel)], check=True)
    program = """
import pathlib, sys
sys.path.insert(0, sys.argv[1])
import easyaiot_face_agent
from easyaiot_face_agent import AgentRuntime
from easyaiot_face_agent.config import AgentConfig
from easyaiot_face_agent.skills import SkillRegistry
assert pathlib.Path(easyaiot_face_agent.__file__).is_relative_to(sys.argv[1])
assert len(SkillRegistry().list()) == 5
with AgentRuntime(AgentConfig()) as runtime:
    result = runtime.chat(message="overview")
    assert result["status"] == "completed"
    assert result["analysis_report"]["metrics"]["get_face_overview"]["face_records"] == 51
print("wheel installation and packaged skills/fixtures: PASS")
"""
    subprocess.run([sys.executable, "-I", "-c", program, folder], cwd=folder, check=True)
