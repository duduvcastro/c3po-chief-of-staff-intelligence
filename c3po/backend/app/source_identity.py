"""The source identity of named functions and methods, from a module's TEXT — standard library only.

The producer of the US point-in-time backtest (``PREREG_VALUATION_PIT_BACKTEST_US_V1`` §1.3) names, besides whole files,
the ``Database`` methods its readers call (``valuation_pit_rerun.IMPLEMENTATION_OBJECTS``): the grid and every run hash
them from the deployed ``database.py``, and the workflow hashes them from ``git show <prereg commit>:…`` on the runner,
where the application cannot be imported. Both go through :func:`object_sha256`: the sha256 of exactly the lines
``inspect.getsource`` returns for the object (its first decorator through the last line of its last statement) — the text
the ``object`` pins of the pre-registrations hash.

``python3 -I source_identity.py <module file> <Qualified.name>…`` prints ``{name: sha256}`` as one JSON line.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import sys
from pathlib import Path


def object_source(text: str, qualified: str) -> str:
    """The source lines of the function or method ``qualified`` (``name`` or ``Class.name``, nested classes allowed) of
    the module ``text``, as ``inspect.getsource`` returns them. ``KeyError`` when the module defines no such object."""
    body: list[ast.stmt] = ast.parse(text).body
    parts = qualified.split(".")
    node: ast.AST | None = None
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        wanted = (ast.FunctionDef, ast.AsyncFunctionDef) if last else (ast.ClassDef,)
        node = next((item for item in body if isinstance(item, wanted) and item.name == part), None)
        if node is None:
            raise KeyError(f"{qualified}: no {'function' if last else 'class'} {part!r}")
        body = _body(node)
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    first = min([node.lineno] + [decorator.lineno for decorator in node.decorator_list])
    lines = io.StringIO(text).readlines()  # split on \n only, as linecache (inspect) does
    return "".join(lines[first - 1:node.end_lineno])


def _body(node: ast.AST) -> list[ast.stmt]:
    return list(getattr(node, "body", []))


def object_sha256(text: str, qualified: str) -> str:
    return hashlib.sha256(object_source(text, qualified).encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2:
        print("usage: source_identity.py <module file> <Qualified.name>...", file=sys.stderr)
        return 2
    text = Path(args[0]).read_text(encoding="utf-8")
    print(json.dumps({name: object_sha256(text, name) for name in args[1:]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
