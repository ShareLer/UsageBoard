import AppKit
import Foundation
import ServiceManagement
import UsageBoardCore

@MainActor
final class UsageBoardStore: ObservableObject {
    @Published var configuration: AppConfiguration
    @Published private(set) var snapshots: [UUID: PluginSnapshot] = [:]
    @Published var lastError: String?
    @Published var updateMessage: String?
    @Published var availableUpdate: UpdateInfo?
    @Published var isUpdating: Bool = false

    private let configStore: ConfigStore
    private let stateStore: PluginStateStore
    private let executor: PluginExecutor
    private let updateChecker: UpdateChecker
    private var refreshTasks: [UUID: Task<Void, Never>] = [:]

    init(
        configStore: ConfigStore = ConfigStore(),
        stateStore: PluginStateStore = PluginStateStore(),
        executor: PluginExecutor = PluginExecutor(),
        updateChecker: UpdateChecker = UpdateChecker()
    ) {
        self.configStore = configStore
        self.stateStore = stateStore
        self.executor = executor
        self.updateChecker = updateChecker
        var didLoadConfiguration = false
        do {
            configuration = try configStore.loadOrCreate()
            didLoadConfiguration = true
        } catch {
            configuration = AppConfiguration()
            lastError = "配置加载失败：\(error.localizedDescription)"
        }
        if didLoadConfiguration {
            try? configStore.save(configuration) // persist generated stateIDs
        }
        do {
            try installBundledPlugins()
        } catch {
            lastError = "内置插件安装失败：\(error.localizedDescription)"
        }
        rebuildSnapshots()
        loadCachedStates()
        startSchedulers()
    }

    deinit {
        refreshTasks.values.forEach { $0.cancel() }
    }

    var displayNames: [UUID: String] {
        PluginDisplayNames.make(for: configuration.plugins)
    }

    var pluginsDirectoryURL: URL {
        configStore.pluginsDirectoryURL()
    }

    func snapshot(for plugin: PluginConfiguration) -> PluginSnapshot {
        if let snapshot = snapshots[plugin.id] {
            return snapshot
        }
        return PluginSnapshot(
            id: plugin.id,
            pluginName: plugin.name,
            displayName: displayNames[plugin.id] ?? plugin.name
        )
    }

    func saveConfiguration() {
        do {
            try configStore.save(configuration)
            lastError = nil
            rebuildSnapshots()
            startSchedulers()
            refreshPluginsAfterConfigurationChange()
        } catch {
            lastError = "配置保存失败：\(error.localizedDescription)"
        }
    }

    func addPlugin(fileURL: URL) {
        let metadata = PluginMetadataParser.parse(fileURL: fileURL)
        let name = metadata?.name ?? fileURL.deletingPathExtension().lastPathComponent
        var values: [String: String] = [:]
        for parameter in metadata?.parameters ?? [] {
            if let defaultValue = parameter.defaultValue {
                values[parameter.name] = defaultValue
            }
        }

        let plugin = PluginConfiguration(
            name: name,
            enabled: false,
            executablePath: fileURL.path,
            refreshIntervalSeconds: 300,
            metadata: metadata,
            parameterValues: values
        )
        configuration.plugins.append(plugin)
        let displayName = displayNames[plugin.id] ?? plugin.name
        snapshots[plugin.id] = PluginSnapshot(
            id: plugin.id,
            pluginName: plugin.name,
            displayName: displayName,
            state: .idle
        )
        saveConfiguration()
    }

    func ensurePluginsDirectory() {
        do {
            try FileManager.default.createDirectory(at: pluginsDirectoryURL, withIntermediateDirectories: true)
        } catch {
            lastError = "插件目录创建失败：\(error.localizedDescription)"
        }
    }

    func setPluginEnabled(id: UUID, enabled: Bool) {
        guard let index = configuration.plugins.firstIndex(where: { $0.id == id }) else { return }
        let plugin = configuration.plugins[index]

        guard enabled else {
            configuration.plugins[index].enabled = false
            saveConfiguration()
            return
        }

        let missing = missingRequiredParameters(for: plugin)
        guard missing.isEmpty else {
            configuration.plugins[index].enabled = false
            lastError = "请先填写必填参数：\(missing.joined(separator: "、"))"
            return
        }

        configuration.plugins[index].enabled = true
        lastError = nil
        saveConfiguration()

        snapshots[id] = PluginSnapshot(
            id: plugin.id,
            pluginName: plugin.name,
            displayName: displayNames[plugin.id] ?? plugin.name,
            state: .loading,
            items: snapshots[plugin.id]?.items ?? [],
            updatedAt: snapshots[plugin.id]?.updatedAt
        )
        refresh(pluginID: id, force: true)
    }

