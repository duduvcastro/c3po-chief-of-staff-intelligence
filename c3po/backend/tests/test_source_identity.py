"""``app.source_identity``: what is hashed for a named function or method of a module's text — the definition from its
first decorator to the last line of its last statement — and what is refused (a name defined twice, a definition the
parser cannot reach without guessing). Compared with ``inspect.getsource`` of the live object where they agree."""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app import source_identity


def _load(tmp_path: Path, text: str, name: str = "synthetic_module") -> ModuleType:
    path = tmp_path / f"{name}.py"
    path.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _live(module: ModuleType, attribute: str = "price_bars") -> str:
    value = module.Database.__dict__[attribute]
    if isinstance(value, (staticmethod, classmethod)):
        value = value.__func__
    if isinstance(value, property):
        value = value.fget
    return inspect.getsource(value)


DECORATED = '''
def deco(*args, **kwargs):
    def wrap(function):
        return function
    return wrap


class Database:
    @deco(
        1,
        2)
    @staticmethod
    def price_bars(x):
        return x

    @property
    def price_bars_v2(self):
        return 2
'''


def test_the_hashed_source_runs_from_the_first_decorator_to_the_last_statement(tmp_path: Path) -> None:
    module = _load(tmp_path, DECORATED)
    ours = source_identity.object_source(DECORATED, "Database.price_bars")
    assert ours.startswith("    @deco(\n") and ours.rstrip().endswith("return x") and ours == _live(module)
    assert source_identity.object_source(DECORATED, "Database.price_bars_v2") == _live(module, "price_bars_v2")  # a name prefix is another name
    assert source_identity.object_sha256(DECORATED, "Database.price_bars") == hashlib.sha256(ours.encode("utf-8")).hexdigest()
    assert source_identity.object_source(DECORATED, "deco").startswith("def deco(")  # a module-level function


def test_a_nested_definition_of_the_same_name_is_part_of_its_parent_never_a_match(tmp_path: Path) -> None:
    text = '''
class Database:
    def price_bars(self):
        def price_bars():
            return 1
        return price_bars()

    def other(self):
        return 2
'''
    module = _load(tmp_path, text)
    ours = source_identity.object_source(text, "Database.price_bars")
    assert ours == _live(module) and "return price_bars()" in ours and "def other" not in ours


def test_a_comment_after_the_last_statement_is_not_hashed(tmp_path: Path) -> None:
    text = '''
class Database:
    def price_bars(self):
        return 1
        # a trailing comment inside the body

    def other(self):
        return 2
'''
    ours = source_identity.object_source(text, "Database.price_bars")
    assert ours == "    def price_bars(self):\n        return 1\n"  # what is hashed: the parser's positions (inspect.getsource on 3.12 keeps the comment)
    assert source_identity.object_sha256(text, "Database.price_bars") == source_identity.object_sha256(text.replace("        # a trailing comment inside the body\n", ""),
                                                                                                    "Database.price_bars")


@pytest.mark.parametrize("text, message", [
    ('''
class Database:
    def price_bars(self):
        return "first (never runs)"

    def price_bars(self):
        return "second (runs)"
''', "defined 2 times"),
    ('''
class Database:
    def price_bars(self):
        return "first class (shadowed)"


class Database:
    def price_bars(self):
        return "second class (runs)"
''', "defined 2 times"),
])
def test_a_name_defined_twice_is_refused_because_python_runs_the_last(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        source_identity.object_source(text, "Database.price_bars")
    with pytest.raises(ValueError, match=message):
        source_identity.objects_sha256(text, ["Database.price_bars"])


def test_what_cannot_be_reached_without_guessing_is_refused() -> None:
    conditional = '''
import sys
class Database:
    if sys.version_info >= (3, 0):
        def price_bars(self):
            return 1
'''
    with pytest.raises(KeyError):
        source_identity.object_source(conditional, "Database.price_bars")
    with pytest.raises(KeyError):
        source_identity.object_source(DECORATED, "Database.missing")
    with pytest.raises(KeyError, match="not a class"):
        source_identity.object_source(DECORATED, "deco.price_bars")
    with pytest.raises(KeyError, match="not a function"):
        source_identity.object_source(DECORATED, "Database")  # a class is never hashed as an object here


def test_several_objects_of_one_module_are_parsed_once_and_the_cli_prints_them(tmp_path: Path) -> None:
    names = ["Database.price_bars", "Database.price_bars_v2", "deco"]
    assert source_identity.objects_sha256(DECORATED, names) == {name: source_identity.object_sha256(DECORATED, name) for name in names}
    path = tmp_path / "database_text.py"
    path.write_text(DECORATED, encoding="utf-8")
    script = Path(source_identity.__file__)
    printed = subprocess.run([sys.executable, "-I", str(script), str(path), *names], capture_output=True, text=True, check=True).stdout
    assert json.loads(printed) == source_identity.objects_sha256(DECORATED, names)
