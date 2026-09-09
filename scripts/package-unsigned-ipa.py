"""Package the Safari iOS archive for user re-signing, without any signing identity."""
import argparse
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path


def package(archive: Path, output: Path):
    apps = list((archive / 'Products/Applications').glob('*.app'))
    assert len(apps) == 1, 'Expected one containing app'
    assert not output.exists(), 'Refusing to overwrite an existing IPA'
    with tempfile.TemporaryDirectory() as directory:
        payload = Path(directory) / 'Payload'
        payload.mkdir()
        app = payload / apps[0].name
        subprocess.run(['ditto', str(apps[0]), str(app)], check=True)
        extensions = list(app.glob('PlugIns/*.appex'))
        assert len(extensions) == 1, 'Expected one Safari extension'
        # Fail closed if the converter starts embedding additional executable bundles.
        assert not list(app.rglob('*.framework')) and not list(app.rglob('*.dylib'))
        for bundle in [*extensions, app]:
            info = plistlib.loads((bundle / 'Info.plist').read_bytes())
            assert info['CFBundlePackageType'] in ('APPL', 'XPC!')
            # Archives are locally ad-hoc signed for exportArchive. Strip that
            # signature from the copy; preserve the archive for TestFlight export.
            subprocess.run(['codesign', '--remove-signature', str(bundle)], check=True)
            (bundle / 'embedded.mobileprovision').unlink(missing_ok=True)
            shutil.rmtree(bundle / '_CodeSignature', ignore_errors=True)
            result = subprocess.run(['codesign', '-d', str(bundle)], capture_output=True)
            assert result.returncode != 0, f'Signature remains: {bundle.name}'
        assert not list(app.rglob('embedded.mobileprovision'))
        assert not list(app.rglob('_CodeSignature'))
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['ditto', '-c', '-k', '--keepParent', '--norsrc',
                        str(payload), str(output.resolve())], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    package(args.archive, args.output)
