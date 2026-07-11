"""Install bundled KotOR NWScript definitions into PyKotor's compiler.

PyKotor 2.3.12's generated tables omit TSL action 876 and 45 FORM_* constants,
and its declaration parser loses the first PlayPazaak parameter.  GhostScripter
ships pinned, retail-derived/community-corrected headers, so compilation must use
the same ordered definitions that the editor and reference browser expose.
"""

from __future__ import annotations

import ast
from typing import Any

from ghostscripter.core.nwscript.parser import NWConstant, NWParam, get_nwscript_db


_installed: set[str] = set()


def _constant_value(constant: NWConstant, constants: dict[str, NWConstant]) -> Any:
    raw = constant.value.strip()
    seen: set[str] = set()
    while raw in constants and raw not in seen:
        seen.add(raw)
        raw = constants[raw].value.strip()
    if constant.type == "int":
        return int(raw, 0)
    if constant.type == "float":
        return float(raw.rstrip("fF"))
    if constant.type == "string":
        value = ast.literal_eval(raw)
        if not isinstance(value, str):
            raise ValueError(f"{constant.name} is not a string literal")
        return value
    raise ValueError(f"Unsupported NWScript constant type: {constant.type}")


def _default_value(
    param: NWParam,
    constants: dict[str, NWConstant],
) -> Any | None:
    raw = param.default
    if raw is None:
        return None
    raw = raw.strip()

    if param.type == "object":
        if raw == "OBJECT_SELF":
            return 0
        if raw == "OBJECT_INVALID":
            return 1
        if raw in constants:
            return int(_constant_value(constants[raw], constants))
        return int(raw, 0)

    if param.type in {"int", "float"}:
        if raw in constants:
            value = _constant_value(constants[raw], constants)
        elif param.type == "int":
            value = int(raw, 0)
        else:
            value = float(raw.rstrip("fF"))
        # PyKotor's compiler models scalar defaults as source-text literals.
        return str(value)

    if param.type == "string":
        value = ast.literal_eval(raw)
        if not isinstance(value, str):
            raise ValueError(f"Default for {param.name} is not a string literal")
        return value

    if param.type == "vector":
        from utility.common.geometry import Vector3

        values = ast.literal_eval(raw)
        if not isinstance(values, (list, tuple)) or len(values) != 3:
            raise ValueError(f"Default for {param.name} is not a 3D vector")
        return Vector3(*(float(value) for value in values))

    raise ValueError(
        f"Unsupported default for NWScript {param.type} parameter {param.name}"
    )


def install_pykotor_definitions(game: str) -> None:
    """Replace PyKotor's game table in-place with the bundled ordered table.

    The mutation is process-local and idempotent.  Updating the lists in-place
    also updates modules that imported PyKotor's original list objects.
    """

    game_id = game.upper()
    if game_id not in {"K1", "K2"}:
        raise ValueError("game must be 'K1' or 'K2'")
    if game_id in _installed:
        return

    from pykotor.common import scriptdefs
    from pykotor.common.script import DataType, ScriptConstant, ScriptFunction, ScriptParam
    from pykotor.resource.formats.ncs import ncs_auto

    db = get_nwscript_db(game_id)
    if not db.is_loaded:
        raise RuntimeError(f"Bundled {game_id} nwscript.nss is unavailable")

    datatype = {item.value: item for item in DataType}
    constants_by_name = {constant.name: constant for constant in db.constants}

    functions = []
    for function in db.functions:
        try:
            return_type = datatype[function.return_type]
            params = [
                ScriptParam(
                    datatype[param.type],
                    param.name,
                    _default_value(param, constants_by_name),
                )
                for param in function.params
            ]
        except KeyError as exc:
            raise RuntimeError(
                f"Unsupported type in {game_id} declaration {function.signature}"
            ) from exc
        declaration = function.signature + ";"
        description = function.comment or declaration
        functions.append(
            ScriptFunction(return_type, function.name, params, description, declaration)
        )

    constants = [
        ScriptConstant(
            datatype[constant.type],
            constant.name,
            _constant_value(constant, constants_by_name),
        )
        for constant in db.constants
    ]

    if game_id == "K1":
        function_targets = (scriptdefs.KOTOR_FUNCTIONS, ncs_auto.KOTOR_FUNCTIONS)
        constant_targets = (scriptdefs.KOTOR_CONSTANTS, ncs_auto.KOTOR_CONSTANTS)
    else:
        function_targets = (scriptdefs.TSL_FUNCTIONS, ncs_auto.TSL_FUNCTIONS)
        constant_targets = (scriptdefs.TSL_CONSTANTS, ncs_auto.TSL_CONSTANTS)

    for target in function_targets:
        target[:] = functions
    for target in constant_targets:
        target[:] = constants
    _installed.add(game_id)


def invalidate_pykotor_definitions() -> None:
    """Forget installation state for tests after external table replacement."""

    _installed.clear()

