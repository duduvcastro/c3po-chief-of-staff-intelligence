"""Candidate offline runtime identity guard. Only named, constant refusal codes leave it."""
import base64
import contextlib
import csv
import hashlib
import importlib
import importlib.machinery
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import stat
import sys
import sysconfig

SCHEMA = 'CODEX_BINDER_OPERATIVE_RUNTIME_IDENTITY_V1'
PYTHON_VERSION = '3.12.14'
CALENDAR_VERSION = '4.13.2'
BINDER_SHA256 = '9dbff222a3f815573d0cf89686f16a841260831400da40c5055999d7c71af133'
ACCEPTED_SHA256 = '78eb4ab25db448d677b5c54bb2f91346c194427fee88028260d1ba2f7be50d72'
IMPORTS = ('numpy', 'numpy.random', 'pandas', 'exchange_calendars', 'dateutil', 'six', 'pytz', 'tzdata',
           'pyluach', 'korean_lunar_calendar', 'toolz')
CYTHON_CREATORS = {'cython_runtime': 'numpy.random', '_cython_3_2_1': 'numpy.random', '_cython_3_0_11': 'pandas'}
CYTHON_PUBLIC_KEYS = {
    'cython_runtime': {'cline_in_traceback'},
    '_cython_3_2_1': {'_common_types_metatype', 'cython_function_or_method', 'generator'},
    '_cython_3_0_11': {'cython_function_or_method', 'fused_cython_function', 'generator'}}


class Refused(Exception):
    pass


def need(ok, code):
    if not ok:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def path_hash(path):
    return sha(os.fsencode(str(Path(path).resolve())))


