import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
# 以下のROOTPATHでimportの起点を指定
ROOTPATH = os.path.abspath(f"{PYPATH}/..")
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]
sys.path.append(ROOTPATH)

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import pytest
from capass_server.common.globals import PARAMS_ERROR_MAX_COUNT, PARAMS_SCHEMA_MAX_BYTES
from capass_server.common.params_schema import validate_params, validate_params_schema_definition

SQL_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {"type": "string", "description": "実行するSQL文"},
        "limit": {"type": "integer", "description": "最大行数", "minimum": 1, "maximum": 1000},
        "format": {"type": "string", "description": "出力形式", "enum": ["json", "csv"]},
    },
    "required": ["sql"],
    "additionalProperties": False,
}


# ---------- validate_params_schema_definition ----------
def test_valid_definitions_are_accepted():
    validate_params_schema_definition(SQL_SCHEMA)
    validate_params_schema_definition({"type": "object", "properties": {}})  # パラメータが無いツール
    validate_params_schema_definition({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "properties": {"a": {"type": "string", "description": "a"}}})
    validate_params_schema_definition({
        "type": "object",
        "properties": {"user": {"$ref": "#/$defs/user", "description": "対象のユーザ"}},
        "$defs": {"user": {"type": "object", "properties": {"id": {"type": "integer"}}}},
    })


@pytest.mark.parametrize("schema, message", [
    ({"type": "array", "items": {}}, "object schema"),
    ({"properties": {}}, "object schema"),
    ({"type": "object"}, "properties"),
    ({"type": "object", "properties": []}, "not a valid JSON Schema"),
    ({"type": "object", "properties": {"a": {"type": "string"}}}, "description"),
    ({"type": "object", "properties": {"a": {"type": "string", "description": ""}}}, "description"),
    ({"type": "object", "properties": {"a": {"type": "string", "description": 5}}}, "not a valid JSON Schema"),
    ({"type": "object", "properties": {"a": True}}, "description"),
    ({"type": "object", "properties": {"a": {"type": "bogus", "description": "x"}}}, "not a valid JSON Schema"),
    ({"type": "object", "properties": {}, "required": "a"}, "not a valid JSON Schema"),
])
def test_invalid_definitions_are_rejected(schema, message):
    with pytest.raises(ValueError) as e:
        validate_params_schema_definition(schema)
    assert message in str(e.value)


def test_external_refs_are_rejected_anywhere():
    for ref_key in ("$ref", "$dynamicRef", "$recursiveRef"):
        schema = {"type": "object", "properties": {"a": {ref_key: "https://evil.example.com/s.json", "description": "x"}}}
        with pytest.raises(ValueError):
            validate_params_schema_definition(schema)
    nested = {"type": "object", "properties": {"a": {"description": "x", "anyOf": [{"type": "string"}, {"items": [{"$ref": "file:///etc/passwd"}]}]}}}
    with pytest.raises(ValueError):
        validate_params_schema_definition(nested)


def test_too_large_definition_is_rejected():
    schema = {"type": "object", "properties": {"a": {"type": "string", "description": "x" * PARAMS_SCHEMA_MAX_BYTES}}}
    with pytest.raises(ValueError):
        validate_params_schema_definition(schema)


# ---------- validate_params ----------
def test_valid_params_return_no_errors():
    assert validate_params(SQL_SCHEMA, {"sql": "SELECT 1"}) == []
    assert validate_params(SQL_SCHEMA, {"sql": "SELECT 1", "limit": 10, "format": "csv"}) == []
    assert validate_params({"type": "object", "properties": {}}, {}) == []


def test_invalid_params_return_where_and_what():
    errors = validate_params(SQL_SCHEMA, {"limit": 0, "format": "xml", "extra": 1})
    assert any(e.startswith("$: ") and "'sql' is a required property" in e for e in errors)
    assert any(e.startswith("$.limit: ") for e in errors)
    assert any(e.startswith("$.format: ") for e in errors)
    assert any(e.startswith("$: ") and "extra" in e for e in errors)  # additionalProperties: false


def test_nested_error_paths():
    schema = {"type": "object", "properties": {"items": {"type": "array", "description": "x", "items": {"type": "object", "properties": {"n": {"type": "integer"}}}}}}
    errors = validate_params(schema, {"items": [{"n": 1}, {"n": "x"}]})
    assert len(errors) == 1
    assert errors[0].startswith("$.items[1].n: ")


def test_params_that_are_not_an_object_are_rejected():
    assert validate_params(SQL_SCHEMA, "SELECT 1")
    assert validate_params(SQL_SCHEMA, [1, 2])


def test_errors_are_limited_in_count_and_length():
    schema = {"type": "object", "properties": {f"p{i}": {"type": "integer", "description": "n"} for i in range(50)}}
    errors = validate_params(schema, {f"p{i}": "x" * 1000 for i in range(50)})
    assert len(errors) == PARAMS_ERROR_MAX_COUNT
    assert all(len(e) < 400 for e in errors)  # 長い値をそのまま返さない
