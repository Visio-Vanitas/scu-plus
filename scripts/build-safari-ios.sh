#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
pnpm package:safari:xcode --ios-only
python3 - <<'PY'
import pathlib, plistlib, subprocess, json, os, re
root = pathlib.Path('build/safari-xcode')
projects = list(root.rglob('*.xcodeproj'))
assert len(projects) == 1, f'Expected one Xcode project, found {len(projects)}'
# The Apple converter may derive the final component from the app name.
# Normalize generated target IDs before compiling, preserving target suffixes.
pbx = projects[0] / 'project.pbxproj'
project_text = pbx.read_text()
ids = re.findall(r'PRODUCT_BUNDLE_IDENTIFIER = "([^";]+)";', project_text)
assert ids, 'No generated bundle identifiers found'
base = min(ids, key=len)
assert all(value.startswith(base) for value in ids), 'Unexpected unrelated target identifiers'
requested = os.environ.get('SAFARI_BUNDLE_ID', 'io.github.brotherhoodofscu.scuplus')
project_text = re.sub(r'(PRODUCT_BUNDLE_IDENTIFIER = ")([^";]+)(";)',
    lambda match: match[1] + requested + match[2][len(base):] + match[3], project_text)
pbx.write_text(project_text)

# The containing app and extension use only sandbox/network access. Fail if a
# future Xcode template introduces capabilities requiring a dedicated profile.
allowed = {'com.apple.security.app-sandbox', 'com.apple.security.network.client', 'com.apple.security.files.user-selected.read-only'}
for path in root.rglob('*.entitlements'):
    data = plistlib.loads(path.read_bytes())
    assert set(data) <= allowed, f'Review new native capabilities before signing: {path}: {list(data)}'
info = json.loads(subprocess.check_output(['xcodebuild', '-list', '-json', '-project', str(projects[0])]))
schemes = [s for s in info['project']['schemes'] if s == 'SCU Plus' or s == 'SCU Plus (iOS)']
assert len(schemes) == 1, f'Unexpected app schemes: {info["project"]["schemes"]}'
for info_path in root.rglob('Info.plist'):
    data = plistlib.loads(info_path.read_bytes())
    data['ITSAppUsesNonExemptEncryption'] = False
    info_path.write_bytes(plistlib.dumps(data))
version = json.loads(pathlib.Path('package.json').read_text())['version']
build_number = os.environ.get('GITHUB_RUN_NUMBER', '1')
subprocess.run(['xcodebuild', 'archive', '-project', str(projects[0]), '-scheme', schemes[0],
    '-configuration', 'Release', '-destination', 'generic/platform=iOS',
    '-archivePath', 'build/safari-ios.xcarchive', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=NO',
    f'MARKETING_VERSION={version}', f'CURRENT_PROJECT_VERSION={build_number}',
    'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'CODE_SIGN_IDENTITY='], check=True)
apps = list(pathlib.Path('build/safari-ios.xcarchive/Products/Applications').glob('*.app'))
assert len(apps) == 1
bundles = [*apps[0].glob('PlugIns/*.appex'), apps[0]]
assert len(bundles) == 2
for bundle in bundles:
    info = plistlib.loads((bundle / 'Info.plist').read_bytes())
    assert info['CFBundleIdentifier'].startswith(requested)
    assert info['CFBundleShortVersionString'] == version
    subprocess.run(['codesign', '--force', '--sign', '-', str(bundle)], check=True)
subprocess.run(['ditto', '-c', '-k', '--keepParent', 'build/safari-ios.xcarchive',
    'build/scu-plus-safari-ios-unsigned.zip'], check=True)
PY
