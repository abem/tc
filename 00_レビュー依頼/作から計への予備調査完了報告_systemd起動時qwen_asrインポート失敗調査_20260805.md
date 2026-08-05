# 作から計への予備調査完了報告 兼 調査計画: systemd起動直後のqwen_asrインポート失敗の原因調査（tc-ops #441）

**報告日**: 2026-08-05
**報告者**: 作成ロール（作／saku）
**対象**: 計から作への作業指示書_systemd起動時qwen_asrインポート失敗調査_20260805.md の4-1節

---

## 1. 事前調査で確認した事実（実験着手前、コード・環境の静的確認）

### 1-1. サービスファイルの実機確認

```
[Service]
Type=simple
WorkingDirectory=/home/abem/Projects/tc
ExecStart=/home/abem/.local/bin/uv run streamlit run webui.py --server.headless true --server.port 8501
Restart=on-failure
RestartSec=5
```
`WorkingDirectory`は正しく設定済み。`ExecStart`は絶対パスで`uv`を呼び、手動起動と全く同一の
コマンド（`uv run streamlit run webui.py ...`）。cgroup系のリソース制限は明示的に設定されていない。

### 1-2. リソース制限の実測（`systemctl --user show tc-webui.service`）

```
CPUQuotaPerSecUSec=infinity
MemoryMax=infinity
StartupMemoryMax=infinity
LimitNOFILE=1048576
LimitNOFILESoft=1024
```
CPU・メモリとも実質無制限。ファイルディスクリプタのソフト上限（1024）はsystemd既定値であり、
`torch`等の初回ロードで大量のfd消費が起きた場合の可能性はゼロではないが、"初回のみ失敗し
2回目以降は必ず成功する"という改善方向の挙動とは相性が悪く（fd枯渇なら継続的悪化が自然）、
優先度は低いと判断する。

### 1-3. 環境変数の比較（`systemctl --user show-environment` vs 手動シェル`env`）

**重要な差異**: `PATH`が大きく異なる。
- systemd --user: `PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin:/snap/bin`
  （`~/.local/bin`・`.venv/bin`を含まない、systemdユーザーマネージャの既定PATH）
- 手動シェル: `~/.local/bin`（`uv`本体の場所）を含む、WSL統合による長大なPATH

**ロケールは同一**（`LANG=C.UTF-8`、両者とも）。当初は「systemd特有のロケール差」を疑ったが、
実測の結果この観点は該当しないことを確認した（棄却）。

`ExecStart`が`uv`を絶対パスで呼んでいるため`uv`自体の起動には影響しないはずだが、**`uv run`が
内部でプロジェクト検出・`.venv`解決を行う際にPATHを参照する経路があるかは未検証**であり、
調査対象とする。

### 1-4. `qwen_asr`パッケージのimport構造

`qwen_asr/__init__.py` → `qwen_asr/inference/qwen3_asr.py`が`torch`・`transformers`
（`AutoConfig`/`AutoModel`/`AutoProcessor`）を実importしている。重量級ライブラリの初回ロードを
伴うネストしたimportチェーンであり、初回ロード時のみ時間・リソースを要する処理が挟まる構造。

## 2. 調査方針（4-1節、実験計画）

**制約の遵守**: 本番`tc-webui.service`は一切停止・再起動しない。検証はすべて
（a）`systemd-run --user`による一時的な単発実行（別ユニット名・別ポート）、
（b）手動シェルからの起動（別ポート）、のいずれかで行う。

### 2-1. 診断ログの一時追加（最優先、直接証拠の取得）

`Qwen3ASREngine._load_model()`のimport直前・直後（成功時・失敗時とも）に、以下を一時的に
ログ出力する診断コードを追加する（**調査専用、コミット対象に含めるかは計の判断を仰ぐ**）:
- `sys.path`の全内容
- `threading.current_thread().name`・プロセスPID
- 失敗時は`traceback.format_exc()`の全文

これにより、「systemd経由・初回のみ」の失敗が実際に発生した瞬間の`sys.path`の状態を直接確認する
（"モジュールが見つからない"エラーは通常`sys.path`の不備を示すため、最も筋が良い検証経路）。

### 2-2. 対照実験: systemd経由 vs 手動起動（采候補1に対応）

同一コマンド・同一コードを、以下の2条件で比較する:
- (a) `systemd-run --user --unit=tc-webui-investigation --collect ... uv run streamlit run
  webui.py --server.headless true --server.port 8502`（本番とは別ユニット名・別ポート）
- (b) 手動シェルから`uv run streamlit run webui.py --server.headless true --server.port 8503`

各条件で起動直後に1回目の文字起こしジョブ（ローカルの短い音声、ネットワーク非依存）を投入し、
再現有無を記録する。「systemd経由か否か」のみを変数化した対照実験とする。

### 2-3. 環境変数の全差異の記録（采候補2に対応、1-3節の実測を踏まえた深掘り）

`systemd-run --user env`の出力と手動シェルの`env`を突き合わせ、PATH以外の差異
（`XDG_*`系、`DBUS_SESSION_BUS_ADDRESS`の有無等）も網羅的に記録する。特に`uv run`が内部で
参照する可能性のある変数（`UV_*`系）の有無を重点確認する。

### 2-4. Streamlitのファイル監視との競合確認（采候補3に対応）

診断ログ（2-1節）のタイムスタンプと、Streamlitサーバーログ上のfile watcher関連の出力
（`docs/system-docs/webui_architecture.md`記載のWSL2ポーリング型監視）を突き合わせ、
タイミング的な相関があるか確認する。有力度は他候補より低いと考えるが、指示書の采候補に
含まれるため調査対象とする。

### 2-5. saku独自の追加観点

- **`uv run`内部のPATH依存経路**（1-3節の実測を踏まえた追加観点）: `uv run`実行時に
  `--verbose`相当のログを取得し、`.venv`検出・Python解決の過程でPATH環境変数がどう参照
  されるかを確認する。
- **importロック・スレッド競合**: 初回のバックグラウンドスレッドからのimportと、Streamlit
  自体の起動シーケンス（メインスクリプト実行・WebSocketハンドラ初期化等）が時間的に近接して
  いないか、診断ログのタイムスタンプから確認する。

## 3. 完了条件の遵守方針

指示書3節（推測のみでの「確定」は不可）に従い、上記実験の結果（成功/失敗の実測記録）に基づいて
原因を特定・絞り込む。完全に特定できない場合も、棄却した仮説とその根拠、残る候補を完了報告に
明記する。

## 4. 質問事項

1. 2-1節の診断ログについて、調査完了後は削除する想定でよいか、それとも今後の運用改善（同種の
   問題の早期検知）のため一部を恒久的な統一ロガー出力として残す価値があるか、原因確定後に
   改めて計のご判断を仰ぎたい（本予備調査の時点では一時的な調査用途と位置づける）。
2. 上記以外は作業指示書の要件・スコープで判断可能なため、承認をいただければ調査に着手します。

---

**セルフチェック**: 4-1節の采提示3候補（systemd-run再現実験・環境変数差異・ファイル監視競合）
すべてに具体的な検証方法を設計済み、saku独自の追加観点（PATH依存経路・importロック競合）も
提案済み。本番サービスを停止しない制約を遵守する実験設計（別ユニット名・別ポート）。作業範囲
（5節、是正実装を含まない）内。Git操作は本報告書作成のみで実施していない。

**提出者**: 作ロール（saku）
