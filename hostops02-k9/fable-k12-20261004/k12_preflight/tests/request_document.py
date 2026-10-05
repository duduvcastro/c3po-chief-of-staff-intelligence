"""request_document() of the documents tool, copied byte for byte (the function only) from
S/opsart/c3po/deployment/capacity-day/capacity_day_documents.py, sha256 888a48e6654aff90e2f305b410ea6c5614485e5ac778354ba721b790bfead183
(the tool the signed Act B names). The function's own text has sha256 10108e7c721a138a8ad099fa70cd4bd42ffff5370007cb482226f1f793cd6350 (FUNCTION_SHA256, pinned
below and by tests/test_static_k12.py when the tool is present). The K12 fixtures build every capacity REQUEST with it,
so that the families accept exactly what the tool writes. It is pure: it reads a.EPOCH and the three constants below,
which are the tool's own values."""
REQUEST_SCHEMA = 'R2D2_CAPACITY_DAY_ONCE_REQUEST_V1'
OPERATION = 'GO_CAPACITY_DAY_03'
WATCHDOG_MARGIN_SECONDS = 90
FUNCTION_SHA256 = '10108e7c721a138a8ad099fa70cd4bd42ffff5370007cb482226f1f793cd6350'
TOOL_SHA256 = '888a48e6654aff90e2f305b410ea6c5614485e5ac778354ba721b790bfead183'


def request_document(a, *, day, window, index, count, view_mode, d, release_sha, package_sha, config_path,
                     config_sha, max_wait, start, observed, until, cutoff, documentary):
    """The dispatch REQUEST. Every argument is an ISO instant, a hash, a path or a constant."""
    argv = ['--day', day, '--manifest-directory', d['manifest_directory'], '--prepare-first',
            '--view-opens-at', observed, '--max-wait-seconds', str(max_wait)]
    if d['writer_require_go_mode'] != 'NOT_REQUIRED':
        argv += ['--require-go-mode', d['writer_require_go_mode']]
    return {'schema': REQUEST_SCHEMA, 'status': 'BOUND', 'operation': OPERATION, 'epoch': a.EPOCH, 'day': day,
            'window': window, 'window_index': index, 'window_count': count,
            'phases': ['admission', 'bar_manifest'], 'mode': 'PREPARE_AND_PUBLISH', 'view_mode': view_mode,
            'image_id': d['image_id'], 'build_sha': d['build_sha'], 'release_sha256': release_sha,
            'package_sha256': package_sha, 'capacity_config_file': config_path,
            'capacity_config_sha256': config_sha, 'network': d['network'], 'mounts': d['mounts'],
            'env_files': {'secret_path': d['secret_env_path'], 'pins': dict(d['pins_env'])},
            'inline_env': {'C3PO_R2D2_V2_SHADOW_ENABLED': 'true', 'C3PO_R2D2_V2_MASSIVE_BARS_ENABLED': 'true',
                           'C3PO_R2D2_V2_CAPACITY_CONFIG_FILE': config_path,
                           'C3PO_R2D2_V2_CAPACITY_CONFIG_SHA': config_sha},
            'docker_config': d['docker_config'], 'writer_sha256': d['writer_sha256'], 'writer_argv': argv,
            'transport_watchdog_seconds': max_wait + WATCHDOG_MARGIN_SECONDS,
            'not_before': start, 'latest_start': observed, 'not_after': until, 'view_opens_at': observed,
            'view_valid_until': until, 'cutoff_at': cutoff, 'documentary': documentary,
            'authority_sha256': d['authority_sha256'], 'host_binding_sha256': d['host_binding_sha256'],
            'executor_uid': 0}