    func reloadMetadata(pluginID: UUID) {
        guard let index = configuration.plugins.firstIndex(where: { $0.id == pluginID }) else { return }
        let fileURL = URL(fileURLWithPath: configuration.plugins[index].executablePath)
        let metadata = PluginMetadataParser.parse(fileURL: fileURL)
        configuration.plugins[index].metadata = metadata

        for parameter in metadata?.parameters ?? [] where configuration.plugins[index].parameterValues[parameter.name] == nil {
            configuration.plugins[index].parameterValues[parameter.name] = parameter.defaultValue ?? ""
        }
    }

    func removePlugin(id: UUID) {
        guard let index = configuration.plugins.firstIndex(where: { $0.id == id }) else { return }
        configuration.plugins.remove(at: index)
        snapshots.removeValue(forKey: id)
        refreshTasks[id]?.cancel()
        refreshTasks.removeValue(forKey: id)
        saveConfiguration()
    }

    func refreshAll() {
        for plugin in configuration.plugins where plugin.enabled {
            refresh(pluginID: plugin.id, force: true)
        }
    }

    func refresh(pluginID: UUID, force: Bool = false) {
        guard let plugin = configuration.plugins.first(where: { $0.id == pluginID }) else { return }
        guard plugin.enabled else { return }
        guard isPluginReadyToRun(plugin) else {
            snapshots[plugin.id] = PluginSnapshot(
                id: plugin.id,
                pluginName: plugin.name,
                displayName: displayNames[plugin.id] ?? plugin.name,
                state: .loading,
                items: snapshots[plugin.id]?.items ?? [],
                updatedAt: snapshots[plugin.id]?.updatedAt
            )
            return
        }
        guard force || stateStore.needsRefresh(stateID: plugin.stateID, intervalSeconds: plugin.refreshIntervalSeconds) else { return }

        snapshots[plugin.id] = PluginSnapshot(
            id: plugin.id,
            pluginName: plugin.name,
            displayName: displayNames[plugin.id] ?? plugin.name,
            state: .loading,
            items: snapshots[plugin.id]?.items ?? [],
            updatedAt: snapshots[plugin.id]?.updatedAt
        )

        let executor = executor
        let stateStore = stateStore
        let displayName = displayNames[plugin.id] ?? plugin.name
        Task {
            let snapshot = await Task.detached(priority: .utility) {
                executor.run(configuration: plugin, displayName: displayName)
            }.value
            snapshots[plugin.id] = snapshot
            if snapshot.state == .ready, let updatedAt = snapshot.updatedAt {
                let cached = PluginCachedState(updatedAt: updatedAt, items: snapshot.items, badge: snapshot.badge)
                stateStore.save(stateID: plugin.stateID, state: cached)
            }
        }
    }

    private static let updateCheckURL: URL? = {
        guard let string = Bundle.main.infoDictionary?["UBUpdateCheckURL"] as? String,
              !string.isEmpty else { return nil }
        return URL(string: string)
    }()

    func checkForUpdates(userInitiated: Bool = false) {
        guard let url = Self.updateCheckURL else {
            updateMessage = "未配置更新检查地址"
            return
        }
        availableUpdate = nil
        Task {
            do {
                let result = try await updateChecker.check(currentVersion: currentVersion, url: url)
                if result.hasUpdate {
                    availableUpdate = result.info
                    updateMessage = nil
                } else {
                    availableUpdate = nil
                    updateMessage = "当前已是最新版本"
                }
            } catch {
                updateMessage = "检查更新失败：\(error.localizedDescription)"
            }
        }
    }

    func performUpdate() {
        guard let info = availableUpdate, let url = URL(string: info.downloadURL) else { return }
        isUpdating = true
        updateMessage = "正在下载更新..."

        Task {
            do {
                let downloader = UpdateDownloader()
                let newBundleURL = try await downloader.download(from: url)
                updateMessage = "正在安装更新..."
                try AppRelauncher.relaunch(replacingWith: newBundleURL)
                NSApp.terminate(nil)
            } catch {
                isUpdating = false
                updateMessage = "更新失败：\(error.localizedDescription)"
            }
        }
    }

