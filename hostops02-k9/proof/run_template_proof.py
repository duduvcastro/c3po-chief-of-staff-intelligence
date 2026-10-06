#!/usr/bin/env python3
"""Offline literal Go proof; unavailable Go is NOT_RUN and a nonzero mandatory gate.

Inputs are verified and consumed from the same buffers. Only environment_format is
called; no Docker, operational command, network, installation, or host action.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import types

PASS = 'PASS_LITERAL_DOCKER_ENV_TEMPLATE'
EXPECTED_COMPARISONS = 46
NAMES = (
    'C3PO_BUILD_SHA',
    'C3PO_R2D2_V2_LIVE_POLICY_FILE',
    'C3PO_R2D2_V2_LIVE_POLICY_SHA',
    'C3PO_R2D2_V2_SHADOW_RELEASE_FILE',
    'C3PO_R2D2_V2_SHADOW_RELEASE_SHA',
)
CANARY = 'UNAPPROVED_SYNTHETIC_CANARY_X7=a=b'
class ProofFailure(ValueError): pass

def sha(raw): return hashlib.sha256(raw).hexdigest()
def require(ok, code):
    if not ok: raise ProofFailure(code)
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def pinned_buffer(path, pin, code):
    require(isinstance(pin, str) and re.fullmatch('[0-9a-f]{64}', pin) is not None, code + '_PIN_INVALID')
    raw = Path(path).read_bytes()
    require(sha(raw) == pin, code + '_PIN_MISMATCH')
    return raw

def load_formatter(raw):
    name = '_offline_literal_environment_template_source'
    module = types.ModuleType(name)
    # Dataclass resolution needs the module registered while its same pinned buffer is compiled.
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(raw, 'PINNED_BOOTSTRAP_SOURCE', 'exec'), module.__dict__)
        require(callable(module.__dict__.get('environment_format')), 'FORMATTER_NOT_FOUND')
        return module.environment_format
    finally:
        if previous is None: sys.modules.pop(name, None)
        else: sys.modules[name] = previous

def cases():
    expected = dict(zip(NAMES, ('a' * 40, '/app/config/policy.json', 'b' * 64,
                              '/app/data/release.json', 'c' * 64)))
    base = [key + '=' + expected[key] for key in NAMES]
    normal = {key: {'present': True, 'equal': True} for key in NAMES}
    result = [('positive_five', expected, base, normal)]
    for family in ('missing', 'wrong', 'duplicate_identical', 'duplicate_divergent'):
        for key in NAMES:
            env = list(base)
            wanted = {name: dict(item) for name, item in normal.items()}
            if family == 'missing':
                env.remove(key + '=' + expected[key]); wanted[key] = {'present': False, 'equal': False}
            elif family == 'wrong':
                env[env.index(key + '=' + expected[key])] = key + '=WRONG_SYNTHETIC_VALUE'
                wanted[key]['equal'] = False
            else:
                value = expected[key] if family == 'duplicate_identical' else 'WRONG_SYNTHETIC_VALUE'
                env.append(key + '=' + value); wanted[key]['equal'] = False
            result.append((family + ':' + key, expected, env, wanted))
    result.append(('unapproved_canary', expected, base + ['SECRET=' + CANARY], normal))
    with_equals = dict(expected); with_equals[NAMES[1]] = '/app/config=equal/policy.json'
    env = [key + '=' + with_equals[key] for key in NAMES]
    result.append(('approved_value_with_equals', with_equals, env, normal))
    require(len(result) == 23, 'CASE_COUNT_INTERNAL')
    return result

def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'OUTPUT_DUPLICATE_KEY')
            result[key] = value
        return result
    def nonfinite(_): raise ProofFailure('OUTPUT_NONFINITE')
    try: return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    except ProofFailure: raise
    except (ValueError, UnicodeError): raise ProofFailure('OUTPUT_NOT_JSON') from None

def check_output(raw, expected):
    require(len(raw) <= 16384, 'OUTPUT_TOO_LARGE')
    require(CANARY.encode() not in raw, 'OUTPUT_CANARY_LEAK')
    value = strict_json(raw)
    require(type(value) is dict and set(value) == set(NAMES), 'OUTPUT_NAMES')
    require(all(type(item) is dict and set(item) == {'present', 'equal'} and
                type(item['present']) is bool and type(item['equal']) is bool
                for item in value.values()), 'OUTPUT_SHAPE')
    require(value == expected, 'LITERAL_COMPARISON_FAILED')

def safe_run(runner, command, **kwargs):
    try: return runner(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False, **kwargs)
    except subprocess.TimeoutExpired: raise ProofFailure('SUBPROCESS_TIMEOUT') from None
    except OSError: raise ProofFailure('SUBPROCESS_UNAVAILABLE') from None

def prove(args, locator=shutil.which, runner=subprocess.run):
    result = {'schema': 1, 'status': 'FAIL_LITERAL_DOCKER_ENV_TEMPLATE',
              'comparisons': 0, 'comparisons_expected': EXPECTED_COMPARISONS,
              'failures': 0, 'omissions': 0, 'source_sha256': args.source_sha256,
              'driver_sha256': args.driver_sha256, 'source_before_after_equal': False,
              'driver_before_after_equal': False, 'mode_counts': {'typed': 0, 'raw': 0},
              'scope': 'STANDARD_GO_TEXT_TEMPLATE_ONLY_NOT_DOCKER_DAEMON_HOST_OR_GATES'}
    code = 1
    output = Path(args.output)
    require(not output.exists(), 'OUTPUT_ALREADY_EXISTS')
    output.mkdir(mode=0o700, parents=True)
    try:
        source = pinned_buffer(args.source, args.source_sha256, 'SOURCE')
        driver = pinned_buffer(args.driver, args.driver_sha256, 'DRIVER')
        formatter = load_formatter(source)
        go = locator('go')
        if not go:
            result['status'] = 'NOT_RUN_GO_UNAVAILABLE'
            result['reason'] = 'GO_REQUIRED_NO_FALLBACK_NO_INSTALL'
            code = 2
        else:
            require(Path(go).is_file(), 'GO_EXECUTABLE_UNAVAILABLE')
            result['go_executable_sha256'] = sha(Path(go).read_bytes())
            with tempfile.TemporaryDirectory(prefix='literal-go-template-') as temp:
                temp = Path(temp)
                driver_copy = temp / 'environment_template_driver.go'
                driver_copy.write_bytes(driver)
                binary = temp / 'environment_template_driver'
                cache = temp / 'cache'; cache.mkdir(mode=0o700)
                env = os.environ.copy()
                env.update({'GOPROXY': 'off', 'GOSUMDB': 'off', 'GOWORK': 'off',
                            'GOTOOLCHAIN': 'local', 'GO111MODULE': 'off', 'CGO_ENABLED': '0',
                            'GOCACHE': str(cache), 'GOENV': 'off', 'GOFLAGS': '', 'GOTMPDIR': str(temp)})
                for key in ('GOOS', 'GOARCH', 'GOEXPERIMENT', 'GOROOT', 'GOTOOLDIR'):
                    env.pop(key, None)
                # No module or external package is used; toolchain downloading is prohibited.
                observed = safe_run(runner, [go, 'version'], env=env, cwd=str(temp))
                (output / 'GO_VERSION.stdout.txt').write_bytes(observed.stdout)
                (output / 'GO_VERSION.stderr.txt').write_bytes(observed.stderr)
                require(observed.returncode == 0 and not observed.stderr and len(observed.stdout) < 4096, 'GO_VERSION_FAILED')
                version = observed.stdout.decode('ascii').strip()
                require(re.fullmatch(r'go version go[0-9][A-Za-z0-9.+-]* [a-z0-9_]+/[a-z0-9_]+', version) is not None, 'GO_VERSION_FORMAT')
                result['go_version'] = version
                built = safe_run(runner, [go, 'build', '-trimpath', '-o', str(binary), str(driver_copy)], env=env, cwd=str(temp))
                (output / 'GO_BUILD.stdout.txt').write_bytes(built.stdout)
                (output / 'GO_BUILD.stderr.txt').write_bytes(built.stderr)
                require(built.returncode == 0, 'GO_BUILD_FAILED')
                require(not built.stdout and not built.stderr, 'GO_BUILD_UNEXPECTED_OUTPUT')
                require(binary.is_file(), 'GO_BINARY_MISSING')
                result['driver_binary_sha256'] = sha(binary.read_bytes())
                require(driver_copy.read_bytes() == driver, 'DRIVER_COMPILE_BUFFER_CHANGED')
                logs = []
                for mode in ('typed', 'raw'):
                    for name, expected, env_values, wanted in cases():
                        template = formatter(dict(expected))
                        require(type(template) is str and len(template.encode()) <= 32000, 'FORMATTER_OUTPUT')
                        payload = canonical({'template': template, 'env': env_values})
                        ran = safe_run(runner, [str(binary), '--mode', mode], input=payload, env=env, cwd=str(temp))
                        row = {'mode': mode, 'case': name, 'exit': ran.returncode,
                               'stdout_sha256': sha(ran.stdout), 'stderr_sha256': sha(ran.stderr)}
                        logs.append(row)
                        (output / 'COMPARISONS.json').write_bytes(canonical(logs) + b'\n')
                        # Preserve exact emitted bytes, including a concrete unexpected output or leak.
                        stem = mode + '-' + str(len(logs)).zfill(2)
                        (output / (stem + '.stdout.txt')).write_bytes(ran.stdout)
                        (output / (stem + '.stderr.txt')).write_bytes(ran.stderr)
                        require(ran.returncode == 0, 'LITERAL_DRIVER_FAILED')
                        require(not ran.stderr, 'LITERAL_DRIVER_STDERR')
                        check_output(ran.stdout, wanted)
                        result['comparisons'] += 1; result['mode_counts'][mode] += 1
                (output / 'COMPARISONS.json').write_bytes(canonical(logs) + b'\n')
                require(result['comparisons'] == EXPECTED_COMPARISONS and result['mode_counts'] == {'typed': 23, 'raw': 23}, 'COMPARISON_COUNT')
                result['status'] = PASS; code = 0
    except (ProofFailure, OSError, UnicodeError) as error:
        result['failures'] = 1
        result['reason'] = str(error) if isinstance(error, ProofFailure) else 'INPUT_OR_OUTPUT_UNAVAILABLE'
    except Exception as error:
        result['failures'] = 1
        result['reason'] = 'PURE_PROOF_EXCEPTION'
        result['exception_type'] = type(error).__name__
    finally:
        # Input failure and runtime failure still record immutable-input comparison; no PASS if either changed.
        try: result['source_before_after_equal'] = sha(Path(args.source).read_bytes()) == args.source_sha256
        except OSError: pass
        try: result['driver_before_after_equal'] = sha(Path(args.driver).read_bytes()) == args.driver_sha256
        except OSError: pass
        if code == 0 and not (result['source_before_after_equal'] and result['driver_before_after_equal']):
            result['status'] = 'FAIL_LITERAL_DOCKER_ENV_TEMPLATE'; result['reason'] = 'INPUT_CHANGED'; result['failures'] = 1; code = 1
        (output / 'RESULT.json').write_bytes(canonical(result) + b'\n')
    return result, code

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--driver', required=True)
    parser.add_argument('--driver-sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try: result, code = prove(args)
    except (ProofFailure, OSError) as error:
        reason = str(error) if isinstance(error, ProofFailure) else 'OUTPUT_UNAVAILABLE'
        result, code = {'schema': 1, 'status': 'FAIL_LITERAL_DOCKER_ENV_TEMPLATE', 'reason': reason,
                        'comparisons': 0, 'comparisons_expected': EXPECTED_COMPARISONS, 'failures': 1, 'omissions': 0}, 1
    print(canonical(result).decode())
    return code
if __name__ == '__main__': sys.exit(main())
