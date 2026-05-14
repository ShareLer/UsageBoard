import AppKit
import SwiftUI
import UsageBoardCore

struct DashboardView: View {
    @ObservedObject var store: UsageBoardStore
    var mode: DisplayMode

    private var maxHeight: CGFloat {
        (NSScreen.main?.visibleFrame.height ?? 800) * 2 / 3
    }

    private var enabledPlugins: [PluginConfiguration] {
        store.configuration.plugins.filter(\.enabled)
    }

    private var strings: AppLocalization {
        AppLocalization(language: store.activeLanguage)
    }

    var body: some View {
        Group {
            if enabledPlugins.isEmpty {
                EmptyPluginsView(language: store.activeLanguage)
            } else {
                switch mode {
                case .grouped:
                    MeasuredScrollView(maxHeight: maxHeight) {
                        VStack(spacing: 8) {
                            ForEach(enabledPlugins) { plugin in
                                PluginGroupView(
                                    snapshot: store.snapshot(for: plugin),
                                    language: store.activeLanguage,
                                    nextRefreshAt: store.nextRefreshAt[plugin.id]
                                ) {
                                    store.refresh(pluginID: plugin.id, force: true)
                                }
                            }
                        }
                        .padding(10)
                    }
                    .background(UB.Canvas.canvasBackground)
                case .tabs:
                    VStack(spacing: 0) {
                        ScrollViewReader { proxy in
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 6) {
                                    ForEach(enabledPlugins) { plugin in
                                        Button {
                                            store.selectedTabID = plugin.id
                                        } label: {
                                            Text(store.snapshot(for: plugin).displayName)
                                                .font(.callout.weight(store.selectedTabID == plugin.id ? .semibold : .regular))
                                                .foregroundStyle(store.selectedTabID == plugin.id ? .primary : .secondary)
                                                .padding(.horizontal, 10)
                                                .padding(.vertical, 4)
                                                .background(
                                                    RoundedRectangle(cornerRadius: 6)
                                                        .fill(store.selectedTabID == plugin.id ? Color(nsColor: .selectedControlColor) : .clear)
                                                )
                                        }
                                        .buttonStyle(.plain)
                                        .id(plugin.id)
                                    }
                                }
                                .padding(.horizontal, 10)
                            }
                            .padding(.vertical, 6)
                            .onAppear {
                                scrollToSelectedTab(with: proxy)
                            }
                            .onChange(of: store.selectedTabID) { _ in
                                scrollToSelectedTab(with: proxy)
                            }
                            .onChange(of: enabledPlugins.map(\.id)) { _ in
                                scrollToSelectedTab(with: proxy)
                            }
                        }
                        Divider()
                        if let plugin = selectedPlugin {
                            PluginGroupView(
                                snapshot: store.snapshot(for: plugin),
                                language: store.activeLanguage,
                                nextRefreshAt: store.nextRefreshAt[plugin.id]
                            ) {
                                store.refresh(pluginID: plugin.id, force: true)
                            }
                            .padding(10)
                        }
                    }
                }
            }
        }
        .onAppear {
            ensureSelectedTab()
        }
        .onChange(of: enabledPlugins.map(\.id)) { _ in
            ensureSelectedTab()
        }
        .toolbar {
            Button {
                store.refreshAll()
            } label: {
                Label(strings.text(.refresh), systemImage: "arrow.clockwise")
            }
            QuitButton(language: store.activeLanguage)
        }
    }

    private var selectedPlugin: PluginConfiguration? {
        if let selectedTabID = store.selectedTabID,
           let plugin = enabledPlugins.first(where: { $0.id == selectedTabID }) {
            return plugin
        }
        return enabledPlugins.first
    }

    private func ensureSelectedTab() {
        guard !enabledPlugins.isEmpty else {
            store.selectedTabID = nil
            return
        }
        if let selectedTabID = store.selectedTabID,
           enabledPlugins.contains(where: { $0.id == selectedTabID }) {
            return
        }
        store.selectedTabID = enabledPlugins.first?.id
    }

    private func scrollToSelectedTab(with proxy: ScrollViewProxy) {
        guard let selectedTabID = store.selectedTabID else { return }
        withAnimation(.easeInOut(duration: 0.15)) {
            proxy.scrollTo(selectedTabID, anchor: .center)
        }
    }
}