def within(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def read_regular(path):
    """Do not follow a final link; compare the opened inode before and after reading."""
    path = Path(path)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            first = os.fstat(fd)
            need(stat.S_ISREG(first.st_mode), 'RUNTIME_NOT_REGULAR')
            chunks = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            last = os.fstat(fd)
            need((first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns,
                  first.st_ctime_ns) == (last.st_dev, last.st_ino, last.st_size,
                  last.st_mtime_ns, last.st_ctime_ns), 'RUNTIME_CHANGED_WHILE_READ')
            return b''.join(chunks)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        raise Refused('RUNTIME_FILE_UNAVAILABLE') from None


def inventory(root, *, omit_site_packages=False):
    """Pin every runtime byte, including unsigned RECORD entries and pre-existing pyc."""
    root = Path(root).resolve()
    result = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        if omit_site_packages:
            dirs[:] = [d for d in dirs if d not in ('site-packages', 'dist-packages')]
        for name in dirs:
            need(not Path(folder, name).is_symlink(), 'RUNTIME_DIRECTORY_LINK')
        for name in files:
            file = Path(folder, name)
            # venv executable links are separately bound to the exact resolved binary.
            if file.is_symlink():
                need(file.parent == root / 'bin' and name.startswith('python'),
                     'RUNTIME_UNAPPROVED_FILE_LINK')
                result[str(file.relative_to(root))] = {'link_target_sha256': path_hash(file)}
            else:
                result[str(file.relative_to(root))] = {'sha256': sha(read_regular(file))}
    need(bool(result), 'RUNTIME_EMPTY_INVENTORY')
    return result


def verify_record(site, dist):
    """RECORD bytes are externally pinned too; its own row is not a self-authentication."""
    site = Path(site).resolve()
    dist_root = Path(dist._path).resolve()
    need(within(dist_root, site), 'RUNTIME_DIST_OUTSIDE_VENV')
    record = dist_root / 'RECORD'
    raw = read_regular(record)
    seen = set()
    rows = 0
    absent_unsigned_bytecode = []
    try:
        for row in csv.reader(io.StringIO(raw.decode('utf-8'))):
            need(len(row) == 3, 'RUNTIME_RECORD_MALFORMED')
            name, digest, size = row
            target = (site / name).resolve()
            # Console entry scripts ../../../bin are legal only inside this same venv.
            venv = site.parents[2]
            need(name and name not in seen and within(target, venv),
                 'RUNTIME_RECORD_PATH')
            need(not (site / name).is_symlink(), 'RUNTIME_RECORD_LINK')
            seen.add(name)
            if digest:
                data = read_regular(target)
                algorithm, separator, encoded = digest.partition('=')
                need(separator and algorithm == 'sha256', 'RUNTIME_RECORD_ALGORITHM')
                want = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
                need(encoded == want, 'RUNTIME_RECORD_BYTES')
                need(size.isdigit() and int(size) == len(data), 'RUNTIME_RECORD_SIZE')
            else:
                need(size == '' and (target == record or target.suffix == '.pyc'),
                     'RUNTIME_RECORD_UNSIGNED')
                if target.suffix == '.pyc' and not target.exists():
                    absent_unsigned_bytecode.append(name)
                else:
                    read_regular(target)  # Existing unsigned pyc is pinned by the whole inventory.
            rows += 1
    except (UnicodeError, csv.Error):
        raise Refused('RUNTIME_RECORD_MALFORMED') from None
    need(rows > 0 and str(record.relative_to(site)) in seen, 'RUNTIME_RECORD_SELF_ABSENT')
    return {'record_sha256': sha(raw), 'rows': rows,
            'dist_info': str(dist_root.relative_to(site)), 'version': dist.version,
            'name': dist.metadata['Name'],
            'absent_unsigned_bytecode': sorted(absent_unsigned_bytecode)}


def calendar_module_identity(module):
    version = getattr(module, '__version__', None)
    need(type(version) is str and version == CALENDAR_VERSION,
         'RUNTIME_CALENDAR_MODULE_VERSION')
    return version


def python_support_libraries(base):
    """Pin CPython's shared interpreter library too, when it is not part of the executable."""
    base = Path(base).resolve()
    files = sorted(set((base/'lib').glob('libpython*.so*')) |
                   set((base/'lib').glob('libpython*.dylib')) |
                   ({base/'Python'} if (base/'Python').exists() else set()))
    shared = bool(sysconfig.get_config_var('Py_ENABLE_SHARED') or
                  sysconfig.get_config_var('PYTHONFRAMEWORK'))
    need(bool(files) or not shared, 'RUNTIME_PYTHON_SHARED_LIBRARY_MISSING')
    out = {}
    for file in files:
        real = file.resolve()
        need(within(real, base), 'RUNTIME_PYTHON_SHARED_LIBRARY_OUTSIDE_BASE')
        out['S/CPYTHON/'+str(file.relative_to(base))] = {
            'realpath_sha256': path_hash(real), 'sha256': sha(read_regular(real))}
    return out


def structural_check(root):
    """No site initialization, path/environment fallback, .pth or inherited packages."""
    root = Path(root).resolve()
    need(sys.platform == 'linux' and os.geteuid() != 0, 'RUNTIME_LINUX_NONROOT')
    venv = root / 'venv'
    need(platform.python_implementation() == 'CPython' and
         platform.python_version() == PYTHON_VERSION, 'RUNTIME_INTERPRETER_VERSION')
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,
         'RUNTIME_STARTUP_NOT_ISOLATED')
    need(sys.pycache_prefix is not None, 'RUNTIME_CACHE_PREFIX_REQUIRED')
    cache = Path(sys.pycache_prefix)
    need(cache.is_dir() and not cache.is_symlink() and not list(cache.iterdir()),
         'RUNTIME_CACHE_PREFIX_NOT_EMPTY')
    need(Path(sys.executable).absolute() == venv / 'bin' / 'python',
         'RUNTIME_EXECUTABLE_SLOT')
    cfg = read_regular(venv / 'pyvenv.cfg').decode('utf-8')
    fields = {}
    for line in cfg.splitlines():
        key, sep, value = line.partition('=')
        if sep:
            need(key.strip() not in fields, 'RUNTIME_VENV_CONFIG_DUPLICATE')
            fields[key.strip()] = value.strip()
    need(fields.get('include-system-site-packages', '').lower() == 'false',
         'RUNTIME_SYSTEM_SITE_PACKAGES')
    site = venv / 'lib' / 'python3.12' / 'site-packages'
    need(site.is_dir() and not site.is_symlink(), 'RUNTIME_SITE_MISSING')
    for p in site.rglob('*'):
        need(not p.is_symlink(), 'RUNTIME_SITE_LINK')
        need(not (p.suffix == '.pth' or p.name in ('sitecustomize.py', 'usercustomize.py')),
             'RUNTIME_STARTUP_HOOK')
    # Python3.12 -S deliberately does not adopt venv sys.prefix. Its base stdlib is legitimate.
    stdlib = Path(sysconfig.get_path('stdlib')).resolve()
    base = Path(sys.base_prefix).resolve()
    need(within(stdlib, base), 'RUNTIME_STDLIB_OUTSIDE_BASE')
    bootstrap_paths(stdlib, base)
    return venv, site, stdlib, base


