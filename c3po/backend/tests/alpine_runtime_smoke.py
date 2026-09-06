"""Backend image runtime check (Alpine); never run in a production container.

Origin: Codex audit package for PR #379 (alpine_runtime_smoke.py); only the
expected-head pin was replaced by the CI-supplied environment variable.

Run only in a disposable Docker container with --network none, no credentials,
and no production mounts. This script was prepared and syntax-compiled locally;
that preparation is NOT a successful Alpine runtime check.
"""
import asyncio
import datetime as dt
import importlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import sys
from zoneinfo import ZoneInfo

# The expected source head is supplied by the CI step (C3PO_SMOKE_SOURCE_HEAD)
# so this file never pins a commit of its own repository.
EXPECTED_HEAD = os.environ.get("C3PO_SMOKE_SOURCE_HEAD", "")
NATIVE_MODULES = {
    "PyYAML": "yaml._yaml",
    "aiohttp": "aiohttp._http_parser",
    "cffi": "_cffi_backend",
    "charset-normalizer": "charset_normalizer.md",
    "cryptography": "cryptography.hazmat.bindings._rust",
    "curl_cffi": "curl_cffi._wrapper",
    "frozenlist": "frozenlist._frozenlist",
    "httptools": "httptools.parser.parser",
    "multidict": "multidict._multidict",
    "numpy": "numpy._core._multiarray_umath",
    "pandas": "pandas._libs.interval",
    "pillow": "PIL._imaging",
    "propcache": "propcache._helpers_c",
    "psycopg-binary": "psycopg_binary.pq",
    "pydantic_core": "pydantic_core._pydantic_core",
    "uvloop": "uvloop.loop",
    "watchfiles": "watchfiles._rust_notify",
    "websockets": "websockets.speedups",
    "yarl": "yarl._quoting_c",
}
ENTRY_POINTS = (
    "app.main", "app.ir_worker", "app.valuation_worker",
    "app.server_usage_worker", "app.r2d2_worker", "app.r2d2_shadow_candidate_worker",
)


async def event_loop_probe():
    await asyncio.sleep(0)
    values = await asyncio.gather(asyncio.sleep(0, result=20), asyncio.sleep(0, result=22))
    return sum(values)