struct EmptyPluginsView: View {
    var language: AppLanguage
    private var strings: AppLocalization {
        AppLocalization(language: language)
    }

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "puzzlepiece.extension")
                .font(.system(size: 40))
                .foregroundStyle(.secondary)
            Text(strings.text(.noPluginsTitle))
                .font(.headline)
            Text(strings.text(.noPluginsDescription))
                .font(.callout)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
    }
}

struct OverviewView: View {
    @ObservedObject var store: UsageBoardStore

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                AppIconSquircle(size: 22)
                Text("UsageBoard")
                    .font(UB.Font.popoverTitle)
                    .tracking(-0.1)
                Spacer()
                Button {
                    store.refreshAll()
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 13, weight: .medium))
                        .frame(width: 24, height: 24)
                }
                .buttonStyle(.borderless)
                SettingsButton(iconSize: 13, buttonSize: 24)
                QuitButton(language: store.activeLanguage, iconSize: 13, buttonSize: 24)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)

            Divider()

            DashboardView(store: store, mode: store.configuration.overviewDisplayMode)
        }
    }
}

struct MeasuredScrollView<Content: View>: View {
    var maxHeight: CGFloat
    var minHeight: CGFloat = 100
    @ViewBuilder var content: Content
    @State private var contentHeight: CGFloat = 0

    var body: some View {
        ScrollView {
            content
                .background(
                    GeometryReader { proxy in
                        Color.clear.preference(key: ContentHeightKey.self, value: proxy.size.height)
                    }
                )
        }
        .frame(height: contentHeight > 0 ? min(max(contentHeight, minHeight), maxHeight) : minHeight)
        .onPreferenceChange(ContentHeightKey.self) { height in
            if height > 0, abs(contentHeight - height) > 1 {
                contentHeight = height
            }
        }
    }
}

private struct ContentHeightKey: PreferenceKey {
    static let defaultValue: CGFloat = 0

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

struct PluginGroupView: View {
    var snapshot: PluginSnapshot
    var language: AppLanguage
    var nextRefreshAt: Date?
    var onRefresh: (() -> Void)?
    @State private var isChartExpanded = false
    private var strings: AppLocalization {
        AppLocalization(language: language)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 10) {
                header

                Divider()

                if case .failed(let message) = snapshot.state {
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(.red)
                            .font(.callout)
                        Text(message)
                            .font(.callout)
                            .foregroundStyle(.red)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .fixedSize(horizontal: false, vertical: true)
                            .textSelection(.enabled)
                    }
                    .padding(.vertical, 8)
                } else if snapshot.items.isEmpty {
                    Text(strings.text(.noUsageData))
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 18)
                } else {
                    VStack(spacing: 8) {
                        ForEach(snapshot.items) { item in
                            UsageItemRow(item: item, language: language)
                        }
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.top, 10)
            .padding(.bottom, snapshot.chart == nil ? 10 : 0)

            if let chart = snapshot.chart {
                VStack(spacing: 0) {
                    Button {
                        withAnimation(.easeInOut(duration: 0.25)) {
                            isChartExpanded.toggle()
                        }
                    } label: {
                        VStack(spacing: 0) {
                            Divider()
                                .padding(.top, 8)
                            Image(systemName: isChartExpanded ? "chevron.up" : "chevron.down")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(.tertiary)
                                .frame(maxWidth: .infinity, minHeight: 22)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .help(isChartExpanded ? strings.text(.collapseTokenStats) : strings.text(.expandTokenStats))

                    if isChartExpanded {
                        TokenUsageChartView(chart: chart, language: language)
                            .padding(.horizontal, 12)
                            .padding(.top, 8)
                            .padding(.bottom, 8)
                    }
                }
            }
        }
        .background(UB.Canvas.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: UB.Radius.card, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: UB.Radius.card, style: .continuous)
                .stroke(UB.Canvas.separator.opacity(0.7), lineWidth: 0.5)
        )
        .shadow(color: Color.black.opacity(0.02), radius: 1, y: 1)
    }

