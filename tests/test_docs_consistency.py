"""文書と実装の整合を機械で検査する(tc-ops #592 Task D0.2)。

文書が古くなる(存在しないファイルを指す、削除したモジュールを案内する、無いオプションを書く)のを、
CI で検出する。パス・名前・オプションの存在だけを検査する。手順や挙動の説明が正しいかは、人間または
独立レビューの仕事(この検査は「grep 0 件」と同じで、記述の内容までは保証しない)。

対象は「現行文書」。次は検査しない:
- `00_レビュー依頼/`: 作業の依頼・報告の記録で、書いた時点の状態を残す(文書ではない)
- `docs/obsolete/`、`docs/historical-records/`: 履歴資料。現状と異なることを前提に置いている
- `Plans.md`: 計画の台帳。完了済みの計画に、削除したファイルの名前が残る
- `CHANGELOG.md`: パスの存在は検査しない(過去の変更の記録は、後に削除したファイルを指してよい)。
  リンク切れだけを検査する
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# 現行文書(リポジトリ直下の文書 + docs/ 配下。除外ディレクトリは上のとおり)
EXCLUDED_DIRS = ("docs/obsolete/", "docs/historical-records/")
ROOT_DOCS = [
    "README.md", "CLAUDE.md", "CONTRIBUTING.md", "DEVELOPMENT.md", "DEVELOPMENT_QUICKREF.md",
    "SECURITY.md", "CHANGELOG.md",
]
LINK_ONLY = {"CHANGELOG.md"}  # パスの存在は検査しない(上記)

# 文書に書いてよいが、リポジトリには無いパス(利用者が作る、または実行時に生成される)
ALLOWED_MISSING_PATHS = {
    "config/context_hints.txt",  # 利用者が作る認識ヒント(サンプルは config/context_hints.txt.sample)
}
# GitHub 上でだけ解決される相対リンク
ALLOWED_MISSING_LINKS = {"../../issues"}

# 削除済みモジュール(CLAUDE.md「削除済みモジュール」)。現行の案内として書いてはいけない
DELETED_NAMES = [
    "transcriber.py", "transcriber/", "logger.py", "gdrive_handler.py", "youtube_handler.py",
    "youtube_gdrive_handler.py", "patterns/", "exceptions.py",
]
# 削除・後継・廃止を説明する行では、削除済みの名前を書いてよい
HISTORY_WORDS = ("削除済み", "削除され", "後継", "廃止", "旧", "かつて", "以前", "移行", "置き換え", "前提に書かれて")

PATH_RE = re.compile(
    r"`((?:core|handlers|scripts|tests|docs|config)/[A-Za-z0-9_./\-]+\.(?:py|sh|md|yaml|yml|txt|json|svg|mmd))`"
)
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def active_docs() -> list[Path]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    docs = []
    for rel in tracked:
        if not rel:
            continue
        if rel in ROOT_DOCS or (rel.startswith("docs/") and not rel.startswith(EXCLUDED_DIRS)):
            docs.append(REPO / rel)
    return sorted(docs)


def strip_fences(text: str) -> str:
    return FENCE_RE.sub("", text)


def rel(path: Path) -> str:
    return str(path.relative_to(REPO))


DOCS = active_docs()
DOC_IDS = [rel(p) for p in DOCS]


def test_documents_are_found():
    """検査対象が空になっていない(除外の誤りで何も検査しない状態を防ぐ)。"""
    assert len(DOCS) >= 15
    assert "README.md" in DOC_IDS and "CLAUDE.md" in DOC_IDS


@pytest.mark.parametrize("doc", DOCS, ids=DOC_IDS)
def test_relative_links_resolve(doc):
    broken = []
    text = INLINE_CODE_RE.sub("", strip_fences(doc.read_text(encoding="utf-8")))
    for target in LINK_RE.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")) or target in ALLOWED_MISSING_LINKS:
            continue
        path = (doc.parent / target.split("#")[0]).resolve()
        if not path.exists():
            broken.append(target)
    assert not broken, f"{rel(doc)}: 存在しないリンク先 {broken}"


@pytest.mark.parametrize("doc", [d for d in DOCS if rel(d) not in LINK_ONLY], ids=lambda d: rel(d))
def test_referenced_repo_paths_exist(doc):
    missing = []
    for path in PATH_RE.findall(strip_fences(doc.read_text(encoding="utf-8"))):
        if "*" in path or path in ALLOWED_MISSING_PATHS:
            continue
        if not (REPO / path).exists():
            missing.append(path)
    assert not missing, f"{rel(doc)}: 存在しないパスへの言及 {sorted(set(missing))}"


@pytest.mark.parametrize("doc", [d for d in DOCS if rel(d) not in LINK_ONLY], ids=lambda d: rel(d))
def test_deleted_modules_are_not_presented_as_current(doc):
    offenders = []
    lines = doc.read_text(encoding="utf-8").splitlines()
    for lineno, line in enumerate(lines, 1):
        # 説明が次の行に折り返されることがあるため、前後 1 行も見る
        context = " ".join(lines[max(lineno - 2, 0): lineno + 1])
        if any(w in context for w in HISTORY_WORDS):
            continue
        for name in DELETED_NAMES:
            # `name` の形(バッククォートで囲んだ単独の名前。`core/xxx.py` のようにディレクトリ付きは別物)
            if f"`{name}`" in line:
                offenders.append(f"L{lineno}: `{name}`")
    assert not offenders, f"{rel(doc)}: 削除済みのモジュールを現行として案内している {offenders}"


def _parser_options(parser: argparse.ArgumentParser) -> set[str]:
    return {opt for action in parser._actions for opt in action.option_strings}


def _tc_options() -> set[str]:
    """`tc`(拡張子の無い Python スクリプト)を読み込み、`build_parser()` の定義済みオプションを返す。"""
    import importlib.util
    from importlib.machinery import SourceFileLoader

    sys.path.insert(0, str(REPO))
    try:
        loader = SourceFileLoader("tc_cli", str(REPO / "tc"))
        spec = importlib.util.spec_from_file_location("tc_cli", str(REPO / "tc"), loader=loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return _parser_options(module.build_parser())
    finally:
        sys.path.remove(str(REPO))


def _transcribe_options() -> set[str]:
    text = (REPO / "transcribe.py").read_text(encoding="utf-8")
    return set(re.findall(r'add_argument\((?:"[^"]*",\s*)*?"(--[a-z\-]+)"', text)) | {"--help"}


@pytest.mark.parametrize("doc", [d for d in DOCS if rel(d) not in LINK_ONLY], ids=lambda d: rel(d))
def test_cli_options_in_commands_exist(doc):
    """`./tc ...` と `transcribe.py ...` のコマンド行に書かれた `--オプション` が、実際の引数定義にある。"""
    tc_opts, tr_opts = _tc_options() | {"-h"}, _transcribe_options() | {"-h", "-p", "-l"}
    problems = []
    for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip().lstrip("$ ").strip("`")
        if re.search(r"(^|\s)(uv run )?\./tc(\s|$)", stripped) and "pytest" not in stripped:
            for opt in re.findall(r"(?<![\w-])(--[a-z][a-z\-]*)", stripped):
                if opt not in tc_opts:
                    problems.append(f"L{lineno}: tc に {opt} は無い")
        elif re.search(r"transcribe\.py\s", stripped) and "pytest" not in stripped:
            for opt in re.findall(r"(?<![\w-])(--[a-z][a-z\-]*)", stripped):
                if opt not in tr_opts:
                    problems.append(f"L{lineno}: transcribe.py に {opt} は無い")
    assert not problems, f"{rel(doc)}: {problems}"


@pytest.mark.parametrize("doc", [d for d in DOCS if rel(d) not in LINK_ONLY], ids=lambda d: rel(d))
def test_pytest_commands_point_to_existing_paths(doc):
    problems = []
    for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
        if "pytest" not in line:
            continue
        for token in re.findall(r"(?<![\w/.-])(tests/[A-Za-z0-9_./\-]+)", line):
            token = token.split("::")[0].rstrip("/.,)`")
            if "*" in token or "<" in token:
                continue
            if not (REPO / token).exists():
                problems.append(f"L{lineno}: {token}")
    assert not problems, f"{rel(doc)}: 存在しない pytest の対象 {problems}"


def test_docs_index_lists_every_current_document():
    """docs/README.md の索引に、docs/ 配下の現行文書がすべて載っている(履歴資料のディレクトリは除く)。"""
    index = (REPO / "docs" / "README.md").read_text(encoding="utf-8")
    missing = []
    for doc in DOCS:
        r = rel(doc)
        if not r.startswith("docs/") or r == "docs/README.md":
            continue
        if r.removeprefix("docs/") not in index:
            missing.append(r)
    assert not missing, f"docs/README.md の索引に無い文書: {missing}"


def test_option_sources_are_loaded():
    """オプション検査が空集合との比較になっていない(恒真になっていない)。"""
    tc_opts = _tc_options()
    assert {"--dry-run", "--no-upload", "--output-dir", "--folder-id"} <= tc_opts
    assert "--bogus" not in tc_opts
    tr_opts = _transcribe_options()
    assert {"--profile", "--language", "--folder-id"} <= tr_opts
