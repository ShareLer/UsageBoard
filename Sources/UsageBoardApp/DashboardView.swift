import AppKit
import SwiftUI
import UsageBoardCore

private final class IconImageCache: @unchecked Sendable {
    static let shared = IconImageCache()
    private let cache = NSCache<NSString, NSImage>()

    func image(for url: URL) async -> NSImage? {
        let key = url.absoluteString as NSString
        if let cached = cache.object(forKey: key) {
            return cached
        }
        guard let (data, _) = try? await URLSession.shared.data(from: url),
              let image = NSImage(data: data) else { return nil }
        cache.setObject(image, forKey: key)
        return image
    }
}

struct DashboardView: View {
    @ObservedObject var store: UsageBoardStore
    var mode: DisplayMode
    @State private var selectedTabID: UUID?

    private var maxHeight: CGFloat {
        (NSScreen.main?.visibleFrame.height ?? 800) * 2 / 3
    }

    private var enabledPlugins: [PluginConfiguration] {
        store.configuration.plugins.filter(\.enabled)
    }

    var body: some View {
        Group {
            if enabledPlugins.isEmpty {
                EmptyPluginsView()
            } else {
                switch mode {
                case .grouped:
                    MeasuredScrollView(maxHeight: maxHeight) {
                        LazyVStack(spacing: 10) {
                            ForEach(enabledPlugins) { plugin in
                                PluginGroupView(snapshot: store.snapshot(for: plugin)) {
                                    store.refresh(pluginID: plugin.id, force: true)
                                }
                            }
                        }
                        .padding(10)
                    }
                case .tabs:
                    TabView(selection: tabSelection) {
                        ForEach(enabledPlugins) { plugin in
                            MeasuredScrollView(maxHeight: maxHeight - 40) {
                                PluginGroupView(snapshot: store.snapshot(for: plugin)) {
                                    store.refresh(pluginID: plugin.id, force: true)
                                }
                                    .padding(10)
                            }
                            .tag(plugin.id)
                            .tabItem { Text(store.snapshot(for: plugin).displayName) }
                        }
                    }
                    .padding(.top, 8)
                    .frame(height: tabViewHeight)
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
                Label("刷新", systemImage: "arrow.clockwise")
            }
            QuitButton()
        }
    }

    private var tabSelection: Binding<UUID> {
        Binding(
            get: {
                selectedPlugin?.id ?? enabledPlugins.first?.id ?? UUID()
            },
            set: { value in
                selectedTabID = value
            }
        )
    }

    private var selectedPlugin: PluginConfiguration? {
        if let selectedTabID,
           let plugin = enabledPlugins.first(where: { $0.id == selectedTabID }) {
            return plugin
        }
        return enabledPlugins.first
    }

    private var tabViewHeight: CGFloat {
        let selectedRows = max(selectedPlugin.map { store.snapshot(for: $0).items.count } ?? 1, 1)
        let rowsHeight = CGFloat(selectedRows) * 26
        return min(max(92 + rowsHeight, 150), maxHeight)
    }

    private func ensureSelectedTab() {
        guard !enabledPlugins.isEmpty else {
            selectedTabID = nil
            return
        }
        if let selectedTabID,
           enabledPlugins.contains(where: { $0.id == selectedTabID }) {
            return
        }
        selectedTabID = enabledPlugins.first?.id
    }
}

struct EmptyPluginsView: View {
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "puzzlepiece.extension")
                .font(.system(size: 40))
                .foregroundStyle(.secondary)
            Text("暂无插件")
                .font(.headline)
            Text("在设置中添加插件后显示用量。")
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
                Image(systemName: "chart.bar.xaxis")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(.secondary)
                    .frame(width: 20, height: 20)
                Text("UsageBoard")
                    .font(.system(size: 15, weight: .semibold))
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
                QuitButton(iconSize: 13, buttonSize: 24)
            }
            .padding(.horizontal)
            .padding(.vertical, 10)

            Divider()

            DashboardView(store: store, mode: store.configuration.overviewDisplayMode)
        }
    }
}

