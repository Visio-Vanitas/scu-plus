# Safari 构建与验证

本项目保留同一套 Plasmo 源码，生成 Safari Manifest V3 扩展。当前验证目标为 macOS Safari 26；iOS/iPadOS 和较早 Safari 版本需要另行验收。Web 扩展 ZIP 是开发测试产物，不是已签名的 macOS App 或 iOS 安装包。

## 构建

与 Chromium / Firefox 使用相同工具链：Node.js `>=22.13 <23`、pnpm `11.18.0`。

```bash
pnpm install --frozen-lockfile
pnpm test:compat
pnpm build:safari
```

输出：

- `build/safari-mv3-prod/`：Safari Web Extension 目录。
- `build/safari-mv3-prod.zip`：相同内容的未签名 ZIP。

清单、后台和内容脚本由 Plasmo 生成；不要手工修改 `build/` 内的清单。发布工作流同时构建 Chrome、Firefox 和 Safari ZIP。

## macOS Safari 临时安装

按照 [Apple 的运行说明](https://developer.apple.com/documentation/safariservices/running-your-safari-web-extension)：

1. Safari → 设置 → 高级，显示网页开发者功能（如果“开发者”标签尚未出现）。
2. 设置 → 开发者 → “添加临时扩展 / Add Temporary Extension…”。按系统提示允许未签名开发扩展，并完成本机认证。
3. 选择 `build/safari-mv3-prod/` 或 ZIP；在扩展设置中启用 SCU Plus。
4. 对统一认证 `id.scu.edu.cn`、教务系统 `zhjw.scu.edu.cn` 授予网站访问权限。更新检查需要 `api.github.com`；QQ 头像涉及 `q1.qlogo.cn`。权限未授予时，相关功能可能不可用。
5. 构建更新后，在 Safari 的扩展设置中重新载入扩展，再刷新相关页面。

临时扩展在退出 Safari 或 24 小时后被移除。安装行为不是永久分发方案。不要为此关闭跨域限制、跟踪防护或证书检查。

## Xcode 与分发

需要完整 Xcode；仅有 Command Line Tools 无法生成原生工程：

```bash
pnpm package:safari:xcode
```

该命令重新构建 Safari 扩展并调用 Apple 的打包器（优先 `safari-web-extension-packager`，兼容旧名 `safari-web-extension-converter`），在 `build/safari-xcode/` 生成工程。如果工程已存在会退出，避免覆盖签名配置或原生修改。默认 bundle identifier 为 `io.github.brotherhoodofscu.scuplus`；正式发布前应在 Xcode 中使用团队持有的标识和签名配置。

工程包含扩展资源的副本；以后重新构建 Web 扩展不会自动更新该副本。需要在 Xcode 中更新资源或保留原生修改后重新生成工程。打包参数依据 [Apple 打包说明](https://developer.apple.com/documentation/safariservices/packaging-a-web-extension-for-safari)。

在 Xcode 选择目标设备和 Signing Team 后运行。iOS/iPadOS 必须通过包含扩展的 App 安装，不能直接安装这里的 ZIP。正式分发参考 [Apple 分发说明](https://developer.apple.com/documentation/safariservices/distributing-your-safari-web-extension)。本仓库不包含签名证书，也不自动发布 App Store。

## 兼容性依据

- [Discussion #40](https://github.com/The-Brotherhood-of-SCU/scu-plus/discussions/40) 和其 [社区移植](https://github.com/wjj-8283/scu-plus-safari) 提供了 Safari 可行性反馈：课表图片与 ICS 导出正常；开启跳过 2FA 出现 505；头像问题后来修复；选课和评教未验证。该讨论没有评论，不能将单个移植报告表述为社区已经全面验证。
- [Apple 浏览器兼容性说明](https://developer.apple.com/documentation/safariservices/assessing-your-safari-web-extension-s-browser-compatibility) 明确支持 `chrome.*` / `browser.*` 和 Promise / callback，无需为 Safari 全量替换 API 命名空间。`storage.sync` 支持存储，但不提供跨设备同步；继续使用原存储区，避免迁移造成配置丢失。
- [Apple Web Extensions 介绍](https://developer.apple.com/videos/play/wwdc2026/216/) 展示了 `declarativeNetRequestWithHostAccess`、动态规则和重定向。保留头像网络重定向，验证时必须检查站点授权、规则安装和图片实际加载；社区旧分支的故障描述不能证明当前 Safari 不支持该 API。
- [Plasmo 构建文档](https://docs.plasmo.com/framework/workflows/build) 支持 Safari 构建目标和 `PLASMO_BROWSER`。生成 Web 扩展与生成 Xcode 工程是两个步骤。

## 验收项目

`pnpm test:compat` 是模拟扩展 API / 页面响应的回归检查，不等于 Safari 实机测试。覆盖更新包匹配、505 回退及同标签页导航、XHR 默认异步行为、document_start 根节点尚不存在等情况。

Safari 实机验收应记录浏览器版本、操作、结果和控制台错误：

| 项目 | 操作与通过标准 |
| --- | --- |
| 安装与权限 | 临时安装成功；仅授权所需站点；后台和内容脚本无初始化异常 |
| 弹窗与设置 | 打开弹窗、进入设置、保存并重新打开，配置仍存在 |
| 主题与 iframe | 明暗切换和点缀色立即生效；教务内嵌页面正常；刷新不闪回旧主题 |
| 本地 OCR | 在用户参与的登录测试中，两个登录入口均可本地识别；无远程 OCR 请求 |
| 普通登录 | 跳过 2FA 关闭时可以按学校正常流程登录 |
| 505 回退 | 服务端返回 `505 / 2factor-pending` 后提示完成验证；同标签页重新登录不再修改 2FA 响应 |
| 头像 | QQ / 自定义 URL 替换成功；修改与关闭后刷新，规则与图片恢复正确 |
| 成绩与课表 | 图表显示；图片、JSON、ICS 文件可下载并打开 |
| 更新 | Safari 只匹配 Safari 生产 ZIP；不存在时打开发布页，不下载 Chrome 或源码 ZIP |
| 选课与评教 | 在合适的测试环境中验证页面增强；真实选退课或提交评教需用户明确确认 |

505 回退只表示停止修改后续认证响应，不能证明服务端登录已经成功。若会话存储不可用，仍会停用当前页面的拦截，但需用户在设置中关闭跳过两步验证，避免导航后重新启用。恢复该功能需在新的标签页会话中重试；服务端要求的两步验证应正常完成。

## 个人 fork 的 GitHub CI/CD

### 暂无 Apple 签名账户时

保持 `APPLE_SIGNING_ENABLED` 未设置或为 `false`，不需要创建任何 Apple Secrets。推送工作流后即可运行无签名构建，下载 Safari Web 扩展、Xcode 工程和未签名 macOS App。未签名 App 不是可直接对外分发的安装包；本机调试优先使用上面的 Safari 临时扩展方式。

配置模板在 `.github/apple/signing-config.example.json`，只包含变量和所需 Secret 名称，不填写私钥或密码。当前采用 macOS Developer ID 分发，后续需要 Developer ID Application 证书及公证密钥；iOS Ad Hoc 分发不属于这条流程。

账户可用后，按以下顺序补齐材料：

1. 由团队 Account Holder 在 Apple Developer 中选择 Developer ID Application，上传本机生成的 CSR，下载签发的 `.cer`。证书属于开发团队；为本项目单独生成密钥便于管理，但不会把证书权限限制到一个 Bundle ID。
2. 将 `.cer` 导入生成 CSR 的同一台 Mac 的登录钥匙串，确认该证书下面存在对应私钥，再导出带密码的 `.p12`。只有 `.cer` 不能完成 CI 签名。
3. 在 App Store Connect 创建用于公证的 Team API Key，保留 Key ID、Issuer ID，并下载 `.p8`。团队密钥的权限不由项目名称隔离；按实际公证需要选择角色。
4. 把 P12、密码和 API Key 配置到下表指定的 GitHub Secrets，核对 Team ID 与证书名称，最后设置 `APPLE_SIGNING_ENABLED=true` 并重新运行。

本地签名材料保存在仓库外；不要把 `.p12`、`.p8` 或密码放进配置模板。申请依据：[Apple Developer ID 证书说明](https://developer.apple.com/help/account/certificates/create-developer-id-certificates)、[CSR 说明](https://developer.apple.com/help/account/certificates/create-a-certificate-signing-request)、[App Store Connect API 说明](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-api)。

### 工作流与配置

[Visio-Vanitas/scu-plus](https://github.com/Visio-Vanitas/scu-plus) 的 `codex/safari-ci-signing` 分支使用 `.github/workflows/safari-ci.yml`。推送到该分支或手动运行 workflow 均会：

1. 在 macOS runner 使用锁定依赖运行回归检查、Chromium / Firefox 构建。
2. 构建 Safari ZIP、完整 Xcode 工程 ZIP，以及同时包含 arm64 / x86_64 的未签名 macOS App ZIP。
3. 当仓库变量 `APPLE_SIGNING_ENABLED=true` 时，独立任务导入 Developer ID 证书，先签扩展、再签包含它的 App，制作 DMG，提交 Apple 公证，装订公证票据并运行验证。
4. 在本次 Actions run 的 Artifacts 中提供产物。只有通过签名、公证和验证的 DMG 才进入 `safari-signed-notarized-*` artifact；不会自动上传到上游 Releases。

构建任务不接收 Apple Secrets。证书只在签名任务中使用，结束后删除临时钥匙串与密钥文件。该结构参考个人 [Bugaoshan apple-ci 工作流](https://github.com/Visio-Vanitas/Bugaoshan/blob/apple-ci/.github/workflows/apple-release-sync.yml)，实现依据 [GitHub 的 Apple 签名说明](https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications)。

在新 fork 的 Settings → Secrets and variables → Actions 配置以下 **Secrets**（名称沿用 Bugaoshan；GitHub 不允许读回旧仓库 Secret）：

| Secret | 内容 |
| --- | --- |
| `MACOS_DEVELOPER_ID_P12_BASE64` | Developer ID Application 证书及私钥导出的 P12，以 base64 编码 |
| `MACOS_DEVELOPER_ID_P12_PASSWORD` | P12 导出密码 |
| `APPLE_API_KEY_ID` | App Store Connect API Key ID |
| `APPLE_API_ISSUER_ID` | 对应 Issuer ID |
| `APPLE_API_PRIVATE_KEY` | 对应 Team API Key 的 `.p8` 私钥全文（本流程使用带 Issuer ID 的团队密钥） |

配置以下 **Variables**：

| Variable | 内容 |
| --- | --- |
| `APPLE_TEAM_ID` | Developer ID 证书所属 Team ID |
| `MACOS_SIGNING_IDENTITY` | 完整的 `Developer ID Application: … (TEAMID)` 证书名称 |
| `APPLE_SIGNING_ENABLED` | 所有材料就绪后设为 `true`；缺省或 `false` 时明确跳过签名 |

当前默认 bundle ID 为 `io.github.brotherhoodofscu.scuplus`，如需更换，应同步工作流中的 `SAFARI_BUNDLE_ID`。不要使用 Bugaoshan 的 bundle ID 或其专属 profile。这里的原生外壳使用 App Sandbox / Network Client 和 Xcode 模板默认的用户所选文件只读权限，不申请 App Groups 等受限能力，因此按 [Apple TN3125](https://developer.apple.com/documentation/technotes/tn3125-inside-code-signing-provisioning-profiles) 的 Developer ID 模型不要求额外 profile。构建脚本遇到新的原生 entitlement 会停止，要求先评估能力及 provisioning，而不会静默丢弃它。

GitHub 无法把 Bugaoshan 的 Secret 解密复制到新 fork。若原始材料已经丢失，需要从可用的钥匙串重新导出 Developer ID 身份，或重新准备签名证书及 API key；本工作流不会自动吊销原有证书。iOS/TestFlight 使用不同的证书、App 标识及 provisioning，本工作流当前不包含 iOS 分发。

## 跟随上游发布

`.github/workflows/safari-release-sync.yml` 只在个人分发仓库运行。默认分支须包含此工作流；当前使用 `codex/safari-ci-signing` 作为分发默认分支。每 15 分钟检查（每小时第 2、17、32、47 分钟）上游最近 100 个 release，从 v2.3.3 起按版本顺序补齐未分发的稳定版本，每次一个。手动运行可指定一个已发布的 `vX.Y.Z` tag；草稿和 prerelease 不进入正式分发。

工作流解析上游 tag 为固定 commit，校验 package 版本，取该 commit 的源码并仅补入 Safari 打包脚本与分发元数据。它不合并 beta 分支的功能代码。构建、签名、公证、发布分为不同任务，构建不读取 Apple Secrets，只有发布任务有 contents: write。通过全部验证后才在子仓库同步同名 tag、上传已签名公证的 DMG、未签名 IPA 和 SHA256SUMS 并发布 Release。发布说明记录上游 commit、打包脚本 commit 和构建链接。已有正式 Release 不覆盖，上游 tag 移动或来源不一致会停止。

可选的 webhook 转发入口是 `repository_dispatch`，事件类型 `upstream-release`，payload 可携带 `tag`。调用方必须用有权向本分发仓库发送 dispatch 的 GitHub 凭据。GitHub 原始 release webhook 不能直接指向 dispatch API，需要验证 webhook 签名并转换事件的接收服务；当前未部署此服务，也未在主仓库添加 webhook。定时检查和手动运行不依赖 webhook 或上游 Secret。GitHub 的定时事件可能延迟，公共仓库长期无活动时可能暂停，维护者应检查 Actions 状态。

## iOS/iPadOS 未签名 IPA

> **不建议任何不了解 IPA 的同学下载或尝试安装。** 普通测试者请使用 TestFlight。

分发仓库的每个新 Safari Release 同时提供 `scu-plus-safari-ios-unsigned.ipa`，从同一上游 tag 的固定 commit 构建。`SHA256SUMS` 包含 DMG 和 IPA 的校验值；v2.3.3 后补的 IPA 使用独立的 `.ipa.sha256` 文件，保留原 DMG 校验文件。

IPA 包含 `Payload/SCU Plus.app` 及其 Safari 扩展。打包脚本从 archive 的副本移除主应用和扩展的临时签名及描述文件，不读取 Apple Secrets；原 archive 仍可用于 TestFlight 签名导出。

此文件面向有技术背景的测试者，不能直接安装到普通 iPhone/iPad。需要使用自己的签名身份和匹配的描述文件同时重签主应用与 `.appex`，必要时调整两者 Bundle ID，然后安装并在 Safari 设置中启用扩展、授予网站权限。重签工具必须保留 Safari 扩展，具体账号和设备限制取决于使用的分发方式。仓库不提供私钥或可供公众直接安装的 iOS 签名。

这是 Release 构建，不附带 `get-task-allow` 调试权限。需要原生断点调试时，应从对应 tag 生成 Xcode 工程并以自己的开发签名运行；重签 IPA 不等于完成 iOS 真机验收。

本地从已构建的 archive 打包：

```bash
python3 scripts/package-unsigned-ipa.py build/safari-ios.xcarchive build/scu-plus-safari-ios-unsigned.ipa
```

## iOS TestFlight

子仓库的 `safari-testflight.yml` 参考 Bugaoshan 的独立 archive / 签名上传 / 测试组及 Beta App Review 分发机制。默认关闭上传；手动运行可先验证无凭据 iOS 构建。上游正式 release tag 对应的源码固定到 commit，主 App 使用 `io.github.brotherhoodofscu.scuplus`，扩展使用 `io.github.brotherhoodofscu.scuplus.Extension`。原生打包使用系统 HTTPS，不引入自定义加密，Info.plist 声明不使用非豁免加密；如后续增加加密功能须重新评估。

启用前需要：
- Apple Developer 协议有效，App Store Connect 已创建对应 iOS App。
- `IOS_DISTRIBUTION_P12_BASE64`、`IOS_DISTRIBUTION_P12_PASSWORD`：Apple Distribution 身份及导出密码。
- `IOS_APP_STORE_PROFILE_BASE64`、`IOS_EXTENSION_APP_STORE_PROFILE_BASE64`：上述两个 Bundle ID 各自的 App Store 分发描述文件。
- 独立的 `TESTFLIGHT_API_KEY_ID`、`TESTFLIGHT_API_ISSUER_ID`、`TESTFLIGHT_API_PRIVATE_KEY` Secrets：使用 App Manager 角色的团队 API 密钥完成上传和外部 TestFlight 管理。团队密钥权限覆盖团队所有 App；原 `APPLE_API_*` 继续供 macOS 公证使用。
- `TESTFLIGHT_BETA_GROUP_IDS` 仓库变量：SCU Plus 自己的测试组 ID，不能使用 Bugaoshan 的组。
- 测试说明、反馈邮箱、审核联系人及必要的测试访问方式已在 App Store Connect 填好。

最后设置 `IOS_TESTFLIGHT_ENABLED=true`，每 15 分钟同步（每小时第 7、22、37、52 分钟）上游未提交的稳定版本。成功标记 `testflight/vX.Y.Z` 表示构建已处理并提交至组/审核，不表示 Apple 已批准。公测必须通过相应审核并启用外部组公开链接，才能把该链接作为可用邀测链接提供。首次 iOS 构建 2.3.3（3）已完成签名、上传并提交 Beta 审核。公开邀测链接为 https://testflight.apple.com/join/VfB4puVJ；能否安装以 Apple 当前审核和测试状态为准。
