"""Fixtures of the bind_once tests: scratch copies of the two sealed families, made once per session and never changed."""
import sys

import pytest

import helpers as h


@pytest.fixture(scope='session')
def families(tmp_path_factory):
    root = h.resolved(tmp_path_factory.mktemp('families'))
    for source in (h.W1_SOURCE, h.HOSTOPS_SOURCE):
        assert (source / 'SHA256SUMS').is_file(), 'sealed family not found: set BIND_TEST_W1 / BIND_TEST_HOSTOPS'
    return {'w1': h.copy_family(h.W1_SOURCE, root / 'w1'), 'hostops': h.copy_family(h.HOSTOPS_SOURCE, root / 'hostops')}


@pytest.fixture
def base(tmp_path):
    return h.resolved(tmp_path)


@pytest.fixture(scope='session')
def w1_harness(families):
    """The candidate's own test module: its emulated host is the local harness of the W1 family."""
    return h.load_module('w1_candidate_tests_as_harness', families['w1'] / 'test_w1_preflight_once.py')


@pytest.fixture(scope='session')
def hostops_harness(families):
    """tests/family.py and tests/hostemu.py of HOSTOPS01: fixtures and the emulated host of that family."""
    directory = str(families['hostops'] / 'tests')
    sys.path.insert(0, directory)
    try:
        import family
        import hostemu
    finally:
        sys.path.remove(directory)
    return family, hostemu


def pytest_collection_modifyitems(session, config, items):
    """The test that compares the refusal codes of the binder with the codes exercised runs last."""
    last = [item for item in items if item.name.startswith('test_zz_')]
    items[:] = [item for item in items if not item.name.startswith('test_zz_')] + last
