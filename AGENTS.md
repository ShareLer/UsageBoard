# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 基本约定

- 默认使用中文沟通，表达简洁，结论可复制。
- 改动保持小而清晰，每处改动都应对应当前请求。
- 不读取、打印或提交真实 API Key、令牌或私有配置。
- 不擅自改无关代码；发现无关问题可以说明，但不要顺手处理。
- 每次修改 app 代码后都重新构建并本地启动 app 验证，如已有运行中的 app 进程则先关闭。

## 常用命令

```bash
swift build                                          # 构建
swift build -c release                               # Release 构建
swift test                                           # 运行全部测试
swift test --filter UsageBoardTests.testProgressHandlesBoundsAndRatio  # 运行单个测试
```

打包本地测试 app：

```bash
cp .build/release/UsageBoard dist/UsageBoard.app/Contents/MacOS/UsageBoard
codesign --force --deep --sign - dist/UsageBoard.app
```

发布新版本：`bash scripts/release.sh`（自动版本号+1、构建、签名、打包、上传到服务器）。

## 项目结构

- `Sources/UsageBoardCore`：核心逻辑（纯 Swift，无 SwiftUI 依赖）。
- `Sources/UsageBoardApp`：SwiftUI macOS app（menu bar popover、主窗口 Dashboard、设置界面）。
- `Tests/UsageBoardTests`：XCTest 测试。
- `Resources/BundledPlugins/`：内置 Python 插件，首次启动自动安装到用户插件目录。
- `Resources/PluginAuthoringGuide.html`：插件编写说明，从设置界面打开。
- `scripts/release.sh`：发布脚本（构建、签名、打包、上传、远程清理）。
- `dist/UsageBoard.app`：本地测试用 app bundle。

AGENTS.md 内容与 CLAUDE.md 相同，修改任一文件后需同步另一个。

## 架构

### 数据流

```
PluginConfiguration (持久化配置)
       ↓
PluginExecutor.run() → 启动子进程执行插件脚本 → 解析 stdout JSON
       ↓
PluginSnapshot (运行时状态: idle/loading/ready/failed)
       ↓
PluginStateStore → 缓存到磁盘 ~/Library/Application Support/UsageBoard/states/
       ↓
DashboardView / OverviewView → SwiftUI 展示
```

### 关键层次

- **UsageBoardStore**（App 层）：`@MainActor ObservableObject`，持有 `AppConfiguration` 和 `[UUID: PluginSnapshot]`。管理插件调度（定时刷新）、缓存加载、配置持久化。所有 UI 通过 `@ObservedObject var store` 访问数据。
- **ConfigStore**（Core 层）：读写 JSON 配置文件 `~/Library/Application Support/UsageBoard/config.json`。
- **PluginExecutor**（Core 层）：`Sendable` struct，`run()` 同步执行子进程并返回 `PluginSnapshot`。`.py` 脚本自动使用 `python3` 前缀。有超时机制（默认 15 秒）。
- **PluginStateStore**（Core 层）：按 `stateID` 缓存 `PluginCachedState` 到独立 JSON 文件，用于判断是否需要刷新。
- **PluginMetadataParser**（Core 层）：从插件脚本前 80 行的 `# UsageBoardPlugin:` / `# /UsageBoardPlugin` 注释块解析元数据。

### Swift 并发

项目使用 Swift 6 strict concurrency（`swiftLanguageModes: [.v6]`）。Core 层类型均为 `Sendable`，Core 的 Foundation import 使用 `@preconcurrency`。App 层的 `UsageBoardStore` 和 `AppDelegate` 标记 `@MainActor`。插件执行在 `Task.detached(priority: .utility)` 中运行。

### JSON 约定

所有 JSON 编解码通过 `UsageBoardJSON` 统一配置：ISO 8601 日期、pretty-printed + sorted keys 输出。所有 `Codable` 模型的 `init(from:)` 对缺失字段使用合理默认值而非崩溃。

### App 运行模式

`AppDelegate` 管理 menu bar status item + NSPopover 弹出总览，设置界面通过独立 `NSWindow` 打开。`UsageBoardApplication.body` 仅提供 `Settings` scene。

### 自动更新

版本检查 URL 硬编码在 `UsageBoardStore` 中。`UpdateChecker` 从远程 `version.json` 比对版本号。更新流程：`UpdateDownloader` 下载 zip → `ditto -x -k` 解压 → `AppRelauncher` 生成临时 shell 脚本等待 app 退出后替换 bundle、重签名、重启。

### 插件设置编辑

插件详细配置使用 draft 机制：选中插件时将配置拷贝到 `@State draft`，编辑绑定指向 draft 而非 store。仅点"保存"时写回 store 并持久化。启用/禁用 toggle 和拖拽排序直接操作 store（即时生效）。

## 插件协议

- 插件统一优先使用 Python 脚本。
- 主程序执行 `.py` 插件时使用 `python3 <script>`。
- 插件配置项通过命令行参数传入：`--usageboard-param KEY=value`。
- 插件不应读取本机隐藏配置文件或环境变量中的密钥；API Key 应通过 UsageBoard 设置界面配置。
- 插件 stdout 必须输出主程序可解析的 JSON：

```json
{
  "schemaVersion": 1,
  "updatedAt": "2026-04-29T00:00:00Z",
  "items": [
    {
      "id": "requests",
      "name": "Requests",
      "used": 1200,
      "limit": 1500,
      "displayStyle": "percent",
      "resetAt": "2026-04-29T00:05:00Z",
      "status": "normal"
    }
  ]
}
```

### 插件元数据

插件脚本开头可用固定注释块声明配置项：

```python
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "Example",
#   "description": "示例插件",
#   "parameters": [
#     {
#       "name": "API_KEY",
#       "label": "Api Key",
#       "type": "string",
#       "required": true
#     }
#   ]
# }
# /UsageBoardPlugin
```

支持的参数类型：`string`、`secret`、`integer`、`boolean`、`choice`。

`choice` 参数使用 `options`：

```json
{
  "name": "PROVIDER",
  "label": "Provider",
  "type": "choice",
  "required": true,
  "defaultValue": "GLM",
  "options": [
    { "label": "GLM", "value": "GLM" },
    { "label": "ZAI", "value": "ZAI" }
  ]
}
```

## UI 注意事项

- 主界面和 menu bar 快速预览都应按内容高度自适应。
- 内容少时不要留下大块空白。
- 内容过多时限制最大高度并显示滚动条。
- 用量行展示顺序和文案应稳定，避免刷新后跳动。
