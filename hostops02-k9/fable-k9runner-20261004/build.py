"""Build k9_runner.py from src/k9_runner.readable.py by removing comments, blank lines, function/class docstrings and
whitespace between tokens, and indenting one space per level.

Proof printed by `python3 build.py check`: the compacted file has the same token sequence (types and strings, whitespace,
comment and docstring tokens aside) and the same AST (ast.dump) as the readable source without its function/class
docstrings (the module docstring is kept), is <= 40,960 bytes, and is byte-identical to a rebuild.
"""
import ast, hashlib, io, sys, tokenize
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE, TARGET, LIMIT = HERE / 'src' / 'k9_runner.readable.py', HERE / 'k9_runner.py', 40960
WORD = (tokenize.NAME, tokenize.NUMBER, tokenize.STRING)


def docstrings(tree):
    return [n.body[0] for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant) and isinstance(n.body[0].value.value, str)]


def without_docstrings(text):
    tree = ast.parse(text)
    for node in docstrings(tree):
        for parent in ast.walk(tree):
            if isinstance(getattr(parent, 'body', None), list) and parent.body and parent.body[0] is node:
                parent.body = parent.body[1:]
                assert parent.body, 'BODY_ONLY_DOCSTRING'
    return ast.dump(tree)


def compact(text):
    skip = {line for node in docstrings(ast.parse(text)) for line in range(node.lineno, node.end_lineno + 1)}
    lines = text.splitlines(True)
    out, row, prev = [], None, None
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type in (tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER, tokenize.COMMENT) or tok.start[0] in skip:
            continue
        if tok.type in (tokenize.NEWLINE, tokenize.NL):
            if row is not None:
                out.append('\n')
            row, prev = None, None
            continue
        if row != tok.start[0]:
            line = lines[tok.start[0] - 1]
            out.append(' ' * ((len(line) - len(line.lstrip(' '))) // 2))  # one space per level of the two-space source
            row = tok.start[0]
        elif prev is not None and prev.type in WORD and tok.type in WORD:
            out.append(' ')
        elif prev is not None and prev.type == tokenize.OP and tok.type == tokenize.OP and (prev.string + tok.string) in (
                '**', '//', '==', '<=', '>=', '!=', '->', '+=', '-=', '*=', '/=', '<<', '>>', ':=', '...', '..'):
            out.append(' ')
        out.append(tok.string)
        row = tok.end[0]
        prev = tok
    return ''.join(out)


def tokens(text, skip=()):
    return [(t.type, t.string) for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.start[0] not in skip
            and t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT)]


def build():
    text = SOURCE.read_text()
    result = compact(text)
    skip = {line for node in docstrings(ast.parse(text)) for line in range(node.lineno, node.end_lineno + 1)}
    assert tokens(result) == tokens(text, skip), 'TOKENS_DIFFER'
    assert ast.dump(ast.parse(result)) == without_docstrings(text), 'AST_DIFFERS'
    assert not docstrings(ast.parse(result)) and ast.get_docstring(ast.parse(result)) == ast.get_docstring(ast.parse(text))
    return result.encode()


if __name__ == '__main__':
    data = build()
    if sys.argv[1:] == ['check']:
        assert TARGET.read_bytes() == data, 'TARGET_NOT_THE_BUILD'
    else:
        TARGET.write_bytes(data)
    assert len(data) <= LIMIT, ('SIZE', len(data))
    print('BUILD_OK size=%d sha256=%s source_sha256=%s' % (len(data), hashlib.sha256(data).hexdigest(),
                                                           hashlib.sha256(SOURCE.read_bytes()).hexdigest()))
