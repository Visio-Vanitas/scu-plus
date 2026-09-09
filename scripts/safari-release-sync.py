"""Resolve published upstream tags and publish notarized Safari releases."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

UPSTREAM = 'The-Brotherhood-of-SCU/scu-plus'
DOWNSTREAM = 'Visio-Vanitas/scu-plus'
TAG = re.compile(r'^v(\d+)\.(\d+)\.(\d+)$')
ASSET = 'scu-plus-safari-macos.dmg'


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True).strip()


def api(path):
    return json.loads(gh('api', path))


def output(**values):
    with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
        for key, value in values.items():
            f.write(f'{key}={value}\n')


def version(tag):
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError(f'Expected a stable vX.Y.Z release tag: {tag!r}')
    return tuple(map(int, match.groups()))


def resolve():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    requested = event.get('inputs', {}).get('tag') or event.get('client_payload', {}).get('tag')
    if requested:
        version(requested)
        releases = [api(f'repos/{UPSTREAM}/releases/tags/{quote(requested, safe="")}')]
    else:
        releases = api(f'repos/{UPSTREAM}/releases?per_page=100')
        releases = [r for r in releases if TAG.fullmatch(r['tag_name'])
                    and version(r['tag_name']) >= (2, 3, 3)]
        releases.sort(key=lambda r: version(r['tag_name']))
    existing = api(f'repos/{DOWNSTREAM}/releases?per_page=100')
    if os.environ.get('RELEASE_CHANNEL') == 'testflight':
        markers = api(f'repos/{DOWNSTREAM}/git/matching-refs/tags/testflight/')
        completed = {m['ref'].removeprefix('refs/tags/testflight/') for m in markers}
        releases = [r for r in releases if r['tag_name'] not in completed]
        existing = []
    for release in releases:
        if release['draft'] or release['prerelease']:
            continue
        tag = release['tag_name']
        ref = api(f'repos/{UPSTREAM}/git/ref/tags/{quote(tag, safe="")}')['object']
        for _ in range(5):
            if ref['type'] == 'commit':
                break
            if ref['type'] != 'tag':
                raise ValueError('Tag does not identify a commit')
            ref = api(f'repos/{UPSTREAM}/git/tags/{ref["sha"]}')['object']
        if ref['type'] != 'commit':
            raise ValueError('Tag indirection too deep')
        sha = ref['sha']
        previous = next((r for r in existing if r['tag_name'] == tag), None)
        if previous and not previous['draft']:
            assert f'Upstream commit: {sha}' in (previous['body'] or ''), 'Published release provenance mismatch'
            assert any(a['name'] == ASSET for a in previous['assets']), 'Published release missing signed DMG'
            continue
        output(build='true', tag=tag, sha=sha, version=tag[1:])
        return
    output(build='false')


def publish():
    tag, sha = os.environ['UPSTREAM_TAG'], os.environ['UPSTREAM_SHA']
    version(tag)
    assert re.fullmatch(r'[0-9a-f]{40}', sha)
    # Fetch the actual tag, retaining annotated tags; never move an existing tag.
    subprocess.run(['git', 'fetch', '--no-tags', f'https://github.com/{UPSTREAM}.git',
                    f'refs/tags/{tag}:refs/tags/{tag}'], check=True)
    assert gh('api', f'repos/{UPSTREAM}/commits/{quote(tag, safe="")}', '--jq', '.sha') == sha
    actual = subprocess.check_output(['git', 'rev-parse', f'{tag}^{{commit}}'], text=True).strip()
    assert actual == sha, 'Upstream tag moved during build'
    subprocess.run(['git', 'push', 'origin', f'refs/tags/{tag}:refs/tags/{tag}'], check=True)
    notes = (f'Safari builds of [{tag}](https://github.com/{UPSTREAM}/releases/tag/{tag}).\n\n'
             f'Upstream commit: {sha}\n\n'
             f'Packaging workflow commit: {os.environ["GITHUB_SHA"]}\n\n'
             f'Build: https://github.com/{DOWNSTREAM}/actions/runs/{os.environ["GITHUB_RUN_ID"]}\n\n'
             'Download the DMG, drag SCU Plus to Applications, then enable it in Safari Settings → Extensions.\n'
             'The macOS DMG is Developer ID signed and Apple notarized.\n\n'
             '**不建议任何不了解 IPA 的同学下载或尝试安装。** 普通测试者请使用 TestFlight。\n\n'
             'iOS/iPadOS: `scu-plus-safari-ios-unsigned.ipa` is an unsigned Release build for technical testers. '
             'It cannot be installed as downloaded. Re-sign both the containing app and Safari extension '
             'with your own identity and matching provisioning profiles before installation; then enable the extension in Safari settings. '
             'It includes no certificate, private key, provisioning profile or debug entitlement. '
             'For native breakpoint debugging, build the source with Xcode.\n\n'
             'TestFlight: https://testflight.apple.com/join/VfB4puVJ (availability depends on Apple review and the active beta).\n')
    Path('release-notes.md').write_text(notes)
    existing = api(f'repos/{DOWNSTREAM}/releases?per_page=100')
    release = next((r for r in existing if r['tag_name'] == tag), None)
    if release:
        assert release['draft'], 'Refusing to overwrite a published release'
    else:
        gh('release', 'create', tag, '--repo', DOWNSTREAM, '--verify-tag', '--draft',
           '--title', f'SCU Plus Safari {tag}', '--notes-file', 'release-notes.md')
    for filename in (ASSET, 'scu-plus-safari-ios-unsigned.ipa', 'SHA256SUMS'):
        gh('release', 'upload', tag, str(Path(os.environ['RELEASE_DIR']) / filename),
           '--repo', DOWNSTREAM, '--clobber')
    gh('release', 'edit', tag, '--repo', DOWNSTREAM, '--draft=false', '--notes-file', 'release-notes.md')


if __name__ == '__main__':
    {'resolve': resolve, 'publish': publish}[sys.argv[1]]()
