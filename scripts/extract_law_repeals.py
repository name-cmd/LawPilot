#!/usr/bin/env python3
"""Extract law repeal relationships and merge with law_registry.json."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse

from src.config import Config
from src.data_processing.repeal_extractor import extract_directory


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract law repeal registry")
    parser.add_argument(
        "--processed-dir",
        default=Config.PROCESSED_DATA_DIR,
    )
    parser.add_argument(
        "--output",
        default=Config.LAW_REPEALS_PATH,
    )
    parser.add_argument(
        "--registry",
        default=Config.LAW_REGISTRY_PATH,
    )
    args = parser.parse_args()

    merged = extract_directory(args.processed_dir, args.output, args.registry)
    print(f"Wrote {len(merged)} law registry entries to {args.output}")


if __name__ == "__main__":
    main()
