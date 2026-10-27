"""出力先などの、実行時のカレントディレクトリに依存しないパス。

`output/`(文字起こし結果・履歴DB・アップロード・ダウンロードの置き場)は、`tc`をどのディレクトリから
起動しても、また本番(systemd・WorkingDirectory=リポジトリ)でも、リポジトリ直下の同じ場所を指す。
別の場所を使うときは環境変数`TC_OUTPUT_DIR`で指定する(テストが実リポジトリの`output/`を汚さないためにも使う)。
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(os.environ.get("TC_OUTPUT_DIR") or PROJECT_ROOT / "output")
