#!/usr/bin/env python3
"""Generate table.json from articles YAML files for Moheji's diaries.

This script parses all YAML files matching `^[0-9]{7}_.+\\.ya?ml$` in the articles directory,
extracts article metadata (id, fileName, title, createDate, updateDate, tags),
sorts them (by createDate descending, then id descending), and writes them out as JSON.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Logger configuration
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("generate_table")

# Regex to match article file names: e.g. 2019001_sample.yml
ARTICLE_FILE_PATTERN = re.compile(r"^([0-9]{7})_(.+)\.ya?ml$", re.IGNORECASE)


def normalize_date(value: Any) -> str:
    """Normalize date/timestamp value into 'YYYY-MM-DD' formatted string.

    Handles datetime.date, datetime.datetime, and string formats.
    """
    if value is None:
        return ""
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.strftime("%Y-%m-%d")

    val_str = str(value).strip()
    match = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", val_str)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

    return val_str


def parse_article_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """Parse a single article YAML file and return record dictionary.

    Returns None if the file is invalid or cannot be parsed.
    """
    match = ARTICLE_FILE_PATTERN.match(file_path.name)
    if not match:
        return None

    article_id = match.group(1)
    file_name = file_path.name

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to parse YAML file '{file_path}': {e}")
        return None

    if not isinstance(data, dict):
        logger.warning(f"File '{file_path}' content is not a mapping/dict. Skipped.")
        return None

    title = str(data.get("title", "")).strip()
    create_date_raw = data.get("createDate")
    update_date_raw = data.get("updateDate")
    raw_tags = data.get("tags")

    # Normalize tags
    tags: List[str] = []
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if t is not None and str(t).strip()]
    elif isinstance(raw_tags, str) and raw_tags.strip():
        tags = [raw_tags.strip()]

    create_date = normalize_date(create_date_raw)
    update_date = normalize_date(update_date_raw) if update_date_raw else create_date

    return {
        "id": article_id,
        "fileName": file_name,
        "title": title,
        "createDate": create_date,
        "updateDate": update_date,
        "tags": tags,
    }


def generate_articles_table(
    articles_dir: Path,
    sort_by: str = "createDate",
    reverse: bool = True,
) -> List[Dict[str, Any]]:
    """Scan articles directory and build sorted list of article records."""
    if not articles_dir.is_dir():
        raise FileNotFoundError(f"Articles directory not found: {articles_dir}")

    records: List[Dict[str, Any]] = []

    for file_path in articles_dir.iterdir():
        if not file_path.is_file():
            continue
        if not ARTICLE_FILE_PATTERN.match(file_path.name):
            continue

        record = parse_article_file(file_path)
        if record:
            records.append(record)

    logger.info(f"Loaded {len(records)} article(s) from {articles_dir}")

    # Sort records
    def sort_key(item: Dict[str, Any]):
        return (item.get(sort_by, ""), item.get("id", ""))

    records.sort(key=sort_key, reverse=reverse)
    return records


def write_table_json(records: List[Dict[str, Any]], output_path: Path) -> None:
    """Save article records to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    logger.info(f"Successfully saved {len(records)} records to {output_path}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate articles table.json from YAML files."
    )
    parser.add_argument(
        "--articles-dir",
        type=Path,
        default=Path("articles"),
        help="Path to articles directory containing YAML files (default: 'articles').",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("github_actions/deliverable/tbl_articles/table.json"),
        help="Destination path for output JSON (default: 'github_actions/deliverable/tbl_articles/table.json').",
    )
    parser.add_argument(
        "--sort-by",
        type=str,
        default="createDate",
        choices=["createDate", "updateDate", "id", "title"],
        help="Field to sort by (default: 'createDate').",
    )
    parser.add_argument(
        "--order",
        type=str,
        default="desc",
        choices=["asc", "desc"],
        help="Sort order (default: 'desc').",
    )

    args = parser.parse_args(argv)

    try:
        records = generate_articles_table(
            articles_dir=args.articles_dir,
            sort_by=args.sort_by,
            reverse=(args.order == "desc"),
        )
        write_table_json(records, args.output)
        return 0
    except Exception as e:
        logger.error(f"Error generating articles table: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
