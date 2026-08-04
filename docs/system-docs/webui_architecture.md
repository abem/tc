# WebUI 内部サーバー構成

**対象**: `webui.py`（Streamlitプロトタイプ、Phase2）
**作成日**: 2026-08-05
**作成者**: 作成ロール（作/saku）
**確認方法**: 全項目、実機（本リポジトリの `.venv`、Streamlit 1.60.0、WSL2環境）で実際に
起動・ログ採取・`ss`によるポート確認を行った実測値に基づく。憶測・未確認の転記は含まない。

---

## 1. サーバースタック

`webui.py` は Streamlit を通じて以下のスタックで動作する（実機確認: `uv pip show streamlit`）。

```
$ uv pip show streamlit
Name: streamlit
Version: 1.60.0
Requires: altair, anyio, blinker, click, gitpython, httptools, itsdangerous, numpy,
          packaging, pandas, pillow, protobuf, pyarrow, pydeck, python-multipart,
          requests, starlette, tenacity, toml, typing-extensions, uvicorn, watchdog,
          websockets
```

- **ASGIアプリケーション**: [Starlette](https://www.starlette.io/)。本バージョンのStreamlitパッケージ内に
  `streamlit/web/server/starlette/`(`starlette_app.py`・`starlette_server.py`・`starlette_websocket.py`等)
  が実在することを実機確認済み。
- **ASGIサーバー**: [uvicorn](https://www.uvicorn.org/)。`starlette_server.py` 内で
  `uvicorn.Config` を組み立て `uvicorn.Server(uvicorn_config)` を生成・`.run()` する実装であることを
  ソース実測で確認済み（`grep -n "uvicorn\." streamlit/web/server/starlette/starlette_server.py` で
  複数箇所ヒット）。
- **Tornadoは不使用**: 旧バージョンのStreamlitはTornadoベースのサーバー実装だったが、
  **本バージョン(1.60.0)ではTornadoへの依存が無い**ことを実機確認済み(`uv pip show tornado` →
  `Package(s) not found`、パッケージ自体が未インストール)。Streamlitの過去バージョン情報を参照する際は
  Tornado前提の記述と混同しないよう注意すること。

## 2. 起動コマンドと起動ログ

**起動コマンド**（本番相当。ブラウザを自動で開く既定動作を含む）:

```bash
uv run streamlit run webui.py
```

**ヘッドレス起動**（自動テスト・サーバー環境向け。ブラウザ自動起動を抑制。`--server.headless` の
既定値はLinuxでSSH接続時など一部条件でtrueになる場合があるが、明示指定が確実）:

```bash
uv run streamlit run webui.py --server.headless true --server.port <PORT>
```

**起動ログの代表例**（実機実行、ポート8503で実測採取）:

```
Collecting usage statistics. To deactivate, set browser.gatherUsageStats to false.

2026-08-05 00:46:31.199 Uvicorn server started on :::8503

  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8503
  Network URL: http://172.28.0.5:8503
  External URL: http://203.0.113.1:8503

  Detected WSL. Using poll-based file watching for better compatibility. To force watchdog, set server.fileWatcherType = "watchdog".
```

- 1行目「Collecting usage statistics」は Streamlit の匿名利用統計収集に関する案内。
  `~/.streamlit/config.toml` または起動フラグで `browser.gatherUsageStats = false` を設定すると
  収集を無効化できる（本プロジェクトでは未設定＝既定の収集有効状態）。
- 「Uvicorn server started on :::8503」がASGIサーバー(uvicorn)の起動完了ログ。

## 3. バインド・公開URLとセキュリティ注意

起動ログに表示される3種のURLの意味:

| URL種別 | 意味 |
|---|---|
| Local URL | サーバーを実行しているマシン自身からのアクセス用(`localhost`)。 |
| Network URL | 同一LAN/プライベートネットワーク上の他端末からアクセスする際のURL(実機確認時はWSL2の内部ネットワークアドレスが表示された。例: `172.28.0.5` は例示用のプレースホルダで、実際の値は環境ごとに異なる)。 |
| External URL | インターネット経由でグローバルにアクセス可能な場合のURL(実機確認時は開発機の実際のグローバルIPが表示された。例: `203.0.113.1` はRFC 5737のドキュメント用予約アドレスによる例示であり、実測値そのものではない)。 |

**バインドアドレスの実機確認**: `--server.address` を指定しない場合(既定は未設定)、サーバーは
**全インターフェースにバインドされる**。起動中に `ss -tlnp` で実測確認した結果:

```
LISTEN 0      2048                *:8503             *:*    users:(("streamlit",...))
```

`*:8503`(IPv6表記では `:::8503`)は全アドレスでの待受を意味する。`uv run streamlit run --help`
の `--server.address` 説明文でも「Default: (unset)」であることが明記されており、既定動作として
特定アドレスへの制限は行われない。

**🚨 セキュリティ上の注意事項(必須記載事項)**:

- `webui.py` は**認証機構を一切実装していない**(本ソース内に認証・アクセス制御コードは存在しない)。
- 上記のとおり既定で全インターフェースにバインドされるため、ファイアウォール等で外部到達性が
  確保された環境(クラウドVM・ポート開放されたネットワーク等)で起動すると、
  **認証なしで誰でも音声のアップロード・文字起こし実行・変換履歴(結果テキスト含む)の閲覧が
  可能な状態になる**。
- ローカル開発・検証以外の用途で起動する場合は、以下のいずれかの対策を必ず講じること:
  - `--server.address 127.0.0.1` を指定しローカルホストのみへバインドを限定する。
  - リバースプロキシ(nginx等)でBasic認証・IP制限を前段に設ける。
  - VPN等、信頼できるネットワーク経由でのみアクセス可能にする。
- 本プロトタイプ(Phase2)の時点では認証機能は設計・実装のいずれにも含まれていない
  (`00_レビュー依頼/作から計への設計書_WebUIフレームワーク選定とプロトタイプ方針_20260806.md`にも
  認証に関する記載なし)。認証機能が必要な場合はPhase3以降の検討課題として別途起案すること。

## 4. WSL2固有の挙動

本プロジェクトの開発環境(WSL2)で起動すると、起動ログに以下が実機確認された:

```
Detected WSL. Using poll-based file watching for better compatibility. To force watchdog, set server.fileWatcherType = "watchdog".
```

- Streamlitは既定でファイル変更監視に`watchdog`パッケージ(inotify等のOSネイティブ機構を利用)を
  使うが、**WSL2環境を検知するとポーリング方式(定期的にファイルの変更有無を確認する方式)へ
  自動フォールバックする**。
- これはWSL2のファイルシステム(特にWindows側ドライブをマウントしている場合)でinotifyイベントが
  正しく配送されないケースがあるための互換性対応。
- ポーリング方式は監視間隔ぶんの検知遅延が生じるが、`webui.py`は開発中のホットリロード
  (`server.runOnSave`)を前提とした設計ではないため、通常利用への実害はない。
- 明示的に `watchdog` 方式を強制したい場合は `--server.fileWatcherType watchdog` を指定できる
  (ログの案内どおり)。WSL2特有の制約下では非推奨。

## 5. 通信方式

ブラウザとサーバー間は **WebSocket** で状態同期する。Streamlitパッケージ内に
`streamlit/web/server/starlette/starlette_websocket.py`(冒頭コメント:
`"""WebSocket handling for the Starlette server."""`)が実在することを実機確認済み。

**実行モデル**: Streamlitはユーザー操作(ウィジェット操作等)のたびに**スクリプト全体を再実行**し、
差分をWebSocket経由でブラウザへ配信する(仮想DOM的な差分配信)。これが `webui.py` の
`st.session_state` を多用した状態管理(`_start_job()` でのジョブ状態保存等)の設計上の理由である。

**`@st.fragment(run_every="1s")` による部分再実行**: `webui.py` の `_render_progress_and_result()`
はフラグメント化されており、画面全体ではなく該当部分のみを1秒間隔で自動再実行してポーリング的に
進捗を再描画する。この設計の詳細な採用理由は既存設計書で扱い済み:

> 5節「5分チャンク分割処理の非同期・安定動作方式」…UI側の自動更新には `st.fragment(run_every="1s")`
> （Streamlit 1.37+の部分再実行機能）を採用し、進捗表示部分のみを1秒間隔で再描画する。これにより
> 画面全体の再実行（Streamlitのデフォルト動作）によるチラつき・状態喪失を避ける。
>
> — `00_レビュー依頼/作から計への設計書_WebUIフレームワーク選定とプロトタイプ方針_20260806.md` §5

## 6. 起動/停止・ログ確認の正式な手順

### 起動(フォアグラウンド、開発時の通常利用)

```bash
uv run streamlit run webui.py
```

ブラウザが自動で開く(WSL2からWindows側ブラウザが開かない場合は、起動ログのLocal URLを
手動でブラウザに貼り付ける)。停止は起動したターミナルで `Ctrl+C`。

### 起動(バックグラウンド、動作確認・自動テスト用途)

```bash
nohup uv run streamlit run webui.py --server.headless true --server.port 8501 \
  > /tmp/webui.log 2>&1 &
echo $!   # PIDを控える
```

Streamlit自体は専用のログファイルを持たない(標準出力/標準エラーにログを出す実装のため、
上記のようにリダイレクトして初めてファイルに残る)。

### 起動確認(ヘルスチェック)

```bash
curl -sf http://localhost:8501/_stcore/health
# 正常時: "ok" を返す
```

### ログ確認

```bash
tail -f /tmp/webui.log
```

起動ログにLocal/Network/External URL・WSL2ポーリング注記等(2〜4節参照)が出力される。

### 停止

```bash
# 起動時に控えたPIDで停止
kill <PID>

# PIDを控えていない場合、プロセス名で検索して停止
pkill -f "streamlit run webui.py"
```

### 稼働中プロセス・ポートの確認

```bash
ss -tlnp | grep <PORT>
# または
ps aux | grep "streamlit run webui.py"
```

## 7. systemdによる常駐化・自動起動

6節の起動/停止手順は開発時の手動運用(フォアグラウンド/バックグラウンド起動)を前提としている。
**systemdユーザーサービスによる常駐化は、これとは別の本番相当の運用モード**であり、
ログイン有無に関わらずマシン起動時に自動でWebUIを起動し、プロセスが落ちた場合も自動再起動する。

> ⚠️ 以下は**本開発機(WSL2、ユーザー`abem`)で実際に構築・実機確認した環境固有の設定例**である。
> 他ホストで同様の常駐化を構築する場合の**再現手順**として記載する。ユーザー名・作業ディレクトリ
> パス等は環境ごとに異なるため、自環境の値に置き換えて適用すること(§3節のIPアドレス
> プレースホルダ化と同じ配慮)。

### サービスファイル

`~/.config/systemd/user/tc-webui.service`(**このファイル自体はリポジトリ管理対象外**。
ホームディレクトリ配下`~/.config/`にあり、Gitの追跡範囲外)。実機で`cat`して再確認した内容:

```ini
[Unit]
Description=tc WebUI (Streamlit) - Transcribe Audio
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/<ユーザー名>/Projects/tc
ExecStart=/home/<ユーザー名>/.local/bin/uv run streamlit run webui.py --server.headless true --server.port 8501
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

(`WorkingDirectory`・`ExecStart`内の`<ユーザー名>`部分は環境固有値のプレースホルダ。
本開発機での実際の値は`abem`)。

### 有効化コマンド

```bash
systemctl --user daemon-reload && systemctl --user enable --now tc-webui.service
```

`daemon-reload`でユニットファイルの変更をsystemdに反映し、`enable --now`で自動起動を有効化した上で
即座に起動する(実機実行済み、既に有効化・稼働中の状態に対しては冪等に成功することを確認)。

### ログイン無しでの自動起動(linger)

systemdユーザーサービスは既定では、そのユーザーが一度もログインしていない状態(SSH未接続等)では
起動しない。`loginctl enable-linger <ユーザー名>` を実行すると、ログイン有無に関わらずユーザーの
systemdインスタンスがマシン起動時から動き続ける(本開発機で実機確認: `loginctl show-user abem`の
出力に`Linger=yes`を確認済み)。

**これはユーザーアカウント単位のシステム設定であり、リポジトリのコード変更ではない**
(`~/.config/systemd/`同様、Git管理対象外)。

```bash
loginctl enable-linger <ユーザー名>
```

### 運用コマンド

以下は実機実行して動作確認済み(status・daemon-reload・enable --nowは実際に実行。**restart・stopは
現在稼働中のサービスが実データ(実際のユーザー利用による文字起こしジョブ)を処理中だったため、
処理を中断させないよう本文書作成時には意図的に実行しなかった**。コマンド自体はsystemdの標準的な
サブコマンドであり、`systemctl --user status`と対称の構文で動作することは`systemctl --help`の
仕様から明らか。実行が必要な場合は稼働中ジョブの有無を確認の上、以下のとおり実行すること):

```bash
# 状態確認(実機実行済み。稼働中プロセスのPID・メモリ使用量・直近ログが表示される)
systemctl --user status tc-webui.service

# 再起動(設定変更後の反映等。実行前に稼働中ジョブが無いことを確認すること)
systemctl --user restart tc-webui.service

# 停止(常駐化を一時的に止める。自動起動の無効化はenableの取り消しが別途必要)
systemctl --user stop tc-webui.service

# ログ確認(リアルタイム追尾)
journalctl --user -u tc-webui.service -f

# ログ確認(直近N件、追尾しない。実機実行済み)
journalctl --user -u tc-webui.service -n 20 --no-pager
```

`journalctl`経由のログは、6節で説明した「Streamlit自体は専用のログファイルを持たない」制約を
systemdが代替する形になる(標準出力/標準エラーがsystemd-journaldへ自動的に取り込まれるため、
6節のような`nohup ... > file 2>&1`によるリダイレクトが不要)。

---

## 【参考】検査コマンド一覧(本文書作成時に実機実行したコマンド)

```bash
uv pip show streamlit
uv pip show tornado
find "$(uv run python3 -c 'import streamlit, os; print(os.path.dirname(streamlit.__file__))')" \
  -iname "*starlette*" -o -iname "*uvicorn*"
grep -n "uvicorn\." <streamlit_install_dir>/web/server/starlette/starlette_server.py
uv run streamlit run --help
uv run streamlit run webui.py --server.headless true --server.port 8503 &
ss -tlnp | grep 8503
curl -sf http://localhost:8503/_stcore/health
grep -n "WebSocket" <streamlit_install_dir>/web/server/starlette/starlette_websocket.py

# 7節(systemd常駐化)分
systemctl --user status tc-webui.service
cat ~/.config/systemd/user/tc-webui.service
loginctl show-user <ユーザー名> | grep -i linger
systemctl --user daemon-reload
systemctl --user enable --now tc-webui.service
journalctl --user -u tc-webui.service -n 20 --no-pager
```