    private var header: some View {
        HStack(spacing: 8) {
            BrandTile(iconURL: snapshot.iconURL, fallbackName: snapshot.displayName, size: 22)
            Text(snapshot.displayName)
                .font(UB.Font.cardTitle)
                .lineLimit(1)
            if let badge = snapshot.badge {
                PlanTag(text: badge)
            }
            if case .failed = snapshot.state {
                Text(language == .en ? "Error" : "错误")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.red)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 1)
                    .background(Color.red.opacity(0.10))
                    .clipShape(Capsule())
            }
            Spacer()
            stateView
        }
    }

    @ViewBuilder
    private var stateView: some View {
        switch snapshot.state {
        case .idle:
            Text(strings.text(.waitingRefresh))
                .font(UB.Font.countdown)
                .foregroundStyle(.secondary)
        case .loading:
            ProgressView()
                .controlSize(.small)
        case .ready, .failed:
            CountdownLabel(target: nextRefreshAt)
            Button {
                onRefresh?()
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 11))
                    .frame(width: 20, height: 20)
            }
            .buttonStyle(.borderless)
            .foregroundStyle(.secondary)
        }
    }

}

struct UsageItemRow: View {
    var item: UsageItem
    var language: AppLanguage

    var body: some View {
        HStack(spacing: 12) {
            Text(item.name)
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.tail)
                .frame(width: 92, alignment: .leading)

            UsageProgressBar(value: item.progress, label: item.displayValue(), color: item.color)
                .frame(height: 18)
                .layoutPriority(1)

            Text(item.resetText(language: language))
                .font(.system(size: 11))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .foregroundStyle(.tertiary)
                .frame(width: 78, alignment: .trailing)
        }
        .padding(.vertical, 2)
    }
}

struct TokenUsageChartView: View {
    var chart: PluginChart
    var language: AppLanguage
    @State private var selectedSeries: String?
    private var strings: AppLocalization {
        AppLocalization(language: language)
    }

    private var series: [TokenChartSeries] {
        var output = [
            TokenChartSeries(
                name: strings.text(.totalTokenUsage),
                color: .blue,
                values: chart.buckets.map(\.total)
            )
        ]
        output.append(contentsOf: modelSummaries.map { summary in
            TokenChartSeries(
                name: strings.usageSuffix(for: summary.name),
                color: summary.color,
                values: chart.buckets.map { bucket in
                    bucket.segments.first(where: { $0.model == summary.name })?.tokens ?? 0
                }
            )
        })
        return output
    }

    private var visibleSeries: [TokenChartSeries] {
        let filtered = series.filter { $0.values.contains(where: { $0 > 0 }) }
        guard let selectedSeries else { return filtered }
        return filtered.filter { $0.name == selectedSeries }
    }

    private var modelSummaries: [TokenModelSummary] {
        var totals: [String: Double] = [:]
        for bucket in chart.buckets {
            for segment in bucket.segments {
                totals[segment.model, default: 0] += max(segment.tokens, 0)
            }
        }
        return totals
            .filter { $0.key != "总计" }
            .sorted(by: { lhs, rhs in
                if lhs.value == rhs.value {
                    return lhs.key < rhs.key
                }
                return lhs.value > rhs.value
            })
            .enumerated()
            .map { index, element in
                TokenModelSummary(name: element.key, total: element.value, color: modelColor(at: index))
            }
    }