def main():
    report = {"schema": "PR379-ALPINE-RUNTIME-SMOKE-v1", "classification": "FAIL",
              "expected_source_head": EXPECTED_HEAD, "production_access": False,
              "provider_calls": 0, "database_connections": 0, "worker_cycles_started": 0}
    stage = "environment"
    try:
        assert sys.flags.optimize == 0, "assertions must be enabled"
        assert os.environ.get("C3PO_SMOKE_NON_PRODUCTION") == "1"
        assert EXPECTED_HEAD and len(EXPECTED_HEAD) == 40, "C3PO_SMOKE_SOURCE_HEAD must be the 40-hex source head"
        assert sys.version_info[:2] == (3, 12)
        os_release = platform.freedesktop_os_release()
        assert os_release["ID"] == "alpine"
        assert os_release["VERSION_ID"].startswith("3.24.")
        musl_loaders = sorted(path.name for path in Path("/lib").glob("ld-musl-*.so.1"))
        assert musl_loaders
        assert sys.dont_write_bytecode
        # All application/provider settings must be pristine in this disposable
        # image. No --env-file, host credentials or .env directory is mounted.
        assert not any(value and (name.startswith("C3PO_") and not name.startswith("C3PO_SMOKE_"))
                       for name, value in os.environ.items())
        for name in ("DATABASE_URL", "BRAPI_TOKEN", "EODHD_API_TOKEN", "PLUGGY_CLIENT_ID",
                     "PLUGGY_CLIENT_SECRET", "PLUGGY_ITEM_IDS", "SENTRY_DSN",
                     "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
                     "EXCHANGE_SERVER", "EXCHANGE_USER", "EXCHANGE_APP_PASSWORD"):
            assert not os.environ.get(name)
        os.environ["C3PO_DATABASE_URL"] = ""
        os.environ["C3PO_SENTRY_DSN"] = ""
        os.environ["C3PO_ENVIRONMENT"] = "development"
        os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
        report["runtime"] = {"python": platform.python_version(), "os_id": os_release["ID"],
                             "os_version": os_release["VERSION_ID"], "machine": platform.machine(),
                             "musl_loaders": musl_loaders}

        stage = "native_extension_imports"
        assert len(NATIVE_MODULES) == 19
        imported = {}
        for distribution, module_name in NATIVE_MODULES.items():
            stage = "import:" + module_name
            if distribution == "psycopg-binary":
                # The distribution explicitly requires psycopg to be imported
                # first; direct psycopg_binary import would be a false failure.
                importlib.import_module("psycopg")
            module = importlib.import_module(module_name)
            assert str(module.__file__).endswith(".so"), "extension must load, not a pure Python fallback"
            imported[distribution] = {"version": importlib.metadata.version(distribution),
                                      "native_module": module_name}
        report["native_distributions"] = imported

        stage = "zoneinfo_offsets"
        offsets = {}
        for key, month, expected_hours in (
            ("America/Sao_Paulo", 1, -3), ("America/Sao_Paulo", 7, -3),
            ("America/New_York", 1, -5), ("America/New_York", 7, -4),
        ):
            instant = dt.datetime(2026, month, 15, 12, tzinfo=dt.timezone.utc)
            seconds = instant.astimezone(ZoneInfo(key)).utcoffset().total_seconds()
            assert seconds == expected_hours * 3600
            offsets[key + ":" + instant.date().isoformat()] = seconds
        report["zoneinfo_offsets_seconds"] = offsets

        stage = "cryptography_fernet"
        from cryptography.fernet import Fernet
        cipher = Fernet(Fernet.generate_key())
        assert cipher.decrypt(cipher.encrypt(b"non-production-runtime-check")) == b"non-production-runtime-check"

        stage = "psycopg_binary_libpq"
        import psycopg
        assert psycopg.pq.__impl__ == "binary"
        libpq_version = psycopg.pq.version()
        assert isinstance(libpq_version, int) and libpq_version > 0
        report["libpq_version"] = libpq_version

        stage = "curl_version_no_http_request"
        from curl_cffi import Curl
        curl = Curl()
        try:
            curl_version = curl.version()
            assert b"libcurl/" in curl_version
            report["curl_version"] = curl_version.decode("ascii", errors="strict")
        finally:
            curl.close()

        stage = "pillow_memory_png"
        from PIL import Image
        png = io.BytesIO()
        Image.new("RGB", (2, 2), (1, 2, 3)).save(png, format="PNG")
        png.seek(0)
        with Image.open(png) as decoded:
            assert decoded.size == (2, 2) and decoded.getpixel((0, 0)) == (1, 2, 3)

        stage = "numpy_pandas_small_operation"
        import numpy as np
        import pandas as pd
        values = np.array([1.0, 2.0, 3.0])
        assert float(np.dot(values, values)) == 14.0
        frame = pd.DataFrame({"group": [0, 0, 1], "value": values})
        assert frame.groupby("group")["value"].sum().tolist() == [3.0, 3.0]

        stage = "entry_point_imports_without_lifespan_or_worker_main"
        entry_points = []
        for module_name in ENTRY_POINTS:
            stage = "entrypoint:" + module_name
            module = importlib.import_module(module_name)
            assert Path(module.__file__).resolve().is_relative_to(Path("/app/app"))
            entry_points.append(module_name)
        report["entry_points_imported"] = entry_points

        stage = "uvloop_execution"
        import uvloop
        loop = uvloop.new_event_loop()
        try:
            assert loop.__class__.__module__.split(".")[0] == "uvloop"
            assert loop.run_until_complete(event_loop_probe()) == 42
        finally:
            loop.close()
        report["operations_passed"] = ["cryptography_fernet_roundtrip", "libpq_version_without_connection",
                                       "curl_version_without_request", "pillow_png_roundtrip_in_memory",
                                       "numpy_dot", "pandas_groupby_sum", "uvloop_async_gather"]
        report["classification"] = "PASS"
        report["limits"] = "No production calls, worker cycles, external DNS validation or performance benchmark. This checks extension loading, small operations and entry-point imports."
    except Exception as exc:
        report["failed_stage"] = stage
        report["error_class"] = type(exc).__name__
    print(json.dumps(report, sort_keys=True, ensure_ascii=True, allow_nan=False))
    return 0 if report["classification"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
