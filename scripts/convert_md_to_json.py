"""
Convert Markdown law files in data/raw/ to structured JSON in data/processed/.

Supports multiple laws: place each .md under data/raw/ (subfolders allowed).

---------------------------------------------------------------------------
File naming convention (law name = filename without .md)
---------------------------------------------------------------------------
  Use the name you want the model to cite inside 《》.

  Good examples:
    民法典.md          -> law_name: 民法典        (matches 《民法典》第N条)
    宪法.md            -> law_name: 宪法
    劳动合同法.md      -> law_name: 劳动合同法
    民事诉讼法2021.md  -> law_name: 民事诉讼法2021  (version in name if needed)

  Rules:
    - One law per file; extension must be .md
    - Avoid \\ / : * ? " < > | in filenames
    - Do not rely on the # title inside the Markdown for law_name
    - Prefer short names consistent with common legal citations
    - Optional: use subfolders under data/raw/ (output JSON name = stem only)

---------------------------------------------------------------------------
Usage:
    python scripts/convert_md_to_json.py
    python scripts/convert_md_to_json.py --input data/raw --output data/processed

After conversion:
    python scripts/build_knowledge_base.py --data-dir data/processed
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import json
from src.config import Config
from src.data_processing.md_converter import convert_md_directory


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert law Markdown files to JSON (law name = filename stem)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Naming: 民法典.md -> law_name '民法典'. "
            "See script docstring for full conventions."
        ),
    )
    parser.add_argument("--input", default=Config.RAW_DATA_DIR, help="Directory with .md files")
    parser.add_argument("--output", default=Config.PROCESSED_DATA_DIR, help="Output JSON directory")
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only scan top-level .md in --input",
    )
    parser.add_argument(
        "--registry", default=str(Config.BASE_DIR / "data" / "law_registry.json"),
        help="Law metadata registry JSON to embed in processed files",
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if not input_dir.is_dir():
        print(f"输入目录不存在: {input_dir}")
        sys.exit(1)

    print("=== Markdown -> JSON 法律数据转换 ===\n")
    print(f"输入: {input_dir}")
    print(f"输出: {output_dir}")
    print("法律名称: 使用 .md 文件名（不含扩展名）\n")

    registry_path = Path(args.registry)
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    results = convert_md_directory(
        input_dir,
        output_dir,
        recursive=not args.no_recursive,
        registry=registry,
    )

    if not results:
        print("未找到 .md 文件。请将法律 Markdown 放入 data/raw/ 后重试。")
        sys.exit(1)

    total_articles = 0
    for md_path, json_path, count in results:
        rel = md_path.relative_to(input_dir)
        print(f"  [OK] {rel}")
        print(f"    -> {json_path.name}  ({count} 条)")
        total_articles += count

    print(f"\n=== 完成：{len(results)} 部法律，共 {total_articles} 条法条 ===")
    print("\n下一步构建向量库：")
    print(f"  python scripts/build_knowledge_base.py --data-dir {output_dir}")


if __name__ == "__main__":
    main()
