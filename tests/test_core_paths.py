"""出力先(output/)はカレントディレクトリに依存しない (tc-ops #578 独立レビュー指摘)。"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = "from core.paths import OUTPUT_DIR, PROJECT_ROOT; from core.cli_workflow import DEFAULT_HISTORY_DB_PATH; print(PROJECT_ROOT); print(OUTPUT_DIR); print(DEFAULT_HISTORY_DB_PATH)"


def test_output_dir_is_anchored_to_the_repository_not_the_cwd(tmp_path):
    import os

    env = {k: v for k, v in os.environ.items() if k != "TC_OUTPUT_DIR"}
    code = "import sys; sys.path.insert(0, %r);" % str(ROOT) + CODE
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    root, output, db = out.stdout.split("\n")[:3]
    assert Path(root) == ROOT
    assert Path(output) == ROOT / "output"
    assert Path(db) == ROOT / "output" / "history.db"


def test_output_dir_can_be_overridden_by_environment(tmp_path):
    import os

    env = dict(os.environ, TC_OUTPUT_DIR=str(tmp_path / "custom"))
    code = "import sys; sys.path.insert(0, %r);" % str(ROOT) + CODE
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    _, output, db = out.stdout.split("\n")[:3]
    assert Path(output) == tmp_path / "custom"
    assert Path(db) == tmp_path / "custom" / "history.db"
