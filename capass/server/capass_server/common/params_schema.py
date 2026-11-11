import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import json
import re
from typing import Any
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from capass_server.common.globals import PARAMS_ERROR_MAX_COUNT, PARAMS_ERROR_MAX_LEN, PARAMS_SCHEMA_MAX_BYTES

# 参照("$ref")は、ルート("#")と、ルート直下の定義("#/$defs/<名前>"、"#/definitions/<名前>")だけ使える。
# それ以外(外部のスキーマ、スキーマ中の任意の場所、アンカー)を許すと、下の正規表現の禁止を、迂回できてしまう
# (例: "$ref": "#/examples/0" で、examplesの中に書いた "pattern" を、スキーマとして評価させる)。
_ALLOWED_REF = re.compile(r"^#(/(\$defs|definitions)/[^/]+)?$")
_DISALLOWED_REF_KEYWORDS = ("$dynamicRef", "$recursiveRef")

# 正規表現を取る、JSON Schemaのキーワード。Pythonのre(バックトラック方式)で評価されるため、
# 悪意のある(または不注意な)正規表現と入力の組み合わせで、処理時間が急激に増える(ReDoS)。登録を拒否する
_REGEX_KEYWORDS = ("pattern", "patternProperties")

# スキーマを値に取るキーワード(値が、サブスキーマ)。正規表現のキーワードを探すときに、サブスキーマとして辿る
_SUBSCHEMA_KEYWORDS = (
    "additionalProperties", "additionalItems", "items", "contains", "propertyNames", "not", "if", "then", "else",
    "unevaluatedItems", "unevaluatedProperties", "contentSchema",
)
_SUBSCHEMA_LIST_KEYWORDS = ("allOf", "anyOf", "oneOf", "prefixItems", "items")  # 値が、サブスキーマのリスト
_SUBSCHEMA_MAP_KEYWORDS = ("properties", "$defs", "definitions", "dependentSchemas", "dependencies")  # 値が、「名前 → サブスキーマ」の辞書


def validate_params_schema_definition(schema: dict[str, Any]) -> None:
    """ツール登録時に、paramsのスキーマ(JSON Schema)が、受け入れられる形かを検証する。不正ならValueError(理由付き)。

    受け入れる条件:
    - JSON Schemaとして正しい(`$schema` を省略した場合は、Draft 2020-12)
    - サイズがPARAMS_SCHEMA_MAX_BYTES以下
    - ルートが {"type": "object", "properties": {...}} である(パラメータが無いツールは "properties": {} )
    - 各パラメータ(properties直下)に、空でない "description" がある(AIエージェントが、何を渡すべきかを理解できるようにするため)
    - `$ref` は、"#"、"#/$defs/<名前>"、"#/definitions/<名前>" のみ(外部のスキーマを取得させないため。`$dynamicRef` と `$recursiveRef` は不可)
    - 正規表現のキーワード("pattern"、"patternProperties")が無いこと(ReDoSを防ぐため。値の形式の確認には、enumや範囲などを使う)。
      "pattern" という名前のパラメータ(properties の中の名前)は、キーワードではないので、使える
    """
    size = len(json.dumps(schema, ensure_ascii=False).encode("utf-8"))
    if size > PARAMS_SCHEMA_MAX_BYTES:
        raise ValueError(f"params_schema is too large ({size} bytes, max {PARAMS_SCHEMA_MAX_BYTES})")
    disallowed_ref = _find_disallowed_ref(schema)
    if disallowed_ref is not None:
        raise ValueError(f'params_schema contains a disallowed reference: {disallowed_ref} ("$ref" must be "#", "#/$defs/<name>" or "#/definitions/<name>")')
    regex_keyword = _find_regex_keyword(schema, "$")
    if regex_keyword is not None:
        raise ValueError(f'params_schema must not use "pattern" or "patternProperties" (regular expressions are not supported): {regex_keyword}')
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


def _find_disallowed_ref(node: Any) -> str | None:
    """許可されていない参照("$ref" の値が、許可された形式ではない、または $dynamicRef/$recursiveRef)を、文書全体から探す。見つからなければNone。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _DISALLOWED_REF_KEYWORDS:
                return f'"{key}"'
            if key == "$ref" and not (isinstance(value, str) and _ALLOWED_REF.match(value)):
                return f'"$ref": {json.dumps(value, ensure_ascii=False)}'
            found = _find_disallowed_ref(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_disallowed_ref(item)
            if found is not None:
                return found
    return None


def _find_regex_keyword(schema: Any, path: str) -> str | None:
    """スキーマの中で、正規表現のキーワード("pattern"、"patternProperties")が使われている場所を探す。見つからなければNone。

    スキーマの構造に沿って辿る(サブスキーマだけを調べる)。そのため、次は、キーワードとして扱わない:
    - properties の中の、パラメータの名前("pattern" という名前のパラメータ)
    - enum / const / default / examples の中の値(データ)
    データの中身が、スキーマとして評価される("$ref" で参照される)ことは、_ALLOWED_REF で防いでいる。
    """
    if not isinstance(schema, dict):
        return None
    for keyword in _REGEX_KEYWORDS:
        if keyword in schema:
            return f"{path}.{keyword}"
    for keyword in _SUBSCHEMA_KEYWORDS:
        found = _find_regex_keyword(schema.get(keyword), f"{path}.{keyword}")
        if found is not None:
            return found
    for keyword in _SUBSCHEMA_LIST_KEYWORDS:
        items = schema.get(keyword)
        if isinstance(items, list):
            for i, sub in enumerate(items):
                found = _find_regex_keyword(sub, f"{path}.{keyword}[{i}]")
                if found is not None:
                    return found
    for keyword in _SUBSCHEMA_MAP_KEYWORDS:
        mapping = schema.get(keyword)
        if isinstance(mapping, dict):
            for name, sub in mapping.items():
                found = _find_regex_keyword(sub, f"{path}.{keyword}.{name}")
                if found is not None:
                    return found
    return None
