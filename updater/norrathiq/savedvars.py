from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class SavedVariablesError(ValueError):
    pass


class LuaLiteralParser:
    """Parse the inert literal subset emitted by WoW SavedVariables."""

    def __init__(self, source: str, start: int = 0) -> None:
        self.source = source
        self.index = start

    def parse(self) -> Any:
        value = self.parse_value()
        self.skip()
        return value

    def skip(self) -> None:
        while self.index < len(self.source):
            if self.source[self.index].isspace():
                self.index += 1
                continue
            if self.source.startswith("--[[", self.index):
                end = self.source.find("]]", self.index + 4)
                if end < 0:
                    raise self.error("Unterminated block comment")
                self.index = end + 2
                continue
            if self.source.startswith("--", self.index):
                end = self.source.find("\n", self.index + 2)
                self.index = len(self.source) if end < 0 else end + 1
                continue
            break

    def parse_value(self) -> Any:
        self.skip()
        if self.index >= len(self.source):
            raise self.error("Expected a value")
        char = self.source[self.index]
        if char == "{":
            return self.parse_table()
        if char in {"'", '"'}:
            return self.parse_string()
        number = re.match(r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", self.source[self.index :])
        if number:
            token = number.group(0)
            self.index += len(token)
            return float(token) if any(marker in token for marker in ".eE") else int(token)
        identifier = self.parse_identifier()
        if identifier == "true":
            return True
        if identifier == "false":
            return False
        if identifier == "nil":
            return None
        raise self.error(f"Unsupported identifier value {identifier!r}")

    def parse_table(self) -> Any:
        self.expect("{")
        values: dict[Any, Any] = {}
        next_array_key = 1
        while True:
            self.skip()
            if self.peek("}"):
                self.index += 1
                break
            key: Any
            value: Any
            if self.peek("["):
                self.index += 1
                key = self.parse_value()
                self.expect("]")
                self.expect("=")
                value = self.parse_value()
            else:
                saved = self.index
                identifier = self.try_identifier()
                self.skip()
                if identifier is not None and self.peek("="):
                    self.index += 1
                    key = identifier
                    value = self.parse_value()
                else:
                    self.index = saved
                    key = next_array_key
                    next_array_key += 1
                    value = self.parse_value()
            if key is not None and value is not None:
                values[key] = value
            self.skip()
            if self.peek(",") or self.peek(";"):
                self.index += 1
            elif not self.peek("}"):
                raise self.error("Expected ',', ';', or '}'")
        if values and all(isinstance(key, int) for key in values):
            keys = sorted(values)
            if keys == list(range(1, len(keys) + 1)):
                return [values[key] for key in keys]
        return values

    def parse_string(self) -> str:
        quote = self.source[self.index]
        self.index += 1
        output: list[str] = []
        escapes = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
        while self.index < len(self.source):
            char = self.source[self.index]
            self.index += 1
            if char == quote:
                return "".join(output)
            if char != "\\":
                output.append(char)
                continue
            if self.index >= len(self.source):
                raise self.error("Unterminated escape sequence")
            escaped = self.source[self.index]
            self.index += 1
            if escaped in escapes:
                output.append(escapes[escaped])
            elif escaped in {"\\", "'", '"'}:
                output.append(escaped)
            elif escaped == "\n":
                pass
            elif escaped.isdigit():
                digits = escaped
                while len(digits) < 3 and self.index < len(self.source) and self.source[self.index].isdigit():
                    digits += self.source[self.index]
                    self.index += 1
                output.append(chr(int(digits, 10)))
            else:
                output.append(escaped)
        raise self.error("Unterminated string")

    def parse_identifier(self) -> str:
        identifier = self.try_identifier()
        if identifier is None:
            raise self.error("Expected identifier")
        return identifier

    def try_identifier(self) -> str | None:
        self.skip()
        match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", self.source[self.index :])
        if not match:
            return None
        value = match.group(0)
        self.index += len(value)
        return value

    def expect(self, token: str) -> None:
        self.skip()
        if not self.source.startswith(token, self.index):
            raise self.error(f"Expected {token!r}")
        self.index += len(token)

    def peek(self, token: str) -> bool:
        self.skip()
        return self.source.startswith(token, self.index)

    def error(self, message: str) -> SavedVariablesError:
        line = self.source.count("\n", 0, self.index) + 1
        return SavedVariablesError(f"{message} at line {line}, offset {self.index}")


def load_saved_variable(path: str | Path, variable: str = "NorrathIQCaptureDB") -> dict[str, Any]:
    source = Path(path).read_text(encoding="utf-8-sig")
    match = re.search(rf"(?m)^\s*{re.escape(variable)}\s*=", source)
    if not match:
        raise SavedVariablesError(f"{variable} was not found in {path}")
    value = LuaLiteralParser(source, match.end()).parse()
    if not isinstance(value, dict):
        raise SavedVariablesError(f"{variable} must be a table")
    return value
