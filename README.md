# UsageBoard

macOS 菜单栏应用，聚合展示各类 API 和服务的用量配额。

## 功能

- 菜单栏常驻，点击图标快速预览用量
- 主窗口分组或标签页展示详细数据
- 插件架构，支持自定义数据源
- 自动定时刷新，磁盘缓存离线可用
- 支持开机启动
- 内置自动更新

## 内置插件

| 插件 | 用途 |
|------|------|
| 智谱 GLM | 查询智谱 Coding Plan 用量 |
| MiniMax | 查询 MiniMax Coding Plan 用量 |
| OpenAI Codex | 查询 Codex CLI 用量配额 |
| Tavily | 查询 Tavily Search 月度用量 |
| FlowerCloud | 查询 FlowerCloud 代理用量 |

## 系统要求

- macOS 13.0+
- Swift 6.3+

## 构建

```bash
swift build -c release
```

本地开发构建并启动：

```bash
bash scripts/build.sh
```

运行测试：

```bash
swift test
```

## 插件开发

插件为 Python 脚本，通过 stdout 输出 JSON 供主程序解析。在脚本开头用注释块声明参数元数据，即可在设置界面自动生成配置表单。

详见 [插件编写说明](Resources/PluginAuthoringGuide.html)。

### 输出格式

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

## 项目结构

```
Sources/
  UsageBoardCore/    核心逻辑（纯 Swift，无 SwiftUI 依赖）
  UsageBoardApp/     macOS app（SwiftUI + AppKit）
Tests/
  UsageBoardTests/   XCTest 测试
Resources/
  BundledPlugins/    内置插件
scripts/
  build.sh           本地构建并启动
  release.sh         发布到服务器
```

## 许可证

私有项目，未授权禁止使用。
