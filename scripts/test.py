#!/usr/bin/env python3
"""CI regression tests for a 3-file Telegram WEB Proxy build repository.

  python3 scripts/build.py restore
  python3 scripts/test.py unit      # standard library, no Docker needed
  python3 scripts/test.py smoke     # Docker required; run after image build

Tests from the original audited project are included in build.py's verified
bundle. The smoke test additionally validates credential persistence, per-boot
connection info, internal-only listeners, runtime warning filtering, container
restart behavior, and local HTTP Web Proxy authentication. It cannot prove
actual Telegram message delivery without real client verification.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DRIVER = REPO / 'scripts/build.py'
WORK = REPO / 'tg-aio-work/project'


def require(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)


def unit_tests() -> None:
    spec = importlib.util.spec_from_file_location('tg_aio_build_driver', DRIVER)
    require(spec is not None and spec.loader is not None, 'Missing build.py driver')
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    blob = base64.b64decode(''.join(driver.ARCHIVE_BASE64.split()), validate=True)
    require(hashlib.sha256(blob).hexdigest() == driver.ARCHIVE_SHA256,
            'Bundled wrapper source integrity check failed')
    for relative in driver.EXPECTED_FILES:
        require((WORK / relative).is_file(), f'Embedded source file missing: {relative}')
    # Guard the public Release attachment naming contract.
    release_file = WORK / 'scripts/release.py'
    spec2 = importlib.util.spec_from_file_location('twp_release_helper', release_file)
    require(spec2 is not None and spec2.loader is not None, 'Missing release helper')
    helper = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(helper)
    require(helper.ASSETS == ('twp-sources.tar.gz', 'twp-amd64.tar.gz'),
            f'Wrong Release attachment names: {helper.ASSETS}')
    require(helper.image_tags('20261018T200000Z-bbbbbbbb-cccccccc') == ['twp:latest', 'twp:bbbbbbbb-cccccccc'],
            'Docker image tags differ from twp:latest and twp:<two-short-IDs>')
    print('PASS: exactly two public Release assets with twp-* names and twp image tags', flush=True)

    # A two-job workflow is enough: detect, then build-and-publish on one runner.
    # No upload-artifact or download-artifact step may create run Artifacts.
    workflow = (REPO / '.github/workflows/build.yml').read_text(encoding='utf-8')
    require('  build_publish:' in workflow and '  detect:' in workflow,
            'Detection and build/publish stages must both be present')
    require('needs: detect' in workflow and "needs.detect.outputs.build_needed == 'true'" in workflow,
            'Do not compile when official upstreams have not changed')
    require('actions/upload-artifact' not in workflow and 'actions/download-artifact' not in workflow,
            'Run Artifacts must not be published')
    require('actions/checkout@v6' in workflow and 'actions/checkout@v4' not in workflow,
            'Node 24-compatible checkout is required')
    require('GITHUB_STEP_SUMMARY' not in release_file.read_text(encoding='utf-8'),
            'Do not write GitHub job summaries')
    require('python3 scripts/build.py publish' in workflow,
            'Publish directly after package on the same runner')
    print('PASS: no job summaries, no run Artifacts, direct Release upload', flush=True)

    print('PASS: embedded bundle SHA256 and required build sources', flush=True)

    subprocess.run([sys.executable, '-m', 'compileall', '-q', 'scripts', 'tests'],
                   cwd=WORK, check=True)
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                    '-p', 'test_release.py', '-v'], cwd=WORK, check=True)
    # Publish the same locally verified assets; no cross-job transfer needed.
    test_spec = importlib.util.spec_from_file_location(
        'twp_release_fixture', WORK / 'tests/test_release.py')
    require(test_spec is not None and test_spec.loader is not None,
            'Release test fixtures are missing')
    fixtures = importlib.util.module_from_spec(test_spec)
    test_spec.loader.exec_module(fixtures)
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / 'dist'
        dist.mkdir(parents=True)
        fixtures.PublicationTests().make_bundle(dist)
        provenance = helper.verify_local_bundle(
            dist, fixtures.REPOSITORY, fixtures.REVISION, '123', '1')
        require(set(provenance['assets']) == set(helper.ASSETS),
                'Publication manifest has unexpected public assets')
    print('PASS: local-only release manifest validation', flush=True)
    print('PASS: 36 official-commit tracking / Release safety tests', flush=True)


def smoke_test(image: str) -> None:
    require((WORK / 'scripts/smoke-test.py').is_file(), 'Restore bundle before smoke test')
    subprocess.run([sys.executable, 'scripts/smoke-test.py', image], cwd=WORK, check=True)
    print('PASS: container startup, secret persistence, filtered logs and HTTP checks', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('unit', 'smoke'))
    parser.add_argument('--image', default='twp:latest')
    opts = parser.parse_args()
    if opts.command == 'unit':
        unit_tests()
    else:
        smoke_test(opts.image)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(1)