def bootstrap_paths(stdlib, base, site=None):
    """Exact startup slots; the zip slot is pinned ABSENT or by its complete bytes."""
    stdlib, base = Path(stdlib).resolve(), Path(base).resolve()
    slots = [stdlib.parent/'python312.zip', stdlib, stdlib/'lib-dynload']
    expected = slots + ([Path(site).resolve()] if site is not None else [])
    need([str(Path(p).absolute()) for p in sys.path] == [str(p) for p in expected],
         'RUNTIME_BOOTSTRAP_SEARCH_PATH')
    result = []
    for index, path in enumerate(slots):
        need(within(path, base) and not path.is_symlink(), 'RUNTIME_BOOTSTRAP_SLOT_LINK')
        row = {'slot': index, 'role': 'S/CPYTHON/'+str(path.relative_to(base)),
               'path_sha256': path_hash(path)}
        if index == 0:
            if path.exists():
                row.update(kind='FILE', sha256=sha(read_regular(path)))
            else:
                row['kind'] = 'ABSENT'
        else:
            need(path.is_dir(), 'RUNTIME_BOOTSTRAP_DIRECTORY_MISSING')
            row['kind'] = 'DIRECTORY_IN_STDLIB_INVENTORY'
        result.append(row)
    return result


def virtual_origin(name, module, site, stdlib, producers):
    """Six exact reviewed virtual names. Every factory remains a separately pinned real origin."""
    if name in ('typing.io', 'typing.re'):
        owner = sys.modules.get('typing')
        need(owner is not None and getattr(owner, name.split('.')[1], None) is module
             and type(module).__module__ == 'typing'
             and within(getattr(owner, '__file__', '/unapproved'), stdlib),
             'RUNTIME_TYPING_ALIAS_PROVENANCE')
        return 'S/CPYTHON/stdlib/typing.py::' + name
    if name == 'six.moves':
        owner = sys.modules.get('six')
        loader = getattr(module, '__loader__', None)
        need(owner is not None and getattr(owner, 'moves', None) is module
             and getattr(owner, '_importer', None) is loader
             and type(loader).__module__ == 'six' and type(loader).__name__ == '_SixMetaPathImporter'
             and type(module).__module__ == 'six' and type(module).__name__ == '_MovedItems'
             and within(getattr(owner, '__file__', '/unapproved'), site),
             'RUNTIME_SIX_ALIAS_PROVENANCE')
        return 'W/venv/site-packages/six.py::six.moves'
    if name in CYTHON_CREATORS:
        owner = CYTHON_CREATORS[name]
        factory = sys.modules.get(owner)
        need(producers.get(name) == owner and factory is not None
             and within(getattr(factory, '__file__', '/unapproved'), site)
             and type(module).__name__ == 'module' and module.__name__ == name
             and getattr(module, '__spec__', None) is None
             and getattr(module, '__loader__', None) is None
             and {k for k in vars(module) if not k.startswith('__')} == CYTHON_PUBLIC_KEYS[name],
             'RUNTIME_CYTHON_ALIAS_PROVENANCE')
        extensions = []
        for loaded_name, loaded in tuple(sys.modules.items()):
            spec = getattr(loaded, '__spec__', None)
            origin = getattr(spec, 'origin', None)
            if loaded_name.startswith(owner+'.') and isinstance(
                    getattr(spec, 'loader', None), importlib.machinery.ExtensionFileLoader):
                need(origin and within(origin, site), 'RUNTIME_CYTHON_EXTENSION_OUTSIDE_VENV')
                extensions.append(loaded_name)
        need(bool(extensions), 'RUNTIME_CYTHON_PRODUCER_EXTENSION_ABSENT')
        return 'W/venv/generated-by-' + owner + '::' + name
    return None


