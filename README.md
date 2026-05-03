# UsageBoard

UsageBoard 是一个原生 macOS 菜单栏应用，用于聚合展示 API、模型服务、搜索服务、代理服务等各类用量配额。每个数据源都以插件形式存在，主程序负责定时执行插件、解析 stdout JSON，并以进度条展示用量。

## 功能特性

- 菜单栏常驻，点击图标打开快速预览。
- 支持分组展示和标签页展示。
- 支持手动刷新、定时刷新、单卡片刷新、退出按钮。
- 插件化用量查询，插件可独立配置刷新间隔和参数。
- 插件图标支持，从元数据配置加载远程图片并缓存。
- 订阅级别徽章显示（黑底白字圆角标签）。
- 插件设置界面从脚本元数据自动生成参数表单。
- 新增插件默认不启用，启用前会检查必填参数。
- 插件数据按 `stateID` 缓存到磁盘，启动后可展示上次成功数据。
- 首次启动会把内置插件安装到用户插件目录。
- 设置页支持开机启动、插件拖拽排序、插件帮助文档、检查更新和在线更新。
- 用量展示支持百分比或数字占比，支持重置时间、进度条颜色和可选 token 统计图。

## 截图

<table>
  <tr>
    <td><img src="Screenshots/grouped.png" alt="分组展示" width="360" /></td>
    <td><img src="Screenshots/tabs.png" alt="标签页展示" width="360" /></td>
  </tr>
  <tr>
    <td align="center">分组展示</td>
    <td align="center">标签页展示</td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="Screenshots/settings.png" alt="插件设置" width="540" /></td>
  </tr>
  <tr>
    <td colspan="2" align="center">插件设置</td>
  </tr>
</table>

## 内置插件

| 插件 | 脚本 | 用途 |
| --- | --- | --- |
| 智谱 | `glm-usage-plugin.py` | 查询智谱 / ZAI Coding Plan 用量和 token 统计 |
| MiniMax | `minimax-usage-plugin.py` | 查询 MiniMax Coding Plan 用量 |
| DeepSeek | `deepseek-usage-plugin.py` | 查询 DeepSeek 账户余额 |
| Tavily | `tavily-usage-plugin.py` | 查询 Tavily Search 月度用量 |
| Codex | `codex-usage-plugin.py` | 查询 OpenAI Codex CLI 用量配额 |
| FlowerCloud | `flowercloud-usage-plugin.py` | 查询 FlowerCloud 代理流量用量 |

内置插件源文件位于 [Resources/BundledPlugins](Resources/BundledPlugins)。打包后它们会位于 app 包的 `Contents/Resources/Plugins/`。

## 运行时目录

UsageBoard 默认使用：

```text
~/Library/Application Support/UsageBoard/
```

目录内容：

- `config.json`：主配置文件。
- `plugins/`：用户插件目录。添加插件时文件选择器默认打开这里。
- `states/`：插件数据缓存目录。

当前实现会在启动时向 `plugins/` 目录创建内置插件的同名符号链接，来源是 app 包内的 `Contents/Resources/Plugins/`，开发运行时则 fallback 到项目的 `Resources/BundledPlugins/`。

## 配置文件

主配置 JSON 当前结构：

```json
{
  "schemaVersion": 1,
  "overviewDisplayMode": "tabs",
  "launchAtLogin": false,
  "plugins": [
    {
      "stateID": "stable-cache-id",
      "name": "Tavily",
      "enabled": false,
      "executablePath": "~/Library/Application Support/UsageBoard/plugins/tavily-usage-plugin.py",
      "refreshIntervalSeconds": 300,
      "metadata": null,
      "parameterValues": {
        "API_KEY": ""
      }
    }
  ]
}
```

说明：

- `overviewDisplayMode` 支持 `grouped` 和 `tabs`。
- `launchAtLogin` 控制开机启动。
- `plugins[].stateID` 是插件缓存 ID，会持久化。
- `plugins[].enabled` 为 `false` 时不执行插件。
- `plugins[].metadata` 通常由插件脚本头部注释块解析生成。
- `plugins[].parameterValues` 保存设置界面填写的插件参数。

## 插件开发

插件推荐使用 Python 脚本。主程序执行 `.py` 插件时使用：

```text
/usr/bin/env python3 /path/to/plugin.py --usageboard-param KEY=value
```

插件必须向 stdout 输出 UsageBoard 可解析的 JSON。stderr 可用于调试；退出码非 0、超时或 stdout 非法 JSON 都会显示为插件错误。

更完整的说明见 [插件编写说明](Resources/PluginAuthoringGuide.html)。

### 参数元数据

在脚本开头放入 `UsageBoardPlugin` 注释块，UsageBoard 会读取它并生成设置表单：

