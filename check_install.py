"""Validate local source files; never open .env, secrets or uploaded research files."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import sys


def main() -> int:
    root = Path(__file__).resolve().parent
    print("Project folder:", root)
    print("Python:", sys.executable)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        print("FAIL: manifest.json is missing. Extract the complete ZIP into a NEW folder.")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print("Package build:", manifest.get("version"))
    failed=[]
    for name, expected in manifest.get("files", {}).items():
        if not name.endswith('.py') or name.startswith('tests/'):
            continue
        path=root/name
        actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        if actual != expected:
            failed.append(name)
    for name in ('app.py','p0_search_ui.py','catalog_identity.py','nanet_metadata.py'):
        path=root/name
        short=hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path.exists() else 'MISSING'
        print(name, short)
    if failed:
        print("FAIL: source files differ from this package:", ', '.join(failed))
        print("Do not mix versions. Back up your work and extract the FULL ZIP into a new folder.")
        return 1
    print("PASS: application source files match this package.")
    try:
        print("Streamlit:", importlib.metadata.version("streamlit"))
    except importlib.metadata.PackageNotFoundError:
        print("Streamlit is not installed in this Python. Run: python -m pip install -r requirements.txt")
    print('Run: "' + sys.executable + '" -m streamlit run "' + str(root/'app.py') + '"')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