def audit_modules(site, stdlib, base, trusted_source_files=(), virtual_producers=None):
    """Base stdlib is allowed; third-party loaded origins and namespace locations are not."""
    site, stdlib, base = (Path(root).resolve() for root in (site, stdlib, base))
    trusted = {str(Path(p).resolve()) for p in trusted_source_files}
    # Generated CPython build-data module has a platform-specific name not in stdlib_module_names.
    stdlib_names = set(sys.stdlib_module_names) | {sysconfig._get_sysconfigdata_name()}
    origins = {}
    for name, module in tuple(sys.modules.items()):
        if module is None or name == '__main__':
            continue
        spec = getattr(module, '__spec__', None)
        origin = getattr(spec, 'origin', None) or getattr(module, '__file__', None)
        if origin in ('built-in', 'frozen'):
            need(name.split('.')[0] in sys.stdlib_module_names or name in sys.builtin_module_names,
                 'RUNTIME_FORGED_BUILTIN_ORIGIN')
            origins[name] = 'S/CPYTHON/' + origin
            continue
        if origin is None:
            virtual = virtual_origin(name, module, site, stdlib, virtual_producers or {})
            if virtual is not None:
                origins[name] = virtual
                continue
            locations = getattr(spec, 'submodule_search_locations', None)
            need(locations is not None and bool(list(locations)) and
                 all(within(p, site) for p in locations), 'RUNTIME_MODULE_NO_APPROVED_ORIGIN')
            origins[name] = 'W/venv/namespace'
        else:
            real = Path(origin).resolve()
            if within(real, site):
                origins[name] = 'W/venv/site-packages/' + str(real.relative_to(site))
            elif within(real, stdlib) and 'site-packages' not in real.parts and 'dist-packages' not in real.parts:
                need(name.split('.')[0] in stdlib_names, 'RUNTIME_THIRDPARTY_IN_STDLIB')
                origins[name] = 'S/CPYTHON/stdlib/' + str(real.relative_to(stdlib))
            elif str(real) in trusted:
                origins[name] = 'W/binder/runtime-guard'
            else:
                raise Refused('RUNTIME_MODULE_OUTSIDE_APPROVED_ROOTS')
    return origins