```python
#!/usr/bin/env python3
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
#     },
#     {
#       "name": "STAT_PERIOD",
#       "label": "统计周期",
#       "type": "choice",
#       "required": true,
#       "defaultValue": "7d",
#       "options": [
#         {"label": "7 天", "value": "7d"},
#         {"label": "30 天", "value": "30d"}
#       ]
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

插件读取参数示例：

```python
def parse_usageboard_params(argv):
    values = {}
    index = 0
    while index < len(argv):
        if argv[index] == "--usageboard-param" and index + 1 < len(argv):
            key_value = argv[index + 1]
            if "=" in key_value:
                key, value = key_value.split("=", 1)
                values[key] = value
            index += 2
        else:
            index += 1
    return values
```

### 返回数据格式

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
          {"model": "glm-4.5", "tokens": 1200},
          {"model": "glm-4.6", "tokens": 800}
        ]
      }
    ],
    "message": null
  }
}
```

字段说明：

- `updatedAt`：插件数据更新时间，ISO 8601 格式。
- `items[].id`：用量项目稳定 ID。
- `items[].name`：界面显示名称。
- `items[].used` / `items[].limit`：已用量和总额度。
- `items[].displayStyle`：`percent` 显示百分比，`ratio` 显示数字占比。
- `items[].resetAt`：可选重置时间，ISO 8601 格式。
- `items[].status`：`normal`、`warning`、`critical`、`unknown`。
- `items[].color`：可选进度条颜色，支持 `blue`、`yellow`、`orange`、`red`、`green`，缺省蓝色。
- `badge`：可选字符串，显示在插件卡片标题旁的黑色圆角徽章中（白色大写加粗文字）。
- `chart`：可选 token 统计图，当前支持 `kind: "line"`。
- `chart.period`：统计周期标识，例如 `7d`、`30d`。
- `chart.bucketUnit`：时间桶单位，支持 `hour` 或 `day`。
- `chart.buckets[].segments[]`：每个时间桶的模型分段，包含 `model` 和 `tokens`。
- `chart.message`：可选提示文案，统计数据为空或不可用时显示。

内置智谱插件提供 `STAT_PERIOD` 参数，支持 `7d`、`30d`。插件统一使用国内站 API 查询，兼容智谱和 ZAI 的 Coding Plan Key；旧配置中残留的 `PROVIDER` 参数会被忽略。

## 系统要求

运行：

- macOS 13.0 或更高版本
- 系统可用 `python3`，用于执行 Python 插件

开发：

- Xcode
- Swift 6.3 toolchain

## 构建与测试

Debug 构建：

```bash
swift build
```

运行测试：

```bash
swift test
```

Release 构建：

```bash
swift build -c release
```

本地构建、签名并启动 `dist/UsageBoard.app`：

```bash
bash scripts/build.sh
```

`scripts/build.sh` 会停止正在运行的 UsageBoard，构建 release，复制二进制和内置插件到 `dist/UsageBoard.app`，通过 PlistBuddy 向 Info.plist 注入更新检查 URL，执行 ad-hoc 签名，然后启动 app。可通过 `UB_UPDATE_CHECK_URL` 环境变量自定义更新检查地址。

## 发布

生成并上传新版本：

```bash
bash scripts/release.sh
```

指定版本：

```bash
bash scripts/release.sh 0.1.6
```

发布脚本会：

1. 从 `dist/UsageBoard.app/Contents/Info.plist` 读取当前版本。
2. 生成新版本号。
3. 自动从上个 release tag 到 HEAD 的提交生成更新说明（也可通过第二个参数手动传入）。
4. 构建 release。
5. 复制二进制和内置插件。
6. 通过 PlistBuddy 向 Info.plist 注入更新检查 URL。
7. 重新签名并验证 app。
8. 生成 `UsageBoard-<version>.zip`。
9. 生成 `version.json`。
10. 上传到脚本中配置的服务器路径。
11. 清理远端旧 zip。

当前发布产物示例：

- `dist/UsageBoard-0.1.8.zip`
- `dist/version.json`

## 项目结构

```text
Sources/
  UsageBoardCore/       配置、模型、插件执行、缓存、更新等核心逻辑
  UsageBoardApp/        SwiftUI + AppKit macOS app
Tests/
  UsageBoardTests/      XCTest 单元测试
Resources/
  BundledPlugins/       内置 Python 插件
  PluginAuthoringGuide.html
  UsageBoard.icns
scripts/
  build.sh              本地构建、签名、启动
  release.sh            发布脚本
dist/
  UsageBoard.app        本地测试 app bundle
```

## 许可证

[MIT](LICENSE)
