# UsageBoard 框架功能增强设计文档

日期: 2026-05-17

> 使用 `bash scripts/build.sh` 构建和重启。

## 概述

对 UsageBoard 框架进行 UI 显示增强和插件功能增强，主要包括：
1. Chart 垂直分离（移除折叠）
2. 卡片内多组 UsageItemRow 按 subtitle 分组
3. 自定义标签列（替换 reset 时间）
4. 双列卡片布局
5. ClaudeCode 使用量插件

---

## 模块 1：Chart 垂直分离

### 现状

当前 `PluginGroupView` 中 chart 位于 card 底部，带有一个 chevron 按钮控制展开/折叠 (`isChartExpanded`)。Items 和 chart 在同一 VStack 中，但 chart 被包裹在条件展开的 VStack 里，与 items 之间通过 Divider + chevron 分隔。

### 改动

**目标文件**: `Sources/UsageBoardApp/DashboardView.swift`

1. **移除 `isChartExpanded` 状态**（`@State private var isChartExpanded = true`）
2. **移除 chevron 按钮**（`Button { withAnimation { isChartExpanded.toggle() } }` 及其相关的 Divider、chevron 图标）
3. **分离 items 和 chart 为同级视图**：在 `PluginGroupView` 的 body 中，items 和 chart 变为 `VStack` 中的两个独立区块，中间用 `Divider()` 分隔。结构变为：

```
┌─ PluginName ──────────────────────┐
│ header + Divider                  │
│ items (按 subtitle 分组)          │
│ ───────────────────────────────── │
│ chart                             │
└───────────────────────────────────┘
```

4. **去除 `.padding(.bottom, snapshot.chart == nil ? 10 : 0)` 三目运算**，改为统一的 padding `.padding(.bottom, 10)`

### 涉及 Swift 视图

- `PluginGroupView` — 移除 isChartExpanded、chevron 按钮、条件展开逻辑
- `TokenUsageChartView` — 保持不变

### 验证

- chart 始终可见，不受按钮控制
- items 和 chart 之间有 Divider 分隔

---

## 模块 2：卡片内多组 UsageItemRow

### 现状

`UsageItem` 已有 `subtitle: String?` 字段。当前逻辑逐行遍历 `snapshot.items`，遇到 `subtitle != nil` 的行渲染为 `SectionHeaderView`，否则渲染为 `UsageItemRow`。

但实际上 items 中每一行都是独立的 UsageItem，subtitle 只是混在 item 列表中的"标记行"，而不是真正的分组结构。

### 改动

**目标文件**: `Sources/UsageBoardApp/DashboardView.swift` (`PluginGroupView`)  
**模型不改**（利用现有 `subtitle` 字段）

1. 将 `snapshot.items` 按 `subtitle` 分组：
   - 连续的、`subtitle` 相同的 item 归为一组
   - `subtitle == nil` 的 item 归为"默认组"
   - 每组渲染为一个独立的 section，包含组标题 + 该组下所有 UsageItemRow

2. 渲染结构：

```
┌─ PluginName ──────────────────────┐
│ SectionHeader: "工具调用"         │
│ 工具调用 (5小时) [████] 45% labels│
│                      (无 label)   │
├───────────────────────────────────┤
│ SectionHeader: "文本生成"         │
│ 文本生成 (周)    [████] 82% labels│
└───────────────────────────────────┘
```

### 分组算法

```swift
// 将 items 按 subtitle 连续相同分组
typealias ItemGroup = (title: String?, items: [UsageItem])

func groupedItems(_ items: [UsageItem]) -> [ItemGroup] {
    var groups: [ItemGroup] = []
    for item in items {
        if let last = groups.last, last.title == item.subtitle {
            groups[groups.count-1].items.append(item)
        } else {
            groups.append((title: item.subtitle, items: [item]))
        }
    }
    return groups
}
```

### 插件兼容

插件无需修改，只需在输出时合理设置 `subtitle` 字段。`subtitle` 为 `nil` 的 item 放在默认组中不显示组标题。

---

## 模块 3：自定义标签列

### 现状

`UsageItem` 末尾显示 `resetText()`（"今天 15:00"、"明天 12:00"），固定宽度 78px。

### 改动

#### 模型层

**目标文件**: `Sources/UsageBoardCore/Models.swift`

新增 `UsageItemLabel` 结构体和 `UsageItem.labels` 字段：