    private var totalTokens: Double {
        chart.buckets.reduce(0) { $0 + $1.total }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if chart.buckets.contains(where: { !$0.segments.isEmpty }) {
                LazyVGrid(
                    columns: [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)],
                    alignment: .leading,
                    spacing: 8
                ) {
                    Button {
                        selectedSeries = selectedSeries == strings.text(.totalTokenUsage) ? nil : strings.text(.totalTokenUsage)
                    } label: {
                        TokenMetricView(
                            title: strings.text(.totalTokenUsage),
                            value: totalTokens,
                            color: .blue,
                            isSelected: selectedSeries == strings.text(.totalTokenUsage)
                        )
                        .contentShape(RoundedRectangle(cornerRadius: 6))
                    }
                    .buttonStyle(.plain)
                    .help(selectedSeries == strings.text(.totalTokenUsage) ? strings.text(.showAllLines) : strings.text(.showOnlyTotalUsage))

                    ForEach(modelSummaries) { summary in
                        Button {
                            let seriesName = strings.usageSuffix(for: summary.name)
                            selectedSeries = selectedSeries == seriesName ? nil : seriesName
                        } label: {
                            TokenMetricView(
                                title: strings.usageSuffix(for: summary.name),
                                value: summary.total,
                                color: summary.color,
                                isSelected: selectedSeries == strings.usageSuffix(for: summary.name)
                            )
                            .contentShape(RoundedRectangle(cornerRadius: 6))
                        }
                        .buttonStyle(.plain)
                        .help(selectedSeries == strings.usageSuffix(for: summary.name) ? strings.text(.showAllLines) : strings.showOnlyUsageSuffix(for: summary.name))
                    }
                }

                GeometryReader { viewport in
                    ScrollView(.horizontal, showsIndicators: false) {
                        let resolvedWidth = resolvedChartWidth(for: viewport.size.width)
                        TokenLineChartPlot(
                            buckets: chart.buckets,
                            series: visibleSeries,
                            maxValue: max(visibleSeries.flatMap(\.values).max() ?? 0, 1),
                            visibleWidth: viewport.size.width
                        )
                        .frame(width: resolvedWidth, height: 170)
                    }
                    .coordinateSpace(name: "TokenChartScroll")
                }
                .frame(height: 170)
            } else {
                Text(chart.message ?? strings.text(.noStatsData))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 10)
            }
        }
    }

    private func resolvedChartWidth(for visibleWidth: CGFloat) -> CGFloat {
        if chart.bucketUnit == "day" {
            return max(visibleWidth, 320)
        }
        let step: CGFloat = 30
        return max(visibleWidth, CGFloat(max(chart.buckets.count - 1, 1)) * step + 110)
    }

    private func modelColor(at index: Int) -> Color {
        let palette: [Color] = [
            .green,
            .orange,
            .purple,
            .pink,
            .teal,
            .red,
            .indigo,
            .mint,
            .brown,
            .cyan,
            .yellow,
        ]
        if index < palette.count {
            return palette[index]
        }

        let hue = Double((index - palette.count) % 24) / 24.0
        let brightness = 0.62 + Double((index / 24) % 3) * 0.12
        return Color(hue: hue, saturation: 0.72, brightness: min(brightness, 0.86))
    }
}

struct TokenModelSummary: Identifiable {
    var name: String
    var total: Double
    var color: Color

    var id: String { name }
}

struct TokenChartSeries: Identifiable {
    var name: String
    var color: Color
    var values: [Double]

    var id: String { name }
}

struct TokenMetricView: View {
    var title: String
    var value: Double
    var color: Color
    var isSelected: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                Circle()
                    .fill(color)
                    .frame(width: 7, height: 7)
                Text(title)
                    .font(.system(size: 11.5))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(formattedTokenNumber(value).number)
                    .font(UB.Font.summaryBig)
                    .tracking(-0.6)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                Text(formattedTokenNumber(value).unit)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(RoundedRectangle(cornerRadius: 6))
        .background(
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(isSelected ? color.opacity(0.10) : .clear)
        )
    }
}

struct TokenLineChartPlot: View {
    var buckets: [PluginChartBucket]
    var series: [TokenChartSeries]
    var maxValue: Double
    var visibleWidth: CGFloat
    @State private var hoverLocation: CGPoint?

    private let leadingWidth: CGFloat = 30
    private let trailingPadding: CGFloat = 20
    private let topPadding: CGFloat = 12
    private let bottomHeight: CGFloat = 26
    private let yTickCount = 3