    private var currentVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.1.0"
    }

    private func installBundledPlugins() throws {
        guard let sourceURL = bundledPluginsDirectoryURL() else { return }
        _ = try BundledPluginInstaller(
            sourceDirectoryURL: sourceURL,
            destinationDirectoryURL: configStore.pluginsDirectoryURL()
        )
        .installIfNeeded()
    }

    private func bundledPluginsDirectoryURL() -> URL? {
        if let appResourceURL = Bundle.main.resourceURL?
            .appendingPathComponent("Plugins", isDirectory: true),
            FileManager.default.fileExists(atPath: appResourceURL.path) {
            return appResourceURL
        }

        let developmentURL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources/BundledPlugins", isDirectory: true)
        if FileManager.default.fileExists(atPath: developmentURL.path) {
            return developmentURL
        }

        return nil
    }

    private func rebuildSnapshots() {
        let names = displayNames
        var next: [UUID: PluginSnapshot] = [:]
        for plugin in configuration.plugins {
            next[plugin.id] = snapshots[plugin.id] ?? PluginSnapshot(
                id: plugin.id,
                pluginName: plugin.name,
                displayName: names[plugin.id] ?? plugin.name
            )
        }
        snapshots = next
    }

    private func loadCachedStates() {
        let names = displayNames
        for plugin in configuration.plugins {
            guard let cached = stateStore.load(stateID: plugin.stateID) else { continue }
            snapshots[plugin.id] = PluginSnapshot(
                id: plugin.id,
                pluginName: plugin.name,
                displayName: names[plugin.id] ?? plugin.name,
                state: .ready,
                items: cached.items,
                updatedAt: cached.updatedAt,
                badge: cached.badge
            )
        }
    }

    private func startSchedulers() {
        refreshTasks.values.forEach { $0.cancel() }
        refreshTasks = [:]

        for plugin in configuration.plugins where plugin.enabled {
            let id = plugin.id
            let interval = max(plugin.refreshIntervalSeconds, 5)
            let hasCached = stateStore.load(stateID: plugin.stateID) != nil

            if !hasCached {
                let names = displayNames
                snapshots[id] = PluginSnapshot(
                    id: id,
                    pluginName: plugin.name,
                    displayName: names[id] ?? plugin.name,
                    state: .loading
                )
            }

            refreshTasks[id] = Task { [weak self] in
                guard self?.isPluginReadyToRun(plugin) == true else { return }
                if let cached = self?.stateStore.load(stateID: plugin.stateID) {
                    let elapsed = Date().timeIntervalSince(cached.updatedAt)
                    let remaining = Double(interval) - elapsed
                    if remaining > 0 {
                        try? await Task.sleep(for: .seconds(remaining))
                    }
                }
                while !Task.isCancelled {
                    self?.refresh(pluginID: id)
                    try? await Task.sleep(for: .seconds(interval))
                }
            }
        }
    }

    private func refreshPluginsAfterConfigurationChange() {
        for plugin in configuration.plugins where plugin.enabled && isPluginReadyToRun(plugin) {
            let snapshot = snapshots[plugin.id]
            let hasCached = stateStore.load(stateID: plugin.stateID) != nil
            let shouldRefresh = !hasCached || snapshot?.state == .loading || isFailed(snapshot?.state)
            if shouldRefresh {
                refresh(pluginID: plugin.id, force: true)
            }
        }
    }

    private func isFailed(_ state: PluginSnapshotState?) -> Bool {
        guard let state else { return false }
        if case .failed = state {
            return true
        }
        return false
    }

    func missingRequiredParameters(for plugin: PluginConfiguration) -> [String] {
        var missing: [String] = []
        for parameter in plugin.metadata?.parameters ?? [] where parameter.required {
            let value = plugin.parameterValues[parameter.name] ?? parameter.defaultValue ?? ""
            if value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                missing.append(parameter.label)
            }
        }
        return missing
    }

    private func isPluginReadyToRun(_ plugin: PluginConfiguration) -> Bool {
        missingRequiredParameters(for: plugin).isEmpty
    }

    // MARK: - Launch at Login

    func toggleLaunchAtLogin(_ enabled: Bool) {
        do {
            if enabled {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
        } catch {
            lastError = "开机启动设置失败：\(error.localizedDescription)"
            configuration.launchAtLogin = !enabled
        }
    }
}
