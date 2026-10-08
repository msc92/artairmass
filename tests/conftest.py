import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validation"))
FIXTURES = ROOT / "validation" / "fixtures"


@pytest.fixture(scope="session")
def jsk_cases():
    cases = json.loads((FIXTURES / "cases.json").read_text())
    ref = {r["id"]: r for r in json.loads((FIXTURES / "jskycalc_reference.json").read_text())}
    return cases, ref