    var body: some View {
        GeometryReader { proxy in
            let size = proxy.size
            let chartFrame = proxy.frame(in: .named("TokenChartScroll"))
            let plotRect = CGRect(
                x: leadingWidth,
                y: topPadding,
                width: max(size.width - leadingWidth - trailingPadding, 1),
                height: max(size.height - topPadding - bottomHeight, 1)
            )
            let hoverIndex = nearestBucketIndex(in: plotRect)

            ZStack(alignment: .topLeading) {
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color(nsColor: .textBackgroundColor).opacity(0.55))

                grid(in: plotRect)
                xAxisLabels(in: plotRect)
                lineSeries(in: plotRect)

                if let hoverIndex {
                    hoverOverlay(index: hoverIndex, in: plotRect, size: size, chartMinX: chartFrame.minX)
                }
            }
            .contentShape(Rectangle())
            .onContinuousHover { phase in
                switch phase {
                case .active(let location):
                    hoverLocation = location
                case .ended:
                    hoverLocation = nil
                }
            }
        }
    }

    private func grid(in plotRect: CGRect) -> some View {
        ZStack(alignment: .topLeading) {
            ForEach(0...yTickCount, id: \.self) { index in
                let value = maxValue * Double(yTickCount - index) / Double(yTickCount)
                let y = plotRect.minY + CGFloat(index) / CGFloat(yTickCount) * plotRect.height
                Path { path in
                    path.move(to: CGPoint(x: plotRect.minX, y: y))
                    path.addLine(to: CGPoint(x: plotRect.maxX, y: y))
                }
                .stroke(Color(nsColor: .separatorColor).opacity(0.65), lineWidth: 0.6)

                Text(formattedAxisTokenNumber(value))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
                    .frame(width: leadingWidth - 4, alignment: .trailing)
                    .position(x: (leadingWidth - 4) / 2, y: y)
            }
        }
    }

    private func xAxisLabels(in plotRect: CGRect) -> some View {
        ZStack(alignment: .topLeading) {
            ForEach(xTickIndices, id: \.self) { index in
                let x = xPosition(for: index, in: plotRect)
                Text(buckets[index].label)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .position(x: x, y: plotRect.maxY + 15)
            }
        }
    }

    private func lineSeries(in plotRect: CGRect) -> some View {
        ZStack {
            ForEach(series) { item in
                Path { path in
                    guard !item.values.isEmpty else { return }
                    path.move(to: CGPoint(x: xPosition(for: 0, in: plotRect), y: plotRect.maxY))
                    for index in item.values.indices {
                        path.addLine(to: CGPoint(
                            x: xPosition(for: index, in: plotRect),
                            y: yPosition(for: item.values[index], in: plotRect)
                        ))
                    }
                    path.addLine(to: CGPoint(x: xPosition(for: item.values.count - 1, in: plotRect), y: plotRect.maxY))
                    path.closeSubpath()
                }
                .fill(item.color.opacity(0.06))

                Path { path in
                    for index in item.values.indices {
                        let point = CGPoint(
                            x: xPosition(for: index, in: plotRect),
                            y: yPosition(for: item.values[index], in: plotRect)
                        )
                        if index == item.values.startIndex {
                            path.move(to: point)
                        } else {
                            path.addLine(to: point)
                        }
                    }
                }
                .stroke(item.color, style: StrokeStyle(lineWidth: 1.6, lineCap: .round, lineJoin: .round))
            }
        }
    }

    private func hoverOverlay(index: Int, in plotRect: CGRect, size: CGSize, chartMinX: CGFloat) -> some View {
        let x = xPosition(for: index, in: plotRect)
        let rows = series.map { ($0.name, $0.color, valueAt(index, in: $0)) }
        let tooltipWidth: CGFloat = 178
        let tooltipMargin: CGFloat = 8
        let tooltipGap: CGFloat = 12
        let rightCenter = x + tooltipWidth / 2 + tooltipGap
        let leftCenter = x - tooltipWidth / 2 - tooltipGap
        let rightVisibleMax = chartMinX + rightCenter + tooltipWidth / 2
        let leftVisibleMin = chartMinX + leftCenter - tooltipWidth / 2
        let tooltipX: CGFloat
        if rightVisibleMax <= visibleWidth - tooltipMargin {
            tooltipX = rightCenter
        } else if leftVisibleMin >= tooltipMargin {
            tooltipX = leftCenter
        } else {
            let minCenter = tooltipMargin - chartMinX + tooltipWidth / 2
            let maxCenter = visibleWidth - tooltipMargin - chartMinX - tooltipWidth / 2
            tooltipX = min(max(rightCenter, minCenter), maxCenter)
        }

        return ZStack(alignment: .topLeading) {
            Path { path in
                path.move(to: CGPoint(x: x, y: plotRect.minY))
                path.addLine(to: CGPoint(x: x, y: plotRect.maxY))
            }
            .stroke(Color.secondary.opacity(0.55), style: StrokeStyle(lineWidth: 1, dash: [4, 3]))

            Circle()
                .strokeBorder(.white, lineWidth: 2)
                .background(Circle().fill(.blue))
                .frame(width: 8, height: 8)
                .position(x: x, y: yPosition(for: buckets[index].total, in: plotRect))

            VStack(alignment: .leading, spacing: 6) {
                Text(buckets[index].id)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
                ForEach(rows, id: \.0) { row in
                    HStack(spacing: 5) {
                        Circle()
                            .fill(row.1)
                            .frame(width: 6, height: 6)
                        Text(row.0)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Spacer(minLength: 4)
                        Text(formattedTokenNumber(row.2).compact)
                            .font(.caption)
                            .foregroundStyle(.primary)
                            .monospacedDigit()
                    }
                }
            }
            .padding(8)
            .frame(width: tooltipWidth)
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .shadow(color: .black.opacity(0.16), radius: 8, y: 3)
            .position(x: tooltipX, y: plotRect.minY + 72)
        }
    }

    private var xTickIndices: [Int] {
        guard buckets.count > 1 else { return buckets.indices.map { $0 } }
        let desiredTicks = min(5, buckets.count)
        let step = max(1, Int(ceil(Double(buckets.count - 1) / Double(desiredTicks - 1))))
        var indices = Array(stride(from: 0, to: buckets.count, by: step))
        if indices.last != buckets.count - 1 {
            indices.append(buckets.count - 1)
        }
        return indices
    }

    private func xPosition(for index: Int, in plotRect: CGRect) -> CGFloat {
        guard buckets.count > 1 else { return plotRect.midX }
        return plotRect.minX + CGFloat(index) / CGFloat(buckets.count - 1) * plotRect.width
    }

    private func yPosition(for value: Double, in plotRect: CGRect) -> CGFloat {
        let clamped = max(0, min(value / maxValue, 1))
        return plotRect.maxY - CGFloat(clamped) * plotRect.height
    }

    private func nearestBucketIndex(in plotRect: CGRect) -> Int? {
        guard let hoverLocation, plotRect.contains(hoverLocation), !buckets.isEmpty else { return nil }
        guard buckets.count > 1 else { return 0 }
        let ratio = min(max((hoverLocation.x - plotRect.minX) / plotRect.width, 0), 1)
        return min(max(Int((ratio * CGFloat(buckets.count - 1)).rounded()), 0), buckets.count - 1)
    }

    private func valueAt(_ index: Int, in series: TokenChartSeries) -> Double {
        guard series.values.indices.contains(index) else { return 0 }
        return series.values[index]
    }
}

