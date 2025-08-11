#!/usr/bin/env python3
"""
HuggingFace Tokenの設定ガイド
"""
import os
from pathlib import Path

def check_huggingface_token():
    """HuggingFace Tokenの設定状況を確認"""
    print("🔍 HuggingFace Token 設定チェック")
    print("=" * 50)
    
    # 環境変数チェック
    token_env = os.environ.get("HUGGINGFACE_TOKEN")
    if token_env:
        print(f"✅ 環境変数 HUGGINGFACE_TOKEN: 設定済み (長さ: {len(token_env)})")
        return True
    else:
        print("❌ 環境変数 HUGGINGFACE_TOKEN: 未設定")
    
    # HuggingFace CLIログインチェック
    hf_home = os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")
    token_file = Path(hf_home) / "token"
    
    if token_file.exists():
        try:
            with open(token_file, 'r') as f:
                token_content = f.read().strip()
            if token_content:
                print(f"✅ HuggingFace CLIトークン: 設定済み (長さ: {len(token_content)})")
                return True
        except Exception as e:
            print(f"❌ HuggingFace CLIトークン読み込みエラー: {e}")
    
    print("❌ HuggingFace CLIトークン: 未設定")
    return False

def setup_instructions():
    """セットアップ手順を表示"""
    print("\\n🛠️ HuggingFace Token セットアップ手順")
    print("=" * 50)
    
    print("1️⃣ HuggingFace アカウント作成・ログイン")
    print("   https://huggingface.co/")
    
    print("\\n2️⃣ アクセストークン作成")
    print("   https://huggingface.co/settings/tokens")
    print("   - [New token] をクリック")
    print("   - 名前: transcribe_audio")
    print("   - Type: Read")
    
    print("\\n3️⃣ トークン設定（以下のいずれか）")
    print("\\n   方法A: 環境変数設定")
    print("   export HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print("   echo 'export HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' >> ~/.bashrc")
    
    print("\\n   方法B: HuggingFace CLI使用")
    print("   pip install huggingface_hub")
    print("   huggingface-cli login")
    
    print("\\n4️⃣ 設定確認")
    print("   python3 setup_huggingface.py")

def test_pyannote_model():
    """pyannote.audioモデルアクセステスト"""
    print("\\n🧪 pyannote.audio モデルアクセステスト")
    print("=" * 50)
    
    try:
        from pyannote.audio import Pipeline
        
        # HuggingFace Tokenを取得
        token = os.environ.get("HUGGINGFACE_TOKEN")
        if not token:
            # HuggingFace CLIトークンを試行
            hf_home = os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")
            token_file = Path(hf_home) / "token"
            if token_file.exists():
                with open(token_file, 'r') as f:
                    token = f.read().strip()
        
        if not token:
            print("❌ HuggingFace Tokenが見つかりません")
            return False
        
        print("🔄 pyannote/speaker-diarization-3.1 モデルアクセス中...")
        
        # モデルロードテスト（実際にダウンロードはしない）
        try:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=token
            )
            print("✅ モデルアクセス成功！")
            return True
        except Exception as e:
            print(f"❌ モデルアクセス失敗: {e}")
            if "401" in str(e) or "unauthorized" in str(e).lower():
                print("💡 トークンが無効またはアクセス権限がありません")
            elif "403" in str(e) or "forbidden" in str(e).lower():
                print("💡 モデルへのアクセス許可が必要です")
                print("   https://huggingface.co/pyannote/speaker-diarization-3.1")
                print("   でモデルの利用許可を申請してください")
            return False
            
    except ImportError:
        print("❌ pyannote.audio がインストールされていません")
        return False
    except Exception as e:
        print(f"❌ テスト中にエラー: {e}")
        return False

def main():
    print("🚀 HuggingFace Token セットアップ確認")
    print("=" * 60)
    
    # Token設定チェック
    token_ok = check_huggingface_token()
    
    if token_ok:
        # モデルアクセステスト
        model_ok = test_pyannote_model()
        
        if model_ok:
            print("\\n🎉 すべて正常に設定されています！")
            print("話者分離機能が使用可能です。")
            return True
        else:
            print("\\n⚠️ Tokenは設定されていますが、モデルアクセスに問題があります")
    
    # セットアップ手順表示
    setup_instructions()
    
    print("\\n" + "=" * 60)
    print("💡 設定完了後、以下で話者分離機能をテストできます:")
    print("   python3 test_with_local_file.py")
    
    return False

if __name__ == "__main__":
    main()