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
```
