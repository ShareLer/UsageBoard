# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` 是指向本文件的软链接，供 Codex 等工具使用。

## 工作约定

- 默认使用中文沟通，表达简洁，结论可复制。
- 改动保持小而清晰，每处改动都应对应当前请求。
- 动手前先说明涉及文件、计划和验证方式。
- 执行命令前先说明为什么执行。
- 不读取、打印或提交真实 API Key、Token、私有配置或用户数据。
- 不擅自改无关代码；发现无关问题可以说明，但不要顺手处理。
- 只改 `~/Library/Application Support/UsageBoard/plugins` 中的用户插件脚本时，不需要重新构建 app。
- 修改 Swift app 代码、内置资源、打包脚本或 `dist/UsageBoard.app` 时，修改后需要构建、测试、签名并重启本地 app。
- 如果 `UsageBoard` 已在运行，重启前先停止旧进程。

## 常用命令

```bash
swift build
swift test
swift build -c release
bash scripts/build.sh
```

运行单个测试：

```bash
swift test --filter UsageBoardTests.testProgressHandlesBoundsAndRatio
```

发布新版本：

```bash
bash scripts/release.sh
bash scripts/release.sh 0.1.6
```

`scripts/release.sh` 会读取 `dist/UsageBoard.app/Contents/Info.plist` 中的当前版本，默认 patch +1，也可以显式传入版本号。脚本会构建、复制二进制和内置插件、签名、生成 zip 和 `version.json`，并上传到脚本中配置的服务器路径。自动生成的更新说明使用中文。

`scripts/build.sh` 和 `scripts/release.sh` 都通过 PlistBuddy 向 Info.plist 注入 `UBUpdateCheckURL` 字段，`UpdateChecker` 运行时从 Bundle 读取该字段作为更新检查地址。

## 项目结构

- `Package.swift`：Swift Package 定义，macOS 13+，Swift 6 strict concurrency。
- `Sources/UsageBoardCore/`：核心逻辑，无 SwiftUI 依赖。
- `Sources/UsageBoardApp/`：SwiftUI + AppKit macOS app。
- `Tests/UsageBoardTests/`：XCTest 单元测试。
- `Resources/BundledPlugins/`：内置 Python 插件，打包进 app 后安装到用户插件目录。
- `Resources/PluginAuthoringGuide.html`：插件编写说明，设置页插件列表右下角帮助按钮会打开它。
- `Resources/UsageBoard.icns`：应用图标资源。
- `scripts/build.sh`：本地 release 构建、签名并启动 app。
- `scripts/release.sh`：发布脚本。
- `dist/UsageBoard.app`：本地测试用 app bundle。
- `dist/version.json`、`dist/UsageBoard-*.zip`：发布产物。

## 运行时目录

默认运行时数据位于：

```text
~/Library/Application Support/UsageBoard/
```

其中：

- `config.json`：主配置文件。
- `plugins/`：用户插件目录。添加插件文件选择器默认打开这里。
- `states/`：插件数据缓存目录，按插件 `stateID` 分文件保存。

当前内置插件安装逻辑由 `BundledPluginInstaller` 负责：启动时从 app 包 `Contents/Resources/Plugins/`，或开发环境的 `Resources/BundledPlugins/`，向用户 `plugins/` 目录创建同名符号链接。若目标同名文件不是指向当前内置插件的符号链接，当前实现会移除并重建符号链接。修改此行为时需要同步 README 和测试。

启动时 `reloadAllMetadata()` 会重新解析所有插件的 metadata（包括 `icon`、`description`、`parameters` 定义）并持久化到 config.json，同时为新参数填充默认值。用户通过 UI 设置的 `parameterValues` 不受影响。

## 架构概览

数据流：

```text
PluginConfiguration
  -> PluginExecutor.run()
  -> 插件进程 stdout JSON
  -> PluginOutput / UsageItem
  -> PluginSnapshot
  -> PluginStateStore 缓存
  -> DashboardView / OverviewView 展示
```

关键类型：

- `UsageBoardStore`：`@MainActor ObservableObject`。持有配置、快照、更新状态；管理插件调度、刷新、缓存加载、配置保存、内置插件安装、更新检查和更新安装。
- `ConfigStore`：读写配置，提供配置目录、插件目录和状态目录路径。
- `PluginExecutor`：执行插件。`.py` 文件用 `/usr/bin/env python3 <script>`，其他可执行文件直接运行。参数通过 `--usageboard-param KEY=value` 传入。默认超时 15 秒。
- `PluginMetadataParser`：读取插件前 80 行中的 `UsageBoardPlugin` 注释块并解析元数据。
- `PluginStateStore`：缓存插件成功返回的数据，用于启动展示和刷新间隔判断。
- `BundledPluginInstaller`：安装内置插件到用户插件目录。
- `UpdateChecker` / `UpdateDownloader` / `AppRelauncher`：检查更新、下载 zip、解压 app、退出后替换并重启。

## 配置模型

当前 `AppConfiguration` JSON 字段：

```json
{
  "schemaVersion": 1,
  "overviewDisplayMode": "tabs",
  "launchAtLogin": false,
  "plugins": []
}
```

当前 `PluginConfiguration` JSON 字段：

```json
{
  "stateID": "stable-cache-id",
  "name": "Example",
  "enabled": false,
  "executablePath": "/path/to/plugin.py",
  "refreshIntervalSeconds": 300,
  "metadata": null,
  "parameterValues": {}
}
```

`PluginConfiguration.id` 是运行时 UUID，不持久化；`stateID` 用于磁盘缓存。

## 插件协议