private func formattedTokenNumber(_ value: Double) -> (number: String, unit: String, compact: String) {
    if value >= 1_000_000_000 {
        let number = String(format: "%.2f", value / 1_000_000_000)
        return (number, "B", "\(number)B")
    }
    if value >= 1_000_000 {
        let number = String(format: "%.2f", value / 1_000_000)
        return (number, "M", "\(number)M")
    }
    if value >= 1_000 {
        let number = String(format: "%.2f", value / 1_000)
        return (number, "K", "\(number)K")
    }
    if value.rounded() == value {
        let number = String(Int(value))
        return (number, "", number)
    }
    let number = String(format: "%.2f", value)
    return (number, "", number)
}

private func formattedAxisTokenNumber(_ value: Double) -> String {
    if value >= 1_000_000_000 {
        return "\(Int((value / 1_000_000_000).rounded()))B"
    }
    if value >= 1_000_000 {
        return "\(Int((value / 1_000_000).rounded()))M"
    }
    if value >= 1_000 {
        return "\(Int((value / 1_000).rounded()))K"
    }
    return "\(Int(value.rounded()))"
}

struct FlowLayout: Layout {
    var spacing: CGFloat = 8
    var rowSpacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? 260
        return layout(in: maxWidth, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        for item in layout(in: bounds.width, subviews: subviews).items {
            subviews[item.index].place(
                at: CGPoint(x: bounds.minX + item.frame.minX, y: bounds.minY + item.frame.minY),
                proposal: ProposedViewSize(item.frame.size)
            )
        }
    }

