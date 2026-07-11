"""Lossless, JSON-safe interchange for KotOR GFF V3.2 resources.

The regular :class:`GFF3Reader` representation is intentionally convenient:
it exposes scalar values directly and omits their binary field types.  That is
useful for UI queries, but it cannot be written back safely because (for
example) ``Int32``, ``UInt32`` and a TLK ``LocalizedString`` are ambiguous once
their types have been discarded.

This module defines the typed interchange used by the MCP ``readGFF`` and
``writeGFF`` tools.  It retains the file content tag, root/list struct IDs,
field order, every standard GFF field type, all localized-string variants, and
binary data.  PyKotor is the project's declared GFF dependency and supplies
the canonical V3.2 reader/writer used at this fidelity boundary.
"""
from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from typing import Any, Mapping


TYPED_GFF_SCHEMA = "ghostscripter.gff.typed.v1"


class GFFSchemaError(ValueError):
    """Raised when a typed GFF document is incomplete or ambiguous."""


@dataclass
class _EncodeState:
    complete: bool = True


def read_typed_gff(data: bytes, *, max_depth: int | None = None) -> dict[str, Any]:
    """Decode binary GFF bytes into the lossless typed JSON schema.

    Omitting ``max_depth`` returns the entire tree.  Supplying it deliberately
    creates a preview when the tree is deeper than the requested limit; such a
    document is marked incomplete and is rejected by :func:`write_typed_gff`.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("GFF data must be bytes-like")
    raw = bytes(data)
    if len(raw) < 56:
        raise GFFSchemaError("GFF data is shorter than the 56-byte V3.2 header")
    if max_depth is not None and (isinstance(max_depth, bool) or max_depth < 1):
        raise GFFSchemaError("max_depth must be a positive integer or omitted")

    try:
        from pykotor.resource.formats.gff import read_gff
    except ImportError as exc:  # pragma: no cover - declared runtime dependency
        raise RuntimeError("PyKotor is required for typed GFF interchange") from exc

    try:
        gff = read_gff(raw)
    except Exception as exc:
        raise GFFSchemaError(f"invalid or unsupported GFF: {exc}") from exc

    state = _EncodeState()
    root = _struct_to_document(gff.root, depth=0, max_depth=max_depth, state=state)
    version = raw[4:8].decode("ascii", errors="strict")
    file_type = gff.content.value
    return {
        "schema": TYPED_GFF_SCHEMA,
        "file_type": file_type,
        "content": gff.content.name,
        "file_version": version,
        "complete": state.complete,
        "root": root,
    }


def write_typed_gff(document: Mapping[str, Any]) -> bytes:
    """Encode a complete typed GFF document without guessing field types."""
    if not isinstance(document, Mapping):
        raise GFFSchemaError("typed GFF document must be a JSON object")
    if document.get("schema") != TYPED_GFF_SCHEMA:
        raise GFFSchemaError(
            f"unsupported schema {document.get('schema')!r}; expected {TYPED_GFF_SCHEMA!r}"
        )
    if document.get("complete") is not True:
        raise GFFSchemaError(
            "typed GFF document is incomplete/truncated; read it again without maxDepth"
        )

    version = document.get("file_version")
    if version != "V3.2":
        raise GFFSchemaError(
            f"unsupported GFF version {version!r}; KotOR resources require 'V3.2'"
        )

    file_type = document.get("file_type")
    if not isinstance(file_type, str) or len(file_type) != 4:
        raise GFFSchemaError("file_type must be the exact four-character GFF content tag")
    try:
        file_type.encode("ascii", errors="strict")
    except UnicodeEncodeError as exc:
        raise GFFSchemaError("file_type must contain ASCII characters only") from exc

    try:
        from pykotor.resource.formats.gff import write_gff
        from pykotor.resource.formats.gff.gff_data import GFF, GFFContent
        from pykotor.resource.type import ResourceType
    except ImportError as exc:  # pragma: no cover - declared runtime dependency
        raise RuntimeError("PyKotor is required for typed GFF interchange") from exc

    try:
        content = GFFContent(file_type)
    except ValueError as exc:
        raise GFFSchemaError(
            f"{file_type!r} is not a recognized KotOR GFF content tag"
        ) from exc

    content_name = document.get("content")
    if content_name is not None and content_name != content.name:
        raise GFFSchemaError(
            f"content {content_name!r} conflicts with file_type {file_type!r} ({content.name})"
        )

    root_document = document.get("root")
    root = _document_to_struct(root_document, path="root")
    gff = GFF(content)
    gff.root = root
    target = bytearray()
    try:
        write_gff(gff, target, ResourceType.GFF)
    except Exception as exc:
        raise GFFSchemaError(f"could not encode typed GFF: {exc}") from exc
    return bytes(target)


def _struct_to_document(
    struct: Any,
    *,
    depth: int,
    max_depth: int | None,
    state: _EncodeState,
) -> dict[str, Any]:
    if max_depth is not None and depth >= max_depth:
        state.complete = False
        return {
            "struct_id": int(struct.struct_id),
            "truncated": True,
            "fields": [],
        }

    fields: list[dict[str, Any]] = []
    for label, field_type, value in struct:
        fields.append({
            "label": label,
            "type": field_type.name,
            "type_id": int(field_type),
            "value": _value_to_document(
                field_type,
                value,
                depth=depth,
                max_depth=max_depth,
                state=state,
            ),
        })
    return {"struct_id": int(struct.struct_id), "fields": fields}


def _value_to_document(
    field_type: Any,
    value: Any,
    *,
    depth: int,
    max_depth: int | None,
    state: _EncodeState,
) -> Any:
    from pykotor.resource.formats.gff.gff_data import GFFFieldType

    if field_type in {GFFFieldType.UInt64, GFFFieldType.Int64}:
        # JSON numbers are frequently decoded through IEEE-754 doubles.  A
        # decimal string keeps all 64 bits intact across every MCP client.
        return str(value)
    if field_type in {
        GFFFieldType.UInt8,
        GFFFieldType.Int8,
        GFFFieldType.UInt16,
        GFFFieldType.Int16,
        GFFFieldType.UInt32,
        GFFFieldType.Int32,
    }:
        return int(value)
    if field_type in {GFFFieldType.Single, GFFFieldType.Double}:
        numeric = float(value)
        if not math.isfinite(numeric):
            raise GFFSchemaError(
                f"non-finite {field_type.name} values are not JSON-safe"
            )
        return numeric
    if field_type == GFFFieldType.String:
        return str(value)
    if field_type == GFFFieldType.ResRef:
        return str(value)
    if field_type == GFFFieldType.LocalizedString:
        return {
            "stringref": int(value.stringref),
            "substrings": [
                {"id": int(substring_id), "text": text}
                for substring_id, text in value._substrings.items()  # noqa: SLF001
            ],
        }
    if field_type == GFFFieldType.Binary:
        return {
            "encoding": "base64",
            "data": base64.b64encode(bytes(value)).decode("ascii"),
        }
    if field_type == GFFFieldType.Struct:
        return _struct_to_document(
            value, depth=depth + 1, max_depth=max_depth, state=state
        )
    if field_type == GFFFieldType.List:
        return [
            _struct_to_document(
                item, depth=depth + 1, max_depth=max_depth, state=state
            )
            for item in value
        ]
    if field_type == GFFFieldType.Vector4:
        return {
            "x": float(value.x),
            "y": float(value.y),
            "z": float(value.z),
            "w": float(value.w),
        }
    if field_type == GFFFieldType.Vector3:
        return {
            "x": float(value.x),
            "y": float(value.y),
            "z": float(value.z),
        }
    raise GFFSchemaError(f"unsupported GFF field type {field_type!r}")


def _document_to_struct(document: Any, *, path: str) -> Any:  # noqa: C901, PLR0912
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff.gff_data import (
        GFFFieldType,
        GFFList,
        GFFStruct,
    )
    from utility.common.geometry import Vector3, Vector4

    if not isinstance(document, Mapping):
        raise GFFSchemaError(f"{path} must be a struct object")
    if document.get("truncated"):
        raise GFFSchemaError(f"{path} is truncated and cannot be written")

    struct_id = _require_int(document.get("struct_id"), f"{path}.struct_id")
    if not -1 <= struct_id <= 0xFFFFFFFF:
        raise GFFSchemaError(f"{path}.struct_id is outside the uint32/-1 range")
    struct = GFFStruct(struct_id)

    fields = document.get("fields")
    if not isinstance(fields, list):
        raise GFFSchemaError(f"{path}.fields must be an ordered array")
    seen_labels: set[str] = set()

    integer_ranges = {
        GFFFieldType.UInt8: (0, 0xFF),
        GFFFieldType.Int8: (-0x80, 0x7F),
        GFFFieldType.UInt16: (0, 0xFFFF),
        GFFFieldType.Int16: (-0x8000, 0x7FFF),
        GFFFieldType.UInt32: (0, 0xFFFFFFFF),
        GFFFieldType.Int32: (-0x80000000, 0x7FFFFFFF),
        GFFFieldType.UInt64: (0, 0xFFFFFFFFFFFFFFFF),
        GFFFieldType.Int64: (-0x8000000000000000, 0x7FFFFFFFFFFFFFFF),
    }
    integer_setters = {
        GFFFieldType.UInt8: struct.set_uint8,
        GFFFieldType.Int8: struct.set_int8,
        GFFFieldType.UInt16: struct.set_uint16,
        GFFFieldType.Int16: struct.set_int16,
        GFFFieldType.UInt32: struct.set_uint32,
        GFFFieldType.Int32: struct.set_int32,
        GFFFieldType.UInt64: struct.set_uint64,
        GFFFieldType.Int64: struct.set_int64,
    }

    for index, field in enumerate(fields):
        field_path = f"{path}.fields[{index}]"
        if not isinstance(field, Mapping):
            raise GFFSchemaError(f"{field_path} must be an object")
        label = field.get("label")
        if not isinstance(label, str):
            raise GFFSchemaError(f"{field_path}.label must be a string")
        try:
            encoded_label = label.encode("ascii", errors="strict")
        except UnicodeEncodeError as exc:
            raise GFFSchemaError(f"{field_path}.label must be ASCII") from exc
        if len(encoded_label) > 16:
            raise GFFSchemaError(f"{field_path}.label exceeds GFF's 16-byte limit")
        if label in seen_labels:
            raise GFFSchemaError(f"{path} contains duplicate field label {label!r}")
        seen_labels.add(label)

        type_name = field.get("type")
        if not isinstance(type_name, str):
            raise GFFSchemaError(f"{field_path}.type must be a GFF type name")
        try:
            field_type = GFFFieldType[type_name]
        except KeyError as exc:
            raise GFFSchemaError(f"{field_path}.type {type_name!r} is not supported") from exc
        if "type_id" in field:
            type_id = _require_int(field["type_id"], f"{field_path}.type_id")
            if type_id != int(field_type):
                raise GFFSchemaError(
                    f"{field_path}.type_id {type_id} conflicts with {type_name} ({int(field_type)})"
                )

        value = field.get("value")
        if field_type in integer_ranges:
            parsed = _require_int(value, f"{field_path}.value")
            minimum, maximum = integer_ranges[field_type]
            if not minimum <= parsed <= maximum:
                raise GFFSchemaError(
                    f"{field_path}.value is outside {field_type.name}'s range"
                )
            integer_setters[field_type](label, parsed)
        elif field_type in {GFFFieldType.Single, GFFFieldType.Double}:
            parsed_float = _require_float(value, f"{field_path}.value")
            if field_type == GFFFieldType.Single:
                struct.set_single(label, parsed_float)
            else:
                struct.set_double(label, parsed_float)
        elif field_type == GFFFieldType.String:
            struct.set_string(label, _require_string(value, f"{field_path}.value"))
        elif field_type == GFFFieldType.ResRef:
            resref = _require_string(value, f"{field_path}.value")
            if len(resref) > 16:
                raise GFFSchemaError(f"{field_path}.value exceeds KotOR's 16-char ResRef limit")
            struct.set_resref(label, ResRef(resref))
        elif field_type == GFFFieldType.LocalizedString:
            if not isinstance(value, Mapping):
                raise GFFSchemaError(f"{field_path}.value must be a localized-string object")
            stringref = _require_int(value.get("stringref"), f"{field_path}.value.stringref")
            substrings = value.get("substrings")
            if not isinstance(substrings, list):
                raise GFFSchemaError(f"{field_path}.value.substrings must be an array")
            substring_map: dict[int, str] = {}
            for sub_index, substring in enumerate(substrings):
                sub_path = f"{field_path}.value.substrings[{sub_index}]"
                if not isinstance(substring, Mapping):
                    raise GFFSchemaError(f"{sub_path} must be an object")
                substring_id = _require_int(substring.get("id"), f"{sub_path}.id")
                if not 0 <= substring_id <= 0xFFFFFFFF:
                    raise GFFSchemaError(f"{sub_path}.id is outside the uint32 range")
                if substring_id in substring_map:
                    raise GFFSchemaError(f"{sub_path}.id {substring_id} is duplicated")
                substring_map[substring_id] = _require_string(
                    substring.get("text"), f"{sub_path}.text"
                )
            struct.set_locstring(label, LocalizedString(stringref, substring_map))
        elif field_type == GFFFieldType.Binary:
            if not isinstance(value, Mapping) or value.get("encoding") != "base64":
                raise GFFSchemaError(
                    f"{field_path}.value must be {{'encoding': 'base64', 'data': ...}}"
                )
            encoded = _require_string(value.get("data"), f"{field_path}.value.data")
            try:
                decoded = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError) as exc:
                raise GFFSchemaError(f"{field_path}.value.data is not valid base64") from exc
            struct.set_binary(label, decoded)
        elif field_type == GFFFieldType.Struct:
            struct.set_struct(label, _document_to_struct(value, path=f"{field_path}.value"))
        elif field_type == GFFFieldType.List:
            if not isinstance(value, list):
                raise GFFSchemaError(f"{field_path}.value must be a struct array")
            gff_list = GFFList()
            for item_index, item in enumerate(value):
                gff_list.append(
                    _document_to_struct(item, path=f"{field_path}.value[{item_index}]")
                )
            struct.set_list(label, gff_list)
        elif field_type in {GFFFieldType.Vector3, GFFFieldType.Vector4}:
            if not isinstance(value, Mapping):
                raise GFFSchemaError(f"{field_path}.value must be a vector object")
            x = _require_float(value.get("x"), f"{field_path}.value.x")
            y = _require_float(value.get("y"), f"{field_path}.value.y")
            z = _require_float(value.get("z"), f"{field_path}.value.z")
            if field_type == GFFFieldType.Vector3:
                struct.set_vector3(label, Vector3(x, y, z))
            else:
                w = _require_float(value.get("w"), f"{field_path}.value.w")
                struct.set_vector4(label, Vector4(x, y, z, w))
        else:  # pragma: no cover - exhaustive over PyKotor's canonical enum
            raise GFFSchemaError(f"{field_path}.type {type_name!r} is unsupported")

    return struct


def _require_int(value: Any, path: str) -> int:
    if isinstance(value, bool):
        raise GFFSchemaError(f"{path} must be an integer, not boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 10)
        except ValueError as exc:
            raise GFFSchemaError(f"{path} must be a base-10 integer") from exc
    raise GFFSchemaError(f"{path} must be an integer")


def _require_float(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GFFSchemaError(f"{path} must be a finite number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise GFFSchemaError(f"{path} must be finite")
    return parsed


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise GFFSchemaError(f"{path} must be a string")
    return value