插件优先使用 Python 脚本。UsageBoard 执行 `.py` 插件时使用：

```text
/usr/bin/env python3 /path/to/plugin.py --usageboard-param KEY=value
```

插件约定：

- 不要从隐藏配置文件或环境变量读取密钥，除非这个文件路径本身是用户在 UsageBoard 中显式配置的参数。
- 密钥类参数使用 `secret` 类型。
- stdout 必须输出一个 JSON 对象。
- stderr 可用于调试；退出码非 0、超时或 stdout 非法 JSON 会让插件卡片进入失败状态。

插件元数据写在脚本前 80 行的注释块里：

```python
# UsageBoardPlugin:
# {
#   "name": "Example",
#   "icon": "https://example.com/icon.png",
#   "description": "示例插件",
#   "parameters": [
#     {
#       "name": "API_KEY",
#       "label": "Api Key",
#       "type": "secret",
#       "required": true,
#       "placeholder": "Service API Key"
#     }
#   ]
# }
# /UsageBoardPlugin
```

支持的参数类型：

- `string`
- `secret`
- `integer`
- `boolean`
- `choice`

`choice` 参数使用 `options`：

```json
{
  "name": "STAT_PERIOD",
  "label": "统计周期",
  "type": "choice",
  "required": true,
  "defaultValue": "7d",
  "options": [
    { "label": "7 天", "value": "7d" },
    { "label": "30 天", "value": "30d" }
  ]
}
```

插件 stdout JSON：

```json
{
  "updatedAt": "2026-04-29T00:00:00Z",
  "items": [
    {
      "id": "requests",
      "name": "Requests",
      "used": 1200,
      "limit": 1500,
      "displayStyle": "ratio",
      "resetAt": "2026-04-29T05:00:00Z",
      "status": "normal",
      "color": "blue"
    }
  ],
  "badge": "PRO",
  "chart": {
    "kind": "line",
    "period": "30d",
    "bucketUnit": "day",
    "buckets": [
      {
        "id": "2026-05-01",
        "label": "05-01",
        "segments": [
          {"model": "glm-4.5", "tokens": 1200}
        ]
      }
    ],
    "message": null
  }
}
```

字段说明：

- `updatedAt`：ISO 8601 时间。
- `items[].id`：稳定 ID。
- `items[].name`：显示名称。
- `items[].used` / `items[].limit`：进度按 `used / limit` 计算并限制在 `0...1`。
- `items[].displayStyle`：`percent` 或 `ratio`。
- `items[].resetAt`：可选 ISO 8601 时间，过期或缺失显示 `--`。
- `items[].status`：`normal`、`warning`、`critical`、`unknown`。
- `items[].color`：可选，支持 `blue`、`yellow`、`orange`、`red`、`green`，缺省蓝色。阈值基于**已用量百分比**：≥90% red，≥80% orange，≥60% yellow，<60% blue。
- `badge`：可选字符串，显示在插件卡片标题旁的黑色圆角徽章中（白色大写加粗文字）。用于显示订阅级别等信息。
- `chart`：可选 token 统计图，当前支持 `kind: "line"`；`bucketUnit` 为 `hour` 或 `day`，`segments` 中每项包含 `model` 和 `tokens`。
- `icon`：插件元数据中的可选字段，为图标图片 URL。显示在插件卡片标题前，无设置时显示默认拼图图标。图片通过 `NSCache` 内存缓存，首次加载后不再重复下载。

## 内置插件

当前内置插件位于 `Resources/BundledPlugins/`：

- `glm-usage-plugin.py`：智谱 / ZAI Coding Plan 用量和 token 统计。
- `deepseek-usage-plugin.py`：DeepSeek API 余额查询。
- `minimax-usage-plugin.py`：MiniMax Coding Plan 用量，API 为 `token_plan/remains`。
- `tavily-usage-plugin.py`：Tavily Search 月度用量。
- `codex-usage-plugin.py`：OpenAI Codex CLI 用量配额。
- `flowercloud-usage-plugin.py`：FlowerCloud 代理流量用量。

用户插件目录中的符号链接指向 app 包中的插件文件，因此修改内置插件源文件后，必须运行 `bash scripts/build.sh` 重新构建才能让改动生效。

## UI 尺寸参考

- 设置窗口：初始 780×560，最小 700×480，可调整大小（`UsageBoardApp.swift` `openSettings()`）。
- Menu bar popover：内容自适应高度，最大为屏幕可见高度的 2/3。

## UI 注意事项

- 主视图和 menu bar 快速预览都支持分组和标签页展示。
- 内容少时不要留下大块空白；内容多时限制最大高度并显示滚动条。
- 标签页切换时高度应随当前插件内容自适应。
- 进度条高度接近文字行高，数值显示在进度条中间。
- 用量行展示顺序和文案应稳定，避免刷新后跳动。
- 设置页插件详情使用 draft 机制：编辑只改 `@State draft`，点击”保存”后才写回 store；启用/禁用和拖拽排序即时生效。
- `PluginSnapshot` 应通过 `UsageBoardStore.makeSnapshot()` 工厂方法创建，确保 `iconURL` 等字段一致传递；`PluginExecutor` 内部直接构造 snapshot 时也需传入 `configuration.metadata?.icon`。

## 验证建议

- 改 Core 模型、解析、执行器或更新逻辑：运行 `swift test`。
- 改 SwiftUI/AppKit UI：至少运行 `swift build`；重要交互改动用 `bash scripts/build.sh` 启动 app 手动检查。
- 改内置插件：运行对应 Python 语法检查，修改源文件后需 `bash scripts/build.sh` 重建才能在 app 中生效。
