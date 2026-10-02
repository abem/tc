"""handlers/gdrive_auth.py(旧ルート config.py): 再認証の経路と import 時の副作用のテスト。

実際の Google Drive・ブラウザ認証には接続しない(認証クライアントと input を差し替える)。
実機での認証確認は別途ユーザーが行う(tc-ops #567 Task 5.5)。
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_import_does_not_change_process_environment():
    """import しただけでは OAUTHLIB_INSECURE_TRANSPORT を設定しない(以前は import 時に無条件で設定していた)。"""
    code = "import os; os.environ.pop('OAUTHLIB_INSECURE_TRANSPORT', None); import handlers.gdrive_auth; print(os.environ.get('OAUTHLIB_INSECURE_TRANSPORT'))"
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().splitlines()[-1] == "None"


def _reauth(tmp_path, monkeypatch, input_side_effect):
    import handlers.gdrive_auth as auth

    monkeypatch.delenv("OAUTHLIB_INSECURE_TRANSPORT", raising=False)
    flow = MagicMock()
    flow.authorization_url.return_value = ("https://auth.example/consent", "state")
    flow.credentials = MagicMock(name="creds")
    with patch.object(auth.InstalledAppFlow, "from_client_secrets_file", return_value=flow), \
         patch.object(auth, "build", return_value="SERVICE") as build, \
         patch("builtins.input", side_effect=input_side_effect):
        result = auth.get_drive_service(
            credentials_path=str(tmp_path / "client.json"), token_path=str(tmp_path / "token.pickle")
        )
    return result, flow, build


def test_reauth_flow_sets_insecure_transport_only_when_reauthenticating(tmp_path, monkeypatch):
    result, flow, build = _reauth(tmp_path, monkeypatch, ["http://localhost:8080/?code=abc"])

    import os

    assert result == "SERVICE"
    assert os.environ.get("OAUTHLIB_INSECURE_TRANSPORT") == "1"
    flow.fetch_token.assert_called_once_with(authorization_response="http://localhost:8080/?code=abc")
    monkeypatch.delenv("OAUTHLIB_INSECURE_TRANSPORT", raising=False)


def test_reauth_without_stdin_fails_instead_of_hanging(tmp_path, monkeypatch):
    """標準入力が無い環境(systemd 下の WebUI は /dev/null)では input() が EOFError になり、
    RuntimeError として失敗する(5.5-spike の確認結果。無期限には止まらない)。"""
    with pytest.raises(RuntimeError, match="認証に失敗"):
        _reauth(tmp_path, monkeypatch, EOFError())
    monkeypatch.delenv("OAUTHLIB_INSECURE_TRANSPORT", raising=False)


def test_gdrive_client_imports_auth_from_handlers():
    import handlers.gdrive as gdrive
    import handlers.gdrive_auth as auth

    assert gdrive.get_drive_service is auth.get_drive_service