```swift
public struct UsageItemLabel: Codable, Equatable, Sendable {
    public var text: String
    public var color: String?  // "blue", "green", "orange", "red", "black"
    
    public init(text: String, color: String? = nil) {
        self.text = text
        self.color = color
    }
}

// 在 UsageItem 中新增:
public var labels: [UsageItemLabel]?
```

#### 渲染层

**目标文件**: `Sources/UsageBoardApp/DashboardView.swift` (`UsageItemRow`)

- `labels` 有值时：渲染标签列（每个 label 独立颜色），**替换** reset 时间
- `labels` 为 nil 或空时：回退显示原有的 reset 时间
- 每个标签固定宽度（如 60px），跨行对齐

#### 渲染效果

```
工具调用  [██████░░]  45%    123  15%  3.14
文本生成  [████████]  82%    456  20%  2.50
                            └── 固定列宽对齐 ──┘
```

#### 颜色解析

```swift
private func resolveLabelColor(_ color: String?) -> Color {
    switch color?.lowercased() {
    case "blue":   return .blue
    case "green":  return .green
    case "orange": return .orange
    case "red":    return .red
    case "black":  return .primary  // 黑色=默认文本色
    default:       return .secondary  // 无色=次级文本色
    }
}
```

### 插件输出格式

```json
{
  "id": "glm-text-5h",
  "name": "工具调用",
  "used": 45,
  "limit": 100,
  "displayStyle": "percent",
  "color": "green",
  "labels": [
    {"text": "123", "color": "blue"},
    {"text": "15%", "color": "green"},
    {"text": "3.14", "color": "orange"}
  ]
}
```

---

## 模块 4：双列卡片布局

### 现状

`grouped` 模式下，插件卡片使用 `VStack(spacing: 8)` 纵向排列，每张卡片占满整行宽度。

### 改动

**目标文件**: `Sources/UsageBoardApp/DashboardView.swift` (`DashboardView.body`)

`grouped` 模式将 `VStack` 替换为 `LazyVGrid`：

```swift
case .grouped:
    MeasuredScrollView(maxHeight: maxHeight) {
        LazyVGrid(
            columns: [
                GridItem(.flexible(), spacing: 8),
                GridItem(.flexible(), spacing: 8)
            ],
            spacing: 8
        ) {
            ForEach(enabledPlugins) { plugin in
                PluginGroupView(...)
            }
        }
        .padding(10)
    }
```

### 注意事项

- `tab` 模式保持不变
- 卡片宽度自适应（`.flexible()`），列间距 8px，行间距 8px
- 对齐方式保持 `.leading`

---

## 模块 5：ClaudeCode-usage.py 插件

### 插件元数据

```python
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "Claude Code",
#   "name@zh-Hans": "Claude Code",
#   "name@en": "Claude Code",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/claude-color.png",
#   "description": "查询 Claude Code 使用量统计和会话概览",
#   "description@zh-Hans": "查询 Claude Code 使用量统计和会话概览",
#   "description@en": "Query Claude Code usage stats and session overview",
#   "parameters": [
#     {
#       "name": "DB_PATH",
#       "label": "数据库路径",
#       "label@zh-Hans": "数据库路径",
#       "label@en": "Database Path",
#       "type": "file",
#       "required": true,
#       "defaultValue": "~/.cc-switch/cc-switch.db"
#     }
#   ]
# }
# /UsageBoardPlugin
```

### 输出结构

```
┌─ Claude Code ─── ●3个活跃 ●7个今日 ── 11:35 ─┐
│                                                 │
│ 今日       [████████░░]  78%    1.2M  0.8M  65% │
│  claude-opus-4-7  [████]  45%    123K  456K  58%│
│  claude-sonnet-4-6 [███]  30%    89K   234K  62%│
│  claude-haiku-4-5  [█]    10%    12K   45K   55%│
│                                                 │
│ 近7天      [████████░░]  78%    8.5M  5.2M  60% │
│  claude-opus-4-7  [████]  45%    890K  1.2M  55%│
│  claude-sonnet-4-6 [███]  30%    567K  890K  58%│
│  claude-haiku-4-5  [█]    10%    89K   234K  52%│
│                                                 │
│ 近30天     [████████░░]  78%    35M   22M   58% │
│  claude-opus-4-7  [████]  45%    3.5M  4.2M  53%│
│  claude-sonnet-4-6 [███]  30%    2.1M  3.5M  56%│
│  claude-haiku-4-5  [█]    10%    456K  1.2M  50%│
│                                                 │
│ ─────────────────────────────────────────────── │
│ 标题: "近30日趋势" (无图例)                       │
│ [Chart: 30日 token 用量折线图]                    │
│  hover 时显示各曲线当前值                          │
└─────────────────────────────────────────────────┘
```

