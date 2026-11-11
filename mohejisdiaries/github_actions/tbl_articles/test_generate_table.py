"""Unit and integration tests for generate_table.py."""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

# Add current directory to sys.path so generate_table can be imported from anywhere
sys.path.insert(0, str(Path(__file__).parent))

import pytest

from generate_table import (
    ARTICLE_FILE_PATTERN,
    generate_articles_table,
    main,
    normalize_date,
    parse_article_file,
    write_table_json,
)


def test_article_file_pattern():
    assert ARTICLE_FILE_PATTERN.match("2019001_sample.yml")
    assert ARTICLE_FILE_PATTERN.match("2026123_hello_world.yaml")
    assert ARTICLE_FILE_PATTERN.match("2020999_test-123.YML")

    # Invalid patterns
    assert not ARTICLE_FILE_PATTERN.match("201901_short.yml")  # only 6 digits
    assert not ARTICLE_FILE_PATTERN.match("20190001_long.yml")  # 8 digits
    assert not ARTICLE_FILE_PATTERN.match("sample.yml")
    assert not ARTICLE_FILE_PATTERN.match("2019001_sample.txt")
    assert not ARTICLE_FILE_PATTERN.match("2019001_.yml")  # empty slug


def test_normalize_date():
    assert normalize_date(datetime.date(2019, 7, 13)) == "2019-07-13"
    assert normalize_date(datetime.datetime(2026, 11, 8, 15, 30)) == "2026-11-08"
    assert normalize_date("2019-07-13") == "2019-07-13"
    assert normalize_date("2019/7/5") == "2019-07-05"
    assert normalize_date("2026.01.09") == "2026-01-09"
    assert normalize_date(None) == ""


def test_parse_article_file(tmp_path: Path):
    valid_file = tmp_path / "2019001_test_article.yml"
    valid_file.write_text(
        """
title: "テスト記事のタイトル"
createDate: 2019-07-13
updateDate: !!timestamp 2019-07-15
tags:
  - Python
  - 機械学習
content:
  - headline: 概要
    body: 本文です
""",
        encoding="utf-8",
    )

    record = parse_article_file(valid_file)
    assert record is not None
    assert record["id"] == "2019001"
    assert record["fileName"] == "2019001_test_article.yml"
    assert record["title"] == "テスト記事のタイトル"
    assert record["createDate"] == "2019-07-13"
    assert record["updateDate"] == "2019-07-15"
    assert record["tags"] == ["Python", "機械学習"]


def test_parse_article_file_fallback_tags_and_date(tmp_path: Path):
    file_path = tmp_path / "2020002_minimal.yml"
    file_path.write_text(
        """
title: 最小記事
createDate: 2020-01-01
""",
        encoding="utf-8",
    )

    record = parse_article_file(file_path)
    assert record is not None
    assert record["id"] == "2020002"
    assert record["updateDate"] == "2020-01-01"  # updateDate falls back to createDate
    assert record["tags"] == []


def test_parse_invalid_file(tmp_path: Path):
    invalid_name = tmp_path / "not_matching.txt"
    invalid_name.write_text("title: invalid", encoding="utf-8")
    assert parse_article_file(invalid_name) is None

    corrupted_yaml = tmp_path / "2021003_broken.yml"
    corrupted_yaml.write_text("title: [broken yaml : {", encoding="utf-8")
    assert parse_article_file(corrupted_yaml) is None


def test_generate_articles_table_and_sorting(tmp_path: Path):
    articles_dir = tmp_path / "articles"
    articles_dir.mkdir()

    # Article 1: Older date
    (articles_dir / "2019001_old.yml").write_text(
        "title: Old Article\ncreateDate: 2019-01-01\ntags: [TagA]\n",
        encoding="utf-8",
    )
    # Article 2: Newer date
    (articles_dir / "2020001_new.yml").write_text(
        "title: New Article\ncreateDate: 2020-05-01\ntags: [TagB]\n",
        encoding="utf-8",
    )
    # Article 3: Same date as Article 2, higher ID
    (articles_dir / "2020002_same_date.yml").write_text(
        "title: Same Date Article\ncreateDate: 2020-05-01\ntags: [TagC]\n",
        encoding="utf-8",
    )
    # Ignore non-matching file
    (articles_dir / "ignore_me.yml").write_text("title: Ignore\n", encoding="utf-8")

    records = generate_articles_table(articles_dir, sort_by="createDate", reverse=True)
    assert len(records) == 3

    # Sorting check: 2020-05-01 (id 2020002), 2020-05-01 (id 2020001), 2019-01-01 (id 2019001)
    assert records[0]["id"] == "2020002"
    assert records[1]["id"] == "2020001"
    assert records[2]["id"] == "2019001"


def test_write_table_json(tmp_path: Path):
    output_path = tmp_path / "deliverable" / "tbl_articles" / "table.json"
    dummy_records = [
        {
            "id": "2019001",
            "fileName": "2019001_sample.yml",
            "title": "テスト",
            "createDate": "2019-07-13",
            "updateDate": "2019-07-13",
            "tags": ["Python"],
        }
    ]

    write_table_json(dummy_records, output_path)
    assert output_path.exists()

    with open(output_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded == dummy_records


def test_main_cli_execution(tmp_path: Path):
    articles_dir = tmp_path / "articles"
    articles_dir.mkdir()
    (articles_dir / "2019001_sample.yml").write_text(
        "title: Sample\ncreateDate: 2019-07-13\ntags: [Test]\n",
        encoding="utf-8",
    )

    out_file = tmp_path / "out" / "table.json"
    exit_code = main(
        [
            "--articles-dir",
            str(articles_dir),
            "--output",
            str(out_file),
        ]
    )
    assert exit_code == 0
    assert out_file.exists()