def observe(root, trusted_source_files=(), expected=None):
    venv, site, stdlib, base = structural_check(root)
    bootstrap = bootstrap_paths(stdlib, base)
    # No metadata import through system site-packages: exactly one approved venv location.
    sys.path.append(str(site))
    distributions = sorted(importlib.metadata.distributions(path=[str(site)]),
                           key=lambda d: d.metadata['Name'].lower().replace('_', '-'))
    dist_rows = [verify_record(site, d) for d in distributions]
    names = [r['name'].lower().replace('_', '-') for r in dist_rows]
    need(len(set(names)) == len(names), 'RUNTIME_DUPLICATE_DISTRIBUTION')
    need(any(r['name'].lower().replace('_', '-') == 'exchange-calendars' and
             r['version'] == CALENDAR_VERSION for r in dist_rows), 'RUNTIME_CALENDAR_VERSION')
    venv_files = inventory(venv)
    stdlib_files = inventory(stdlib, omit_site_packages=True)
    executable = Path(sys.executable).resolve()
    identity = {'schema': SCHEMA, 'python_version': platform.python_version(),
                'implementation': 'CPython', 'calendar_version': CALENDAR_VERSION,
                'venv_path_sha256': path_hash(venv), 'base_path_sha256': path_hash(base),
                'executable_realpath_sha256': path_hash(executable),
                'executable_sha256': sha(read_regular(executable)),
                'bootstrap_search_paths': bootstrap,
                'python_support_libraries': python_support_libraries(base),
                'venv_files': venv_files, 'stdlib_files': stdlib_files,
                'distributions': dist_rows, 'dependency_imports': list(IMPORTS),
                'binder_sha256': BINDER_SHA256, 'accepted_seals_sha256': ACCEPTED_SHA256,
                'stdlib_is_base_not_thirdparty': True,
                'child_interpreters': 'CANDIDATE_LITERAL_SYSTEM_CHILDREN_SEPARATE_NOT_THIS_GATE'}
    if expected is not None:
        # Check package bytes/RECORD/version pins before any third-party code is imported.
        need(expected.get('schema') == SCHEMA, 'RUNTIME_IDENTITY_SCHEMA')
        need(all(expected.get(key) == value for key, value in identity.items()),
             'RUNTIME_IDENTITY_MISMATCH')
    output, errors = io.StringIO(), io.StringIO()
    virtual_producers = {}
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            for module in IMPORTS:
                before = set(sys.modules)
                importlib.import_module(module)
                for name in set(sys.modules)-before:
                    if name in CYTHON_CREATORS:
                        need(CYTHON_CREATORS[name] == module, 'RUNTIME_CYTHON_IMPORT_FACTORY')
                        virtual_producers[name] = module
    except Refused:
        raise
    except Exception:
        raise Refused('RUNTIME_DEPENDENCY_IMPORT_FAILED') from None
    need(not output.getvalue() and not errors.getvalue(), 'RUNTIME_DEPENDENCY_IMPORT_OUTPUT')
    calendar_module_version = calendar_module_identity(sys.modules['exchange_calendars'])
    origins = audit_modules(site, stdlib, base, trusted_source_files, virtual_producers)
    need(inventory(venv) == venv_files and inventory(stdlib, omit_site_packages=True) == stdlib_files,
         'RUNTIME_CHANGED_DURING_IMPORT')
    need(python_support_libraries(base) == identity['python_support_libraries'],
         'RUNTIME_PYTHON_SHARED_LIBRARY_CHANGED')
    need(bootstrap_paths(stdlib, base, site) == bootstrap, 'RUNTIME_BOOTSTRAP_SLOTS_CHANGED')
    identity['module_origins'] = origins
    identity['calendar_module_version'] = calendar_module_version
    identity['virtual_producers'] = virtual_producers
    return identity


def compare(expected, actual):
    """Compare an externally reviewed measurement. Never update a pin or infer acceptance."""
    need(expected.get('schema') == SCHEMA, 'RUNTIME_IDENTITY_SCHEMA')
    for key in ('python_version', 'implementation', 'calendar_version', 'venv_path_sha256',
                'base_path_sha256', 'executable_realpath_sha256', 'executable_sha256',
                'python_support_libraries',
                'bootstrap_search_paths',
                'venv_files', 'stdlib_files', 'distributions', 'dependency_imports',
                'binder_sha256', 'accepted_seals_sha256', 'stdlib_is_base_not_thirdparty',
                'child_interpreters', 'calendar_module_version', 'virtual_producers'):
        need(expected.get(key) == actual.get(key), 'RUNTIME_IDENTITY_MISMATCH')
    # Guard/measurement imports differ. Every loaded origin is still individually approved above.
    expected_modules = expected.get('module_origins', {})
    need(all(expected_modules.get(n) == p for n, p in actual['module_origins'].items()),
         'RUNTIME_MODULE_ORIGIN_MISMATCH')
    return {'status': 'VERIFIED_RUNTIME', 'python_version': PYTHON_VERSION,
            'calendar_version': CALENDAR_VERSION,
            'distributions': len(actual['distributions']),
            'venv_files': len(actual['venv_files']), 'stdlib_files': len(actual['stdlib_files']),
            'loaded_modules': len(actual['module_origins']),
            'binder_sha256': BINDER_SHA256, 'accepted_seals_sha256': ACCEPTED_SHA256,
            'host_proof': False}
