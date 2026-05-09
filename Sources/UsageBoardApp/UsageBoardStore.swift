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
    @Published var selectedTabID: UUID?

    let activeLanguage: AppLanguage

    private let configStore: ConfigStore
    private let stateStore: PluginStateStore
    private let executor: PluginExecutor
    private let updateChecker: UpdateChecker
    private var refreshTasks: [UUID: Task<Void, Never>] = [:]
    private var isSystemActive: Bool = true
    private var systemActivityObservers: [NSObjectProtocol] = []

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
        let loadedConfiguration: AppConfiguration
        var didLoadConfiguration = false
        do {
            loadedConfiguration = try configStore.loadOrCreate()
            didLoadConfiguration = true
        } catch {
            loadedConfiguration = AppConfiguration()
            lastError = "配置加载失败：\(error.localizedDescription)"
        }
        configuration = loadedConfiguration
        activeLanguage = loadedConfiguration.language
        if didLoadConfiguration {
            try? configStore.save(configuration) // persist generated stateIDs
        }
        do {
            try installBundledPlugins()
        } catch {
            lastError = activeLanguage == .en
                ? "Failed to install bundled plugins: \(error.localizedDescription)"
                : "内置插件安装失败：\(error.localizedDescription)"
        }
        reloadAllMetadata()
        try? configStore.save(configuration)
        rebuildSnapshots()
        loadCachedStates()
        startSchedulers()
        observeSystemActivity()
    }

    deinit {
        refreshTasks.values.forEach { $0.cancel() }
    }

    var displayNames: [UUID: String] {
        PluginDisplayNames.make(for: configuration.plugins, language: activeLanguage)
    }

    var pluginsDirectoryURL: URL {
        configStore.pluginsDirectoryURL()
    }

    func snapshot(for plugin: PluginConfiguration) -> PluginSnapshot {
        if let snapshot = snapshots[plugin.id] {
            return snapshot
        }
        return makeSnapshot(for: plugin)
    }

    func saveConfiguration() {
        do {
            try configStore.save(configuration)
            lastError = nil
            rebuildSnapshots()
            startSchedulers()
            refreshPluginsAfterConfigurationChange()
        } catch {
            lastError = storeMessage(.configurationSaveFailed(error.localizedDescription))
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
        snapshots[plugin.id] = makeSnapshot(for: plugin)
        saveConfiguration()
    }

    func ensurePluginsDirectory() {
        do {
            try FileManager.default.createDirectory(at: pluginsDirectoryURL, withIntermediateDirectories: true)
        } catch {
            lastError = storeMessage(.pluginsDirectoryCreateFailed(error.localizedDescription))
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
            lastError = storeMessage(.missingRequiredParameters(missing))
            return
        }

        configuration.plugins[index].enabled = true
        lastError = nil
        saveConfiguration()

        snapshots[id] = makeSnapshot(
            for: plugin,
            state: .loading,
            items: snapshots[plugin.id]?.items ?? [],
            updatedAt: snapshots[plugin.id]?.updatedAt,
            chart: snapshots[plugin.id]?.chart
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

    private func reloadAllMetadata() {
        for plugin in configuration.plugins {
            reloadMetadata(pluginID: plugin.id)
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
            snapshots[plugin.id] = makeSnapshot(
                for: plugin,
                state: .loading,
                items: snapshots[plugin.id]?.items ?? [],
                updatedAt: snapshots[plugin.id]?.updatedAt,
                chart: snapshots[plugin.id]?.chart
            )
            return
        }
        guard force || stateStore.needsRefresh(stateID: plugin.stateID, intervalSeconds: plugin.refreshIntervalSeconds) else { return }

        snapshots[plugin.id] = makeSnapshot(
            for: plugin,
            state: .loading,
            items: snapshots[plugin.id]?.items ?? [],
            updatedAt: snapshots[plugin.id]?.updatedAt,
            badge: snapshots[plugin.id]?.badge,
            chart: snapshots[plugin.id]?.chart
        )

        let executor = executor
        let stateStore = stateStore
        let displayName = displayNames[plugin.id] ?? PluginDisplayNames.displayName(for: plugin, language: activeLanguage)
        let language = activeLanguage
        Task {
            let snapshot = await Task.detached(priority: .utility) {
                executor.run(configuration: plugin, displayName: displayName, language: language)
            }.value
            snapshots[plugin.id] = snapshot
            if snapshot.state == .ready, let updatedAt = snapshot.updatedAt {
                let cached = PluginCachedState(
                    updatedAt: updatedAt,
                    items: snapshot.items,
                    badge: snapshot.badge,
                    chart: snapshot.chart
                )
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
            updateMessage = storeMessage(.updateCheckURLMissing)
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
                    updateMessage = storeMessage(.alreadyLatestVersion)
                }
            } catch {
                updateMessage = storeMessage(.updateCheckFailed(error.localizedDescription))
            }
        }
    }

    func performUpdate() {
        guard let info = availableUpdate, let url = URL(string: info.downloadURL) else { return }
        isUpdating = true
        updateMessage = storeMessage(.downloadingUpdate)

        Task {
            do {
                let downloader = UpdateDownloader()
                let newBundleURL = try await downloader.download(from: url)
                updateMessage = storeMessage(.installingUpdate)
                try AppRelauncher.relaunch(replacingWith: newBundleURL)
                NSApp.terminate(nil)
            } catch {
                isUpdating = false
                updateMessage = storeMessage(.updateFailed(error.localizedDescription))
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
        var next: [UUID: PluginSnapshot] = [:]
        for plugin in configuration.plugins {
            next[plugin.id] = snapshots[plugin.id] ?? makeSnapshot(for: plugin)
        }
        snapshots = next
    }

    private func loadCachedStates() {
        for plugin in configuration.plugins {
            guard let cached = stateStore.load(stateID: plugin.stateID) else { continue }
            snapshots[plugin.id] = makeSnapshot(
                for: plugin,
                state: .ready,
                items: cached.items,
                updatedAt: cached.updatedAt,
                badge: cached.badge,
                chart: cached.chart
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
                snapshots[id] = makeSnapshot(for: plugin, state: .loading)
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
                    if self?.isSystemActive == true {
                        self?.refresh(pluginID: id)
                    }
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

    private func observeSystemActivity() {
        let workspaceCenter = NSWorkspace.shared.notificationCenter
        let distributedCenter = DistributedNotificationCenter.default()

        let inactiveWorkspaceEvents: [NSNotification.Name] = [
            NSWorkspace.willSleepNotification,
            NSWorkspace.screensDidSleepNotification,
            NSWorkspace.sessionDidResignActiveNotification,
        ]
        let activeWorkspaceEvents: [NSNotification.Name] = [
            NSWorkspace.didWakeNotification,
            NSWorkspace.screensDidWakeNotification,
            NSWorkspace.sessionDidBecomeActiveNotification,
        ]

        for name in inactiveWorkspaceEvents {
            let token = workspaceCenter.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.setSystemActive(false) }
            }
            systemActivityObservers.append(token)
        }
        for name in activeWorkspaceEvents {
            let token = workspaceCenter.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.setSystemActive(true) }
            }
            systemActivityObservers.append(token)
        }

        let lockedToken = distributedCenter.addObserver(
            forName: Notification.Name("com.apple.screenIsLocked"), object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.setSystemActive(false) }
        }
        let unlockedToken = distributedCenter.addObserver(
            forName: Notification.Name("com.apple.screenIsUnlocked"), object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.setSystemActive(true) }
        }
        systemActivityObservers.append(lockedToken)
        systemActivityObservers.append(unlockedToken)
    }

    private func setSystemActive(_ active: Bool) {
        guard active != isSystemActive else { return }
        isSystemActive = active
        if active {
            refreshPluginsIfDue()
        }
    }

    private func refreshPluginsIfDue() {
        for plugin in configuration.plugins where plugin.enabled && isPluginReadyToRun(plugin) {
            refresh(pluginID: plugin.id)
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
                missing.append(parameter.localizedLabel(language: activeLanguage))
            }
        }
        return missing
    }

    private func makeSnapshot(
        for plugin: PluginConfiguration,
        state: PluginSnapshotState = .idle,
        items: [UsageItem] = [],
        updatedAt: Date? = nil,
        badge: String? = nil,
        chart: PluginChart? = nil
    ) -> PluginSnapshot {
        PluginSnapshot(
            id: plugin.id,
            pluginName: plugin.name,
            displayName: displayNames[plugin.id] ?? PluginDisplayNames.displayName(for: plugin, language: activeLanguage),
            state: state,
            items: items,
            updatedAt: updatedAt,
            badge: badge,
            iconURL: plugin.metadata?.icon,
            chart: chart
        )
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
            lastError = storeMessage(.launchAtLoginFailed(error.localizedDescription))
            configuration.launchAtLogin = !enabled
        }
    }

    private enum StoreMessage {
        case configurationSaveFailed(String)
        case pluginsDirectoryCreateFailed(String)
        case missingRequiredParameters([String])
        case updateCheckURLMissing
        case alreadyLatestVersion
        case updateCheckFailed(String)
        case downloadingUpdate
        case installingUpdate
        case updateFailed(String)
        case launchAtLoginFailed(String)
    }

    private func storeMessage(_ message: StoreMessage) -> String {
        switch (message, activeLanguage) {
        case (.configurationSaveFailed(let detail), .en):
            return "Failed to save configuration: \(detail)"
        case (.configurationSaveFailed(let detail), .zhHans):
            return "配置保存失败：\(detail)"
        case (.pluginsDirectoryCreateFailed(let detail), .en):
            return "Failed to create plugins folder: \(detail)"
        case (.pluginsDirectoryCreateFailed(let detail), .zhHans):
            return "插件目录创建失败：\(detail)"
        case (.missingRequiredParameters(let names), .en):
            return "Fill required parameters first: \(names.joined(separator: ", "))"
        case (.missingRequiredParameters(let names), .zhHans):
            return "请先填写必填参数：\(names.joined(separator: "、"))"
        case (.updateCheckURLMissing, .en):
            return "Update check URL is not configured"
        case (.updateCheckURLMissing, .zhHans):
            return "未配置更新检查地址"
        case (.alreadyLatestVersion, .en):
            return "You are on the latest version"
        case (.alreadyLatestVersion, .zhHans):
            return "当前已是最新版本"
        case (.updateCheckFailed(let detail), .en):
            return "Failed to check for updates: \(detail)"
        case (.updateCheckFailed(let detail), .zhHans):
            return "检查更新失败：\(detail)"
        case (.downloadingUpdate, .en):
            return "Downloading update..."
        case (.downloadingUpdate, .zhHans):
            return "正在下载更新..."
        case (.installingUpdate, .en):
            return "Installing update..."
        case (.installingUpdate, .zhHans):
            return "正在安装更新..."
        case (.updateFailed(let detail), .en):
            return "Update failed: \(detail)"
        case (.updateFailed(let detail), .zhHans):
            return "更新失败：\(detail)"
        case (.launchAtLoginFailed(let detail), .en):
            return "Failed to update launch at login: \(detail)"
        case (.launchAtLoginFailed(let detail), .zhHans):
            return "开机启动设置失败：\(detail)"
        }
    }
}