### 模型改动：PluginOutput / PluginSnapshot 新增 sessions 字段

**目标文件**: `Sources/UsageBoardCore/Models.swift`

新增 `SessionInfo` 结构体和 `PluginOutput` / `PluginSnapshot` 中的 `sessions` 字段：

```swift
public struct SessionInfo: Codable, Equatable, Sendable {
    public var active: Int   // 活跃会话数（2小时内）
    public var today: Int    // 今日会话数
}

// PluginOutput 新增:
public var sessions: SessionInfo?

// PluginSnapshot 新增:
public var sessions: SessionInfo?
```

该字段从插件 JSON 输出中自动解码，供 header 渲染使用。

### header 渲染逻辑

**目标文件**: `Sources/UsageBoardApp/DashboardView.swift` (`PluginGroupView.header`)

```swift
private var header: some View {
    HStack(spacing: 8) {
        BrandTile(iconURL: snapshot.iconURL, fallbackName: snapshot.displayName, size: 22)
        Text(snapshot.displayName)
            .font(UB.Font.cardTitle)
            .lineLimit(1)
        if let badge = snapshot.badge {
            PlanTag(text: badge)
        }
        // 会话指示器
        if let sessions = snapshot.sessions {
            SessionIndicator(count: sessions.active, color: .green, label: "活跃")
            SessionIndicator(count: sessions.today, color: .blue, label: "今日")
        }
        ...
    }
}
```

`SessionIndicator` 是一个新的轻量 View，显示 `●N个活跃` / `●N个今日` 格式。

### 会话计数数据来源

**数据来源**: `proxy_request_logs` 表的 `session_id` 字段

```sql
-- 活跃会话（2小时内有请求）
SELECT COUNT(DISTINCT session_id) FROM proxy_request_logs 
WHERE app_type = 'claude' AND session_id IS NOT NULL 
AND created_at >= (strftime('%s', 'now') - 7200)

-- 今日会话
SELECT COUNT(DISTINCT session_id) FROM proxy_request_logs 
WHERE app_type = 'claude' AND session_id IS NOT NULL 
AND created_at >= strftime('%s', 'date('now'))
```

**显示格式**: `●3个活跃 ●7个今日`

#### header 渲染逻辑

```swift
// 解析 badge 为特殊格式
// "sessions:3:7" → 活跃3个，今日7个
// 渲染在 header 中 name 之后、stateView 之前
```

**color 规则**:
- 活跃会话（绿色 `●`）
- 今日会话（蓝色 `●`）

### Items 输出

每时间段三项：时间段总计 + top 3 模型

**数据来源**: `usage_daily_rollups` 或 `proxy_request_logs`

```sql
-- 每个时间段按模型聚合
SELECT model,
       SUM(input_tokens) as total_input,
       SUM(output_tokens) as total_output,
       CASE WHEN SUM(input_tokens + cache_creation_tokens) > 0 
            THEN CAST(SUM(cache_read_tokens) AS REAL) / SUM(input_tokens + cache_creation_tokens) * 100 
            ELSE 0 END as cache_rate
FROM proxy_request_logs
WHERE app_type = 'claude' AND created_at >= ?
GROUP BY model
ORDER BY (total_input + total_output) DESC
LIMIT 3
```

**items 结构**:
- 每个时间段第一行：时间段名（"今日"、"近7天"、"近30天"），显示该时间段总输入token + 总输出token + 总cache率
- 后面每行：模型名 + 该模型的输入token、输出token、cache率

**labels 颜色规则**:
| label | color |
|-------|-------|
| 输入 token | blue |
| 输出 token | orange |
| cache 率 | green (≥90%), primary (80-90%), red (<80%) |

**进度条颜色**: green

### Chart 输出

**数据来源**: `usage_daily_rollups` 表

```sql
SELECT date, model, 
       SUM(input_tokens + output_tokens) as total_tokens
FROM usage_daily_rollups
WHERE app_type = 'claude'
  AND date >= date('now', '-30 days')
GROUP BY date, model
ORDER BY date
```

**Chart 属性**:
- `title`: "近30日趋势"
- `showLegend`: false（不显示图例）
- `kind`: "line"
- `bucketUnit`: "day"
- 包含总 token 和每个模型的 token 序列

### Swift 端 Chart 增强

**目标文件**: `Sources/UsageBoardApp/DashboardView.swift` (`TokenUsageChartView`, `TokenLineChartPlot`)

