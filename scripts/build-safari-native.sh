#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
pnpm package:safari:xcode --macos-only
python3 - <<'PY'
import pathlib, plistlib, subprocess, json, os
root = pathlib.Path('build/safari-xcode')
projects = list(root.rglob('*.xcodeproj'))
assert len(projects) == 1, f'Expected one Xcode project, found {len(projects)}'
# The containing app and extension use only sandbox/network access. Fail if a
# future Xcode template introduces capabilities requiring a dedicated profile.
allowed = {'com.apple.security.app-sandbox', 'com.apple.security.network.client', 'com.apple.security.files.user-selected.read-only'}
for path in root.rglob('*.entitlements'):
    data = plistlib.loads(path.read_bytes())
    assert set(data) <= allowed, f'Review new native capabilities before signing: {path}: {list(data)}'
info = json.loads(subprocess.check_output(['xcodebuild', '-list', '-json', '-project', str(projects[0])]))
schemes = [s for s in info['project']['schemes'] if s == 'SCU Plus' or s == 'SCU Plus (macOS)']
assert len(schemes) == 1, f'Unexpected app schemes: {info["project"]["schemes"]}'
version = json.loads(pathlib.Path('package.json').read_text())['version']
build_number = os.environ.get('GITHUB_RUN_NUMBER', '1')
subprocess.run(['xcodebuild', 'archive', '-project', str(projects[0]), '-scheme', schemes[0],
    '-configuration', 'Release', '-destination', 'generic/platform=macOS',
    '-archivePath', 'build/safari-native.xcarchive', 'ARCHS=arm64 x86_64', 'ONLY_ACTIVE_ARCH=NO',
    f'MARKETING_VERSION={version}', f'CURRENT_PROJECT_VERSION={build_number}',
    'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'CODE_SIGN_IDENTITY='], check=True)
apps = list(pathlib.Path('build/safari-native.xcarchive/Products/Applications').glob('*.app'))
assert len(apps) == 1, 'Expected one containing app'
for bundle in [apps[0], *apps[0].glob('Contents/PlugIns/*.appex')]:
    info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
    binary = bundle / 'Contents/MacOS' / info['CFBundleExecutable']
    archs = subprocess.check_output(['lipo', '-archs', str(binary)], text=True).split()
    assert set(archs) == {'arm64', 'x86_64'}, f'Expected universal binary: {binary}: {archs}'
subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(apps[0]),
    'build/scu-plus-safari-macos-unsigned.zip'], check=True)
subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(root),
    'build/scu-plus-safari-xcode.zip'], check=True)
PY
