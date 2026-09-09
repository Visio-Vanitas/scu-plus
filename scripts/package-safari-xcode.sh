#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

SAFARI_PACKAGER=""
if [[ "$(uname -s)" == Darwin ]]; then
  for candidate in safari-web-extension-packager safari-web-extension-converter; do
    if xcrun --find "${candidate}" >/dev/null 2>&1; then
      SAFARI_PACKAGER="${candidate}"
      break
    fi
  done
fi
if [[ -z "${SAFARI_PACKAGER}" ]]; then
  echo "需要完整 Xcode 和 Safari Web Extension Packager（旧名 Converter）；仅安装 Command Line Tools 不够。" >&2
  echo "macOS Safari 临时测试可直接使用 pnpm build:safari 生成的目录，无需 Xcode。" >&2
  exit 1
fi
if [[ -e build/safari-xcode ]]; then
  echo "build/safari-xcode 已存在。请移走已有工程后重试，以保留签名和原生工程修改。" >&2
  exit 1
fi
pnpm build:safari
xcrun "${SAFARI_PACKAGER}" build/safari-mv3-prod \
  --project-location build/safari-xcode \
  --app-name 'SCU Plus' \
  --bundle-identifier "${SAFARI_BUNDLE_ID:-io.github.brotherhoodofscu.scuplus}" \
  --swift --copy-resources --no-open --no-prompt "$@"
