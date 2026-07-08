# 新しいCLIローダーの使用方法

## 概要
従来のexec.shに代わる、モダンでかっこいいPythonベースのCLIローダーを実装しました。

## 実行方法

### 基本コマンド
```bash
# フルコマンド
./transcribe [URL/ファイルパス]

# ショートカット
./tc [URL/ファイルパス]

# Pythonスクリプト直接実行 (uv 経由で起動)
./transcribe.py [URL/ファイルパス]
```

### インタラクティブモード
引数なしで実行すると、対話的に設定を選択できます：
```bash
./tc
```

## 主な特徴

### シンプルで高速な処理
- 設定ファイルから自動でURL読み込み
- 確認なしで即座に処理開始
- デバイス自動検出（CUDA/CPU）

### 自動入力検出
- YouTube URL自動認識
- Google Drive URL自動認識  
- ローカルファイル自動認識

### Google Drive連携
- 元ファイルと同じフォルダにアップロード
- 完全なURLを表示（省略なし）
- 既存の認証システムを活用

## コマンドライン引数

```bash
./tc [入力ソース] [オプション]

オプション:
  --profile, -p     プロファイル番号を直接指定
  --language, -l    言語 (ja/en)
  --diarization, -d 話者分離を有効化
  --help           ヘルプ表示
```

## 使用例

### YouTube動画の文字起こし
```bash
./tc "https://youtube.com/watch?v=abc123"
```

### ローカルファイルの処理
```bash
./tc /path/to/audio.wav --language en --diarization
```

### プロファイル指定
```bash
./tc "youtube_url" --profile 2
```

## 従来のexec.shとの違い

| 項目 | exec.sh | 新CLI |
|------|---------|-------|
| UI | 複雑な出力 | シンプルなテキスト |
| 確認 | 多数の確認メッセージ | 確認なしで自動実行 |
| 設定 | 手動設定が必要 | 設定ファイル自動読み込み |
| アップロード先 | 新フォルダ作成 | 元ファイルと同じフォルダ |
| 実行方式 | Bash + Python | Pure Python |

## 互換性
- exec.shは引き続き利用可能
- 同じ機能を提供（YouTube、Google Drive、話者分離等）
- 設定ファイル（config.yaml）は共通

## 今後の拡張予定
- クリップボードからURL自動取得
- 複数ファイル一括処理
- 処理履歴表示
- 設定プロファイルの保存・読み込み