struct MeasuredScrollView<Content: View>: View {
    var maxHeight: CGFloat
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
        .frame(height: contentHeight > 0 ? min(contentHeight, maxHeight) : maxHeight)
        .onPreferenceChange(ContentHeightKey.self) { height in
            if height > 0 {
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
    var onRefresh: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                pluginIcon
                Text(snapshot.displayName)
                    .font(.headline)
                if let badge = snapshot.badge {
                    Text(badge.uppercased())
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(.black)
                        .clipShape(RoundedRectangle(cornerRadius: 3))
                }
                Spacer()
                stateView
            }

            Divider()

            if snapshot.items.isEmpty {
                Text(emptyText)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 18)
            } else {
                VStack(spacing: 8) {
                    ForEach(snapshot.items) { item in
                        UsageItemRow(item: item)
                    }
                }
            }
        }
        .padding(10)
        .background(Color(nsColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color(nsColor: .separatorColor), lineWidth: 0.5)
        )
    }

    @ViewBuilder
    private var pluginIcon: some View {
        Group {
            if let urlString = snapshot.iconURL, let url = URL(string: urlString) {
                CachedIconImage(url: url)
            } else {
                Image(systemName: "puzzlepiece.extension")
            }
        }
        .frame(width: 18, height: 18)
    }

    @ViewBuilder
    private var stateView: some View {
        switch snapshot.state {
        case .idle:
            Text("等待刷新")
                .foregroundStyle(.secondary)
        case .loading:
            ProgressView()
                .controlSize(.small)
        case .ready:
            if let updatedAt = snapshot.updatedAt {
                Button {
                    onRefresh?()
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 10))
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.secondary)
                Text(updatedAt, style: .time)
                    .foregroundStyle(.secondary)
            }
        case .failed(let message):
            Text(message)
                .lineLimit(1)
                .foregroundStyle(.red)
        }
    }

    private var emptyText: String {
        switch snapshot.state {
        case .failed:
            return "插件执行失败"
        default:
            return "暂无用量数据"
        }
    }
}

struct UsageItemRow: View {
    var item: UsageItem

    var body: some View {
        HStack(spacing: 6) {
            Text(item.name)
                .lineLimit(1)
                .truncationMode(.tail)
                .frame(width: 120, alignment: .leading)

            UsageProgressBar(value: item.progress, label: item.displayValue(), color: item.color)
                .frame(height: 18)
                .layoutPriority(1)

            Text(item.resetText())
                .font(.caption)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .foregroundStyle(.secondary)
                .frame(width: 80, alignment: .trailing)
        }
        .font(.callout)
    }
}

struct UsageProgressBar: View {
    var value: Double
    var label: String
    var color: String?

    var body: some View {
        GeometryReader { proxy in
            let width = max(0, min(value, 1)) * proxy.size.width
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 5)
                    .fill(progressColor.opacity(0.16))
                RoundedRectangle(cornerRadius: 5)
                    .fill(progressColor)
                    .frame(width: width)
                Text(label)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .monospacedDigit()
                    .foregroundStyle(.primary)
                    .frame(maxWidth: .infinity, alignment: .center)
            }
        }
        .frame(minWidth: 80)
        .clipShape(RoundedRectangle(cornerRadius: 5))
        .accessibilityLabel(label)
    }

    private var progressColor: Color {
        switch color?.lowercased() {
        case "red":
            return .red
        case "orange":
            return .orange
        case "yellow":
            return .yellow
        case "green":
            return .green
        case "blue", nil:
            return .blue
        default:
            return .blue
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
    var iconSize: CGFloat = 13
    var buttonSize: CGFloat = 24

    var body: some View {
        Button {
            NSApp.terminate(nil)
        } label: {
            Image(systemName: "power")
                .font(.system(size: iconSize, weight: .medium))
                .frame(width: buttonSize, height: buttonSize)
        }
        .buttonStyle(.borderless)
        .help("退出 UsageBoard")
    }
}

private struct CachedIconImage: View {
    let url: URL
    @State private var image: NSImage?

    var body: some View {
        Group {
            if let image {
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
            } else {
                Image(systemName: "puzzlepiece.extension")
            }
        }
        .task { image = await IconImageCache.shared.image(for: url) }
    }
}