1. **Chart 标题支持**: 
   - `PluginChart` 新增 `title: String?`
   - 在 `TokenUsageChartView` 中，chart 顶部（`LazyVGrid` 图例上方）显示标题文字
   - 标题字体: `.system(size: 13, weight: .semibold)`

2. **图例控制**:
   - `PluginChart` 新增 `showLegend: Bool?`（默认 true）
   - 设为 false 时隐藏 `LazyVGrid` 图例卡片
   - **hover 仍然显示**所有曲线当前选中时间的值（hover overlay 不受影响）

3. **模型层新增**:
   ```swift
   // PluginChart 新增
   public var title: String?
   public var showLegend: Bool?
   ```

### 弧线平滑插值

**目标文件**: `TokenLineChartPlot.lineSeries(in:)`

当前折线使用 `Path.addLine(to:)` 绘制直线段。改为通过 Catmull-Rom 转 cubic Bezier 实现平滑：

```swift
// 输入: [CGPoint] 数据点序列
// 输出: 平滑曲线 Path

func smoothPath(points: [CGPoint]) -> Path {
    Path { path in
        guard points.count >= 2 else { return }
        path.move(to: points[0])
        for i in 1..<points.count {
            let prev = points[i - 1]
            let curr = points[i]
            
            // Catmull-Rom → Cubic Bezier:
            // 控制点1 = curr + (prev - prevPrev) / 6
            // 控制点2 = prev + (next - curr) / 6
            
            let prevPrev = i >= 2 ? points[i - 2] : prev
            let next = i + 1 < points.count ? points[i + 1] : curr
            
            let cp1 = CGPoint(
                x: prev.x + (next.x - prevPrev.x) / 6,
                y: prev.y + (next.y - prevPrev.y) / 6
            )
            let cp2 = CGPoint(
                x: curr.x - (next - curr).x / 6,
                y: curr.y - (next - curr).y / 6
            )
            
            path.addCurve(to: curr, control1: cp1, control2: cp2)
        }
    }
}
```

保持 fill area 也用平滑 path。

---

## 插件数据流

```
┌─────────────┐     ┌────────────────┐     ┌──────────────────┐
│ cc-switch   │     │ ClaudeCode-    │     │ PluginGroupView  │
│ SQLite DB   │──►  │ usage.py       │──►  │ (SwiftUI 渲染)   │
│             │     │ (Python 插件)   │     │                  │
│ proxy_      │     │                │     │ • header(会话数)  │
│ request_    │     │ • SQL 查询      │     │ • section分组    │
│ logs        │     │ • 聚合统计      │     │ • UsageItemRow   │
│             │     │ • 构建items/    │     │   + 标签列       │
│ usage_      │     │   chart        │     │ • chart(曲线图)  │
│ daily_      │     │ • JSON stdout  │     │                  │
│ rollups     │     └────────────────┘     └──────────────────┘
└─────────────┘
```

---

## 涉及修改的文件清单

| 文件 | 改动内容 |
|------|---------|
| `Sources/UsageBoardCore/Models.swift` | 新增 `UsageItemLabel`、`UsageItem.labels`、`SessionInfo`、`PluginOutput.sessions`、`PluginSnapshot.sessions`、`PluginChart.title`、`PluginChart.showLegend` |
| `Sources/UsageBoardApp/DashboardView.swift` | Chart 垂直分离、Subtitle 分组渲染、标签列渲染、双列布局、SessionIndicator 视图、Chart 标题/图例控制、平滑曲线插值 |
| `Resources/BundledPlugins/ClaudeCode-usage.py` | 新建插件 |

---

## 测试

### Models
- `UsageItemLabel` 编解码测试
- `PluginChart` 新字段兼容性测试（nil 默认值）

### UI
- 双列布局在不同数量的插件下是否正确
- chart 始终可见
- 标签列对齐、颜色
- header 会话数 badge

### 插件
- DB_PATH 参数
- 三个时间段的数据聚合
- session 计数
- chart 构建
- cc-switch DB 不存在时的降级处理（返回错误信息）

---

## 降级处理

| 异常场景 | 处理方式 |
|---------|---------|
| cc-switch DB 不存在 | 返回 `PluginOutput` 带 error 信息："未检测到 cc-switch 数据库，请先安装 cc-switch" |
| `proxy_request_logs` 表无数据 | items 返回空列表，chart 返回 message："暂无使用数据" |
| `session_id` 全为 NULL | badge 不显示会话计数，只显示插件名 |
| DB 查询异常 | 捕获异常，返回带 error 信息的 PluginOutput |
