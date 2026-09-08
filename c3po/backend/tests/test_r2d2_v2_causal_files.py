"""Counterexamples for exclusive private publication, without network/DB."""
from pathlib import Path
import os

import pytest

from app.r2d2_v2_causal_files import _atomic_bytes, FileRelaySink, write_private_envelope
from app.r2d2_v2_causal_emitter import _public
from app.r2d2_v2_store import ShadowIntegrityError
from test_r2d2_v2_causal_emitter import receipt_fixture


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "private"
    path.mkdir(mode=0o700)
    return path


def test_identical_retry_keeps_original_inode_and_content(root):
    ref = _atomic_bytes(root, ("sub", "receipt.json"), b"original")
    target = root / ref
    before = target.stat()
    assert _atomic_bytes(root, ("sub", "receipt.json"), b"original") == ref
    assert target.stat().st_ino == before.st_ino and target.read_bytes() == b"original"
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.parent.stat().st_mode & 0o777 == 0o700
    assert target.stat().st_nlink == 1
    assert not list(target.parent.glob(".causal-*"))


def test_conflict_preserves_original(root):
    _atomic_bytes(root, ("receipt.json",), b"old")
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_FILE_CONFLICT"):
        _atomic_bytes(root, ("receipt.json",), b"new")
    assert (root / "receipt.json").read_bytes() == b"old"


@pytest.mark.parametrize("parts", [("..", "x"), ("sub/foreign", "x"), ("../x",), (".",), ()])
def test_traversal_or_empty_path_rejected(root, parts):
    with pytest.raises(ShadowIntegrityError):
        _atomic_bytes(root, parts, b"x")


@pytest.mark.parametrize("location", ["root", "parent", "file"])
def test_symlinks_never_followed(root, tmp_path, location):
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    if location == "root":
        alias = tmp_path / "alias"
        alias.symlink_to(root)
        root = alias
        parts = ("x",)
    elif location == "parent":
        (root / "link").symlink_to(outside)
        parts = ("link", "x")
    else:
        (outside / "original").write_bytes(b"x")
        (root / "x").symlink_to(outside / "original")
        parts = ("x",)
    with pytest.raises(OSError):
        _atomic_bytes(root, parts, b"x")
    assert not (outside / "x").exists()


@pytest.mark.parametrize("location", ["root", "parent", "file"])
def test_non_private_existing_paths_rejected(root, location):
    parts = ("sub", "x")
    (root / "sub").mkdir(mode=0o700)
    (root / "sub" / "x").write_bytes(b"x")
    (root / "sub" / "x").chmod(0o600)
    target = root if location == "root" else root / "sub" if location == "parent" else root / "sub" / "x"
    target.chmod(0o755 if location != "file" else 0o644)
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_FILE_NOT_PRIVATE"):
        _atomic_bytes(root, parts, b"x")


def test_existing_hardlink_rejected(root):
    (root / "x").write_bytes(b"x")
    (root / "x").chmod(0o600)
    os.link(root / "x", root / "alias")
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_FILE_HARDLINK"):
        _atomic_bytes(root, ("x",), b"x")


def test_relay_receipt_and_private_envelope_are_separate(root, tmp_path):
    commitment, audit, publication = receipt_fixture()
    public = _public(commitment, audit)
    channel, ref = FileRelaySink(root)(public)
    assert channel == "relay" and ref.startswith("causal_publications/")
    assert "PRIVATE" not in (root / ref).read_text()
    spool = tmp_path / "spool"
    spool.mkdir(mode=0o700)
    envelope = {"commitment": commitment, "audit_receipt": audit, "publication_receipt": publication}
    private_ref = write_private_envelope(spool, envelope)
    assert private_ref.startswith("causal_list/")
    assert "PRIVATE" in (spool / private_ref).read_text()
    assert write_private_envelope(spool, envelope) == private_ref


def test_sink_rejects_added_private_field(root):
    commitment, audit, _ = receipt_fixture()
    public = _public(commitment, audit)
    public["registry_raw_base64"] = "PRIVATE"
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_PUBLIC_FIELDS"):
        FileRelaySink(root)(public)
    assert list(root.iterdir()) == []
