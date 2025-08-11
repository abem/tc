# tc CLI使用方法ガイド 🚀

## 概要
従来のexec.shに代わる、プロダクション品質のモダンCLIシステムです。

## 🎆 プロダクション特徴

- **uv環境対応**: pip比較10倍高速インストール
- **設定自動読み込み**: config.yamlからURL自動取得
- **Google Drive完全自動化**: 同一フォルダ自動アップロード
- **警告抑制**: クリーンなログ出力
- **OOM自動対処**: GPUメモリ不足時のCPU自動切り替え

## 実行方法

### 基本コマンド（プロダクション推奨）
```bash
# 最もシンプルな実行（config.yamlからURL自動読み込み）
./tc

# YouTube URL直接指定
./tc "https://youtube.com/watch?v=abc123"

# ローカルファイル処理
./tc audio.wav

# Google Drive URL直接処理
./tc "https://drive.google.com/file/d/1abc123def456/view"
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

## プロダクション適用状況

### ✅ 完全動作確認済み
- **YouTube動画処理**: 音声抽出から転写まで完全自動
- **Google Drive連携**: ダウンロード〜アップロードまで完全自動
- **話者分離機能**: pyannote.audio v3.3.2で高精度分離
- **多言語対応**: 日本語/英語モデル自動選択

### 互換性情報
- **exec.sh**: 引き続き利用可能（非推奨）
- **設定ファイル**: config.yamlを共用可能
- **認証情報**: credentials.json/token.pickleを共用

### ロードマップ（既に実現済み）
- ✅ 設定ファイル自動読み込み
- ✅ 同一フォルダ自動アップロード
- ✅ クリーンログ出力
- ✅ OOM自動対処
- ✅ uv環境対応