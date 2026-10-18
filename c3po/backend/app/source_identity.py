"""The source identity of named functions and methods, from a module's TEXT — standard library only.

The producer of the US point-in-time backtest (``PREREG_VALUATION_PIT_BACKTEST_US_V1`` §1.3) names, besides whole files,
the ``Database`` methods its readers call (``valuation_pit_rerun.IMPLEMENTATION_OBJECTS``): the grid and every run hash
them from the deployed ``database.py``, and the workflow hashes them from ``git show <prereg commit>:…`` on the runner,
where the application cannot be imported. Both go through :func:`objects_sha256`.

What is hashed: the sha256 of the source lines of the definition, from its first decorator (or its ``def`` line) to the
last line of the last statement of its body, by the parser's own positions — a comment after the last statement is NOT
part of it (``inspect.getsource`` on Python 3.12 includes such a comment; for the methods the producer names the two
agree, which a test checks). A name defined twice in the same body (two ``def``s, or two classes on the way) is refused:
Python runs the LAST definition, and hashing either one alone would name the wrong code. A definition nested under an
``if``/``try`` is not found (refused), never guessed.

``python3 -I source_identity.py <module file> <Qualified.name>…`` prints ``{name: sha256}`` as one JSON line.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Iterable

_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _unique(body: list[ast.stmt], name: str, qualified: str) -> ast.stmt:
    """The ONE definition (function, method or class) of ``name`` in ``body``: ``KeyError`` when there is none, ``ValueError``
    when the body defines it twice."""
    found = [item for item in body if isinstance(item, _DEFINITIONS) and item.name == name]
    if not found:
        raise KeyError(f"{qualified}: no definition {name!r}")
    if len(found) > 1:
        raise ValueError(f"{qualified}: {name!r} is defined {len(found)} times — Python runs the last one; refused")
    return found[0]


def _source(tree: ast.Module, lines: list[str], qualified: str) -> str:
    body: list[ast.stmt] = tree.body
    parts = qualified.split(".")
    node: ast.stmt | None = None
    for index, part in enumerate(parts):
        node = _unique(body, part, qualified)
        last = index == len(parts) - 1
        if last and not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise KeyError(f"{qualified}: {part!r} is not a function")
        if not last and not isinstance(node, ast.ClassDef):
            raise KeyError(f"{qualified}: {part!r} is not a class")
        body = list(getattr(node, "body", []))
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    first = min([node.lineno] + [decorator.lineno for decorator in node.decorator_list])
    return "".join(lines[first - 1:node.end_lineno])


def object_source(text: str, qualified: str) -> str:
    """The hashed source of the function or method ``qualified`` (``name`` or ``Class.name``, nested classes allowed) of
    the module ``text``."""
    return _source(ast.parse(text), io.StringIO(text).readlines(), qualified)


def object_sha256(text: str, qualified: str) -> str:
    return hashlib.sha256(object_source(text, qualified).encode("utf-8")).hexdigest()


def objects_sha256(text: str, names: Iterable[str]) -> dict[str, str]:
    """``{name: sha256}`` of several objects of ONE module, parsed once."""
    tree, lines = ast.parse(text), io.StringIO(text).readlines()  # split on \n only, as the parser counts lines
    return {name: hashlib.sha256(_source(tree, lines, name).encode("utf-8")).hexdigest() for name in names}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2:
        print("usage: source_identity.py <module file> <Qualified.name>...", file=sys.stderr)
        return 2
    print(json.dumps(objects_sha256(Path(args[0]).read_text(encoding="utf-8"), args[1:]), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
