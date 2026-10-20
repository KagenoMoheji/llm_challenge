import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import json
from typing import Any
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from capass_server.common.globals import PARAMS_ERROR_MAX_COUNT, PARAMS_ERROR_MAX_LEN, PARAMS_SCHEMA_MAX_BYTES

_REF_KEYS = ("$ref", "$dynamicRef", "$recursiveRef")


def validate_params_schema_definition(schema: dict[str, Any]) -> None:
    """ツール登録時に、paramsのスキーマ(JSON Schema)が、受け入れられる形かを検証する。不正ならValueError(理由付き)。

    受け入れる条件:
    - JSON Schemaとして正しい(`$schema` を省略した場合は、Draft 2020-12)
    - サイズがPARAMS_SCHEMA_MAX_BYTES以下
    - ルートが {"type": "object", "properties": {...}} である(パラメータが無いツールは "properties": {} )
    - 各パラメータ(properties直下)に、空でない "description" がある(AIエージェントが、何を渡すべきかを理解できるようにするため)
    - `$ref` は、スキーマ内の参照("#" から始まるもの)のみ(外部のスキーマを取得させないため)
    """
    size = len(json.dumps(schema, ensure_ascii=False).encode("utf-8"))
    if size > PARAMS_SCHEMA_MAX_BYTES:
        raise ValueError(f"params_schema is too large ({size} bytes, max {PARAMS_SCHEMA_MAX_BYTES})")
    if _has_non_local_ref(schema):
        raise ValueError('params_schema must not contain external references ("$ref" must start with "#")')
    try:
        validator_for(schema, default=Draft202012Validator).check_schema(schema)
    except SchemaError as e:
        raise ValueError(f"params_schema is not a valid JSON Schema: {e.message}")
    if schema.get("type") != "object":
        raise ValueError('params_schema must be an object schema: {"type": "object", "properties": {...}}')
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError('params_schema must have "properties" (use {} for a tool without parameters)')
    for name, prop in properties.items():
        description = prop.get("description") if isinstance(prop, dict) else None
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f'parameter "{name}" must have a non-empty "description" (so that AI agents can understand what to pass)')


def validate_params(schema: dict[str, Any], params: Any) -> list[str]:
    """paramsが、スキーマに合っているかを検証する。合っていれば空のリスト。合っていなければ、エラーの説明のリスト
    (PARAMS_ERROR_MAX_COUNT件まで。例: "$.sql: 'sql' is a required property")。AIエージェントが、パラメータを直せるようにするためのもの。"""
    validator = validator_for(schema, default=Draft202012Validator)(schema)
    errors = sorted(validator.iter_errors(params), key=lambda e: [str(p) for p in e.absolute_path])
    return [f"{_format_path(e.absolute_path)}: {e.message[:PARAMS_ERROR_MAX_LEN]}" for e in errors[:PARAMS_ERROR_MAX_COUNT]]


def _format_path(path) -> str:
    """検証エラーの場所を、"$.a[0].b" の形にする。"""
    text = "$"
    for part in path:
        text += f"[{part}]" if isinstance(part, int) else f".{part}"
    return text


def _has_non_local_ref(node: Any) -> bool:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _REF_KEYS and not (isinstance(value, str) and value.startswith("#")):
                return True
            if _has_non_local_ref(value):
                return True
    elif isinstance(node, list):
        return any(_has_non_local_ref(item) for item in node)
    return False
