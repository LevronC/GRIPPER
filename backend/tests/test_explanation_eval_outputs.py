"""Evaluation reruns must not overwrite historical evidence or reach a database."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("suffix", [".json", ".md"])
def test_existing_explanation_artifact_stops_before_database_setup(tmp_path, suffix):
    output = tmp_path / "historical"
    artifact = output.with_suffix(suffix)
    artifact.write_text("original evidence\n")
    backend = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, DATABASE_URL="invalid", MIGRATION_DATABASE_URL="invalid")
    result = subprocess.run(
        [sys.executable, str(backend / "scripts/eval_explanations.py"), "--out", str(output)],
        env=environment, cwd=backend, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert "Output exists" in result.stderr
    assert artifact.read_text() == "original evidence\n"
    assert not output.with_suffix(".md" if suffix == ".json" else ".json").exists()