    private func layout(in maxWidth: CGFloat, subviews: Subviews) -> (items: [(index: Int, frame: CGRect)], size: CGSize) {
        var items: [(index: Int, frame: CGRect)] = []
        var cursor = CGPoint.zero
        var rowHeight: CGFloat = 0
        var usedWidth: CGFloat = 0

        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            if cursor.x > 0, cursor.x + size.width > maxWidth {
                cursor.x = 0
                cursor.y += rowHeight + rowSpacing
                rowHeight = 0
            }

            items.append((index, CGRect(origin: cursor, size: size)))
            cursor.x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
            usedWidth = max(usedWidth, cursor.x - spacing)
        }

        return (items, CGSize(width: min(maxWidth, usedWidth), height: cursor.y + rowHeight))
    }
}

struct UsageProgressBar: View {
    var value: Double
    var label: String
    var color: String?

    var body: some View {
        GeometryReader { proxy in
            let ratio = max(0, min(value, 1))
            let width = ratio * proxy.size.width
            let textWhite = ratio >= 0.55
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: UB.Radius.bar, style: .continuous)
                    .fill(resolvedColor.opacity(0.16))
                RoundedRectangle(cornerRadius: UB.Radius.bar, style: .continuous)
                    .fill(resolvedColor)
                    .frame(width: width)
                Text(label)
                    .font(.system(size: 11, weight: .semibold))
                    .monospacedDigit()
                    .foregroundStyle(textWhite ? Color.white : Color.primary)
                    .frame(maxWidth: .infinity, alignment: .center)
            }
        }
        .frame(minWidth: 80, idealHeight: 18, maxHeight: 18)
        .clipShape(RoundedRectangle(cornerRadius: UB.Radius.bar, style: .continuous))
        .accessibilityLabel(label)
    }

    private var resolvedColor: Color {
        if let override = color?.lowercased(), let c = mapOverride(override) {
            return c
        }
        let pct = value * 100
        if pct >= 100 { return .red }
        if pct >= 80 { return .orange }
        if pct >= 60 { return .yellow }
        return .blue
    }

    private func mapOverride(_ name: String) -> Color? {
        switch name {
        case "red": return .red
        case "orange": return .orange
        case "yellow": return .yellow
        case "green": return .green
        case "blue": return .blue
        default: return nil
        }
    }
}

private struct SettingsButton: View {
    var iconSize: CGFloat = 13
    var buttonSize: CGFloat = 24

    var body: some View {
        Button {
            AppDelegate.shared?.openSettings()
        } label: {
            Image(systemName: "gear")
                .font(.system(size: iconSize, weight: .medium))
                .frame(width: buttonSize, height: buttonSize)
        }
        .buttonStyle(.borderless)
    }
}

private struct QuitButton: View {
    var language: AppLanguage = .zhHans
    var iconSize: CGFloat = 13
    var buttonSize: CGFloat = 24
    private var strings: AppLocalization {
        AppLocalization(language: language)
    }

    var body: some View {
        Button {
            NSApp.terminate(nil)
        } label: {
            Image(systemName: "power")
                .font(.system(size: iconSize, weight: .medium))
                .frame(width: buttonSize, height: buttonSize)
        }
        .buttonStyle(.borderless)
        .help(strings.text(.quitUsageBoard))
    }
}
