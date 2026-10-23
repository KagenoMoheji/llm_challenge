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
    validate_params_schema_definition({
        "type": "object",
        "properties": {"node": {"$ref": "#", "description": "再帰的な構造"}},
    })
    validate_params_schema_definition({
        "type": "object",
        "properties": {"user": {"$ref": "#/definitions/user", "description": "対象のユーザ"}},
        "definitions": {"user": {"type": "object", "properties": {"id": {"type": "integer"}}}},
    })


def test_parameter_named_pattern_is_allowed():
    # "pattern" という名前のパラメータ(例: grepのような検索パターン)は、キーワードではないので使える
    validate_params_schema_definition({
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "検索する文字列"},
            "patternProperties": {"type": "string", "description": "名前が紛らわしいパラメータ"},
        },
        "required": ["pattern"],
    })
    validate_params_schema_definition({
        "type": "object",
        "properties": {"options": {"type": "object", "description": "オプション", "properties": {"pattern": {"type": "string", "description": "検索パターン"}}}},
    })


def test_pattern_inside_data_keywords_is_allowed():
    # enum / const / default / examples の中の値は、データ(スキーマではない)。"pattern" というキーがあっても、キーワードではない
    validate_params_schema_definition({
        "type": "object",
        "properties": {
            "options": {"type": "object", "description": "オプション", "default": {"pattern": "TODO"}, "enum": [{"pattern": "a"}, {"pattern": "b"}]},
            "mode": {"type": "string", "description": "モード", "const": "grep"},
        },
        "examples": [{"options": {"pattern": "TODO"}, "mode": "grep"}],
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


def test_pattern_keywords_are_rejected_in_every_subschema_position():
    described = {"type": "string", "description": "x"}
    regex = {"type": "string", "pattern": "^a$"}
    cases = {
        "property": {"type": "object", "properties": {"a": {**described, "pattern": "^a$"}}},
        "nested property": {"type": "object", "properties": {"a": {"type": "object", "description": "x", "properties": {"b": {**described, "pattern": "^a$"}}}}},
        "items": {"type": "object", "properties": {"a": {"type": "array", "description": "x", "items": regex}}},
        "prefixItems": {"type": "object", "properties": {"a": {"type": "array", "description": "x", "prefixItems": [described, regex]}}},
        "additionalProperties": {"type": "object", "properties": {}, "additionalProperties": regex},
        "anyOf": {"type": "object", "properties": {"a": {"description": "x", "anyOf": [{"type": "integer"}, regex]}}},
        "allOf": {"type": "object", "properties": {}, "allOf": [regex]},
        "oneOf": {"type": "object", "properties": {}, "oneOf": [regex]},
        "not": {"type": "object", "properties": {}, "not": regex},
        "if/then/else": {"type": "object", "properties": {}, "if": {"properties": {}}, "then": regex},
        "propertyNames": {"type": "object", "properties": {}, "propertyNames": {"pattern": "^[a-z]+$"}},
        "$defs": {"type": "object", "properties": {}, "$defs": {"s": regex}},
        "definitions": {"type": "object", "properties": {}, "definitions": {"s": regex}},
        "dependentSchemas": {"type": "object", "properties": {}, "dependentSchemas": {"a": regex}},
        "patternProperties": {"type": "object", "properties": {}, "patternProperties": {"^x_": {"type": "string"}}},
    }
    for label, schema in cases.items():
        with pytest.raises(ValueError) as e:
            validate_params_schema_definition(schema)
        assert "pattern" in str(e.value), label


def test_pattern_error_message_tells_where():
    schema = {"type": "object", "properties": {"sql": {"type": "string", "description": "SQL", "pattern": "^SELECT"}}}
    with pytest.raises(ValueError) as e:
        validate_params_schema_definition(schema)
    assert "$.properties.sql.pattern" in str(e.value)


def test_refs_other_than_root_and_defs_are_rejected():
    # "$ref" で、examples などの中のデータを、スキーマとして評価させることで、正規表現の禁止を迂回できてしまうため、参照できる場所を限る
    bypass = {
        "type": "object",
        "properties": {"a": {"$ref": "#/examples/0", "description": "x"}},
        "examples": [{"type": "string", "pattern": "(a+)+$"}],
    }
    for ref in ("#/examples/0", "#/properties/a", "#foo", "#/$defs/a/b", "#/$defs/", "#/$defs", "https://example.com/s.json", "other.json", ""):
        schema = {"type": "object", "properties": {"a": {"$ref": ref, "description": "x"}}}
        with pytest.raises(ValueError) as e:
            validate_params_schema_definition(schema)
        assert "disallowed reference" in str(e.value), ref
    with pytest.raises(ValueError):
        validate_params_schema_definition(bypass)


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
