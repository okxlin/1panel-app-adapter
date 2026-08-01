#!/usr/bin/env python3
"""Extract supported braced Compose variable names deterministically."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

PARAMETER_EXPRESSION = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)(?:(?::[-+?]|[-+?])(.*))?\s*$",
    flags=re.S,
)
UNBRACED_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _balanced_braced_expression(text: str, start: int) -> tuple[str, int] | None:
    depth = 1
    cursor = start + 2
    expression_start = cursor
    while cursor < len(text):
        if text.startswith("${", cursor):
            depth += 1
            cursor += 2
            continue
        if text[cursor] == "}":
            depth -= 1
            if depth == 0:
                return text[expression_start:cursor], cursor + 1
        cursor += 1
    return None


def _extract_interpolation_names(text: str) -> set[str]:
    names: set[str] = set()
    cursor = 0
    while cursor < len(text):
        if text[cursor] != "$":
            cursor += 1
            continue
        if text.startswith("$$", cursor):
            cursor += 2
            continue
        if text.startswith("${", cursor):
            parsed = _balanced_braced_expression(text, cursor)
            if parsed is None:
                cursor += 2
                continue
            expression, cursor = parsed
            match = PARAMETER_EXPRESSION.fullmatch(expression)
            if match:
                names.add(match.group(1))
                if match.group(2):
                    names.update(_extract_interpolation_names(match.group(2)))
            continue
        match = UNBRACED_NAME.match(text, cursor + 1)
        if match:
            names.add(match.group(0))
            cursor = match.end()
            continue
        cursor += 1
    return names


def _iter_yaml_string_values(value: Any, seen: set[int]):
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        identity = id(value)
        if identity in seen:
            return
        seen.add(identity)
        for child in value.values():
            yield from _iter_yaml_string_values(child, seen)
        return
    if isinstance(value, list):
        identity = id(value)
        if identity in seen:
            return
        seen.add(identity)
        for child in value:
            yield from _iter_yaml_string_values(child, seen)


def extract_compose_variable_names(text: str) -> set[str]:
    payload = yaml.safe_load(text)
    names: set[str] = set()
    for value in _iter_yaml_string_values(payload, set()):
        names.update(_extract_interpolation_names(value))
    return names


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List braced variable names used by a Compose file"
    )
    parser.add_argument("compose_file")
    args = parser.parse_args()
    text = Path(args.compose_file).read_text(encoding="utf-8", errors="ignore")
    for name in sorted(extract_compose_variable_names(text)):
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
