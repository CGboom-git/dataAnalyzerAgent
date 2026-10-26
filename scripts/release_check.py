"""Small public-tree check. Pattern scanning is not proof of complete secret removal."""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parents[1]
excluded = {".git", ".venv", ".local", ".pytest_cache", "build", "dist",
            "artifacts", "__pycache__", "uploads"}
patterns = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "aws_key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "private_endpoint": re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
}
findings = []
count = 0
for folder, dirs, names in os.walk(root):
    dirs[:] = [d for d in dirs if d not in excluded and not d.endswith(".egg-info")]
    for name in names:
        path = pathlib.Path(folder) / name
        if path.suffix not in {".py", ".md", ".toml", ".yaml", ".yml", ".lock", ".example"}:
            continue
        count += 1
        content = path.read_text(encoding="utf-8")
        for kind, pattern in patterns.items():
            if pattern.search(content):
                findings.append({"file": str(path.relative_to(root)), "kind": kind})
fixtures = json.loads((root / "easyaiot_face_agent/data/events.json").read_text())["events"]
synthetic = all(row["person_ref"].startswith("demo-subject-")
                and row["camera_id"].startswith("demo-camera-") for row in fixtures)
resources = all((root / "easyaiot_face_agent/skills/prompts" / f"{name}.md").is_file()
                for name in ["face_overview", "face_activity", "person_trace",
                             "person_lookup", "face_analysis"])
rights_pending = ("not been confirmed" in (root / "LICENSE_STATUS.md").read_text()
                  or not (root / "LICENSE").exists())
result = {"source_files_checked": count, "pattern_findings": findings,
          "synthetic_fixture": synthetic, "skill_resources": resources,
          "readme_present": (root / "README.md").stat().st_size > 500,
          "publication_rights_pending": rights_pending}
print(json.dumps(result, ensure_ascii=False, indent=2))
failed = findings or not synthetic or not resources or not result["readme_present"]
sys.exit(1 if failed else 2 if "--for-publication" in sys.argv and rights_pending else 0)
