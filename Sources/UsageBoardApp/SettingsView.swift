import AppKit
import SwiftUI
import UsageBoardCore

// MARK: - Tab Enum

enum SettingsTab: CaseIterable, Identifiable {
    case general
    case plugins
    case about

    var id: Self { self }

    var icon: String {
        switch self {
        case .general: return "gear"
        case .plugins: return "powerplug"
        case .about: return "info.circle"
        }
    }
}

// MARK: - Main Settings View

struct SettingsView: View {
    @ObservedObject var store: UsageBoardStore
    @State private var selectedTab: SettingsTab = .general

    private var strings: AppLocalization {
        AppLocalization(language: store.activeLanguage)
    }

    var body: some View {
        HStack(spacing: 0) {
            // Sidebar
            sidebar

            Divider()

            // Content
            VStack(spacing: 0) {
                // Page header
                pageHeader

                Divider()

                // Content area
                switch selectedTab {
                case .general:
                    ScrollView {
                        GeneralSettingsView(store: store)
                            .padding(20)
                    }
                case .plugins:
                    PluginSettingsView(store: store)
                case .about:
                    AboutView(store: store)
                }
            }
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }

    // MARK: Sidebar

    private var sidebar: some View {
        VStack(spacing: 0) {
            VStack(spacing: 6) {
                AppIconSquircle(size: 44)
                Text("UsageBoard")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 14)
            .padding(.bottom, 14)

            VStack(alignment: .leading, spacing: 2) {
                ForEach(SettingsTab.allCases) { tab in
                    sidebarItem(tab)
                }
            }
            .padding(.horizontal, 10)

            Spacer()

            Text("v\(currentVersionString)")
                .font(.system(size: 10.5))
                .foregroundStyle(.tertiary)
                .frame(maxWidth: .infinity)
                .padding(.bottom, 8)
        }
        .frame(width: 188)
        .background(.regularMaterial)
    }

    private var currentVersionString: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.0.0"
    }

    private func sidebarItem(_ tab: SettingsTab) -> some View {
        Button {
            selectedTab = tab
        } label: {
            HStack(spacing: 8) {
                Image(systemName: tab.icon)
                    .font(.system(size: 13))
                    .frame(width: 16)
                Text(strings.tabTitle(tab))
                    .font(.system(size: 13))
                Spacer()
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(selectedTab == tab ? Color.accentColor : Color.clear)
            )
            .foregroundStyle(selectedTab == tab ? Color.white : Color.primary)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // MARK: Page Header

    private var pageHeader: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(strings.tabTitle(selectedTab))
                .font(.system(size: 20, weight: .semibold))
            Text(strings.tabSubtitle(selectedTab))
                .font(.system(size: 13))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
        .background(Color(nsColor: .windowBackgroundColor))
    }
}

// MARK: - General Settings

struct GeneralSettingsView: View {
    @ObservedObject var store: UsageBoardStore
    private var strings: AppLocalization {
        AppLocalization(language: store.activeLanguage)
    }

    var body: some View {
        SettingsSection {
            SettingsRow(label: strings.text(.launchAtLogin), hint: strings.text(.launchAtLoginHint)) {
                Toggle("", isOn: $store.configuration.launchAtLogin)
                    .toggleStyle(.switch)
                    .labelsHidden()
                    .onChange(of: store.configuration.launchAtLogin) { newValue in
                        store.toggleLaunchAtLogin(newValue)
                        store.saveConfiguration()
                    }
                    .frame(width: 120, alignment: .leading)
            }

            SettingsRow(label: strings.text(.displayMode), hint: strings.text(.displayModeHint)) {
                Picker("", selection: $store.configuration.overviewDisplayMode) {
                    ForEach(DisplayMode.allCases) { mode in
                        Text(strings.displayModeName(mode)).tag(mode)
                    }
                }
                .labelsHidden()
                .frame(width: 120, alignment: .leading)
                .onChange(of: store.configuration.overviewDisplayMode) { _ in
                    store.saveConfiguration()
                }
            }

            SettingsRow(label: strings.text(.language)) {
                Picker("", selection: $store.configuration.language) {
                    ForEach(AppLanguage.allCases) { language in
                        Text(language.displayName).tag(language)
                    }
                }
                .labelsHidden()
                .frame(width: 120, alignment: .leading)
                .onChange(of: store.configuration.language) { newValue in
                    store.saveConfiguration()
                    if newValue != store.activeLanguage {
                        showRestartRequiredAlert()
                    }
                }
            }
        }
    }

    private func showRestartRequiredAlert() {
        let alert = NSAlert()
        alert.messageText = strings.text(.restartRequiredTitle)
        alert.informativeText = strings.text(.restartRequiredMessage)
        alert.alertStyle = .informational
        alert.addButton(withTitle: strings.text(.restartNow))
        alert.addButton(withTitle: strings.text(.restartLater))

        if alert.runModal() == .alertFirstButtonReturn {
            do {
                try AppRelauncher.relaunchCurrent()
                NSApp.terminate(nil)
            } catch {
                store.lastError = "\(strings.text(.relaunchFailed)): \(error.localizedDescription)"
            }
        }
    }
}

// MARK: - Plugin Settings

struct PluginSettingsView: View {
    @ObservedObject var store: UsageBoardStore
    @State private var selectedPluginID: UUID?
    @State private var draggingPluginID: UUID?
    @State private var draft: PluginConfiguration?
    @State private var searchText = ""
    private var strings: AppLocalization {
        AppLocalization(language: store.activeLanguage)
    }

    private var hasChanges: Bool {
        guard let id = selectedPluginID,
              let original = store.configuration.plugins.first(where: { $0.id == id }),
              let draft else { return false }
        return draft.name != original.name
            || draft.executablePath != original.executablePath
            || draft.refreshIntervalSeconds != original.refreshIntervalSeconds
            || draft.parameterValues != original.parameterValues
    }

    private var filteredPlugins: [PluginConfiguration] {
        guard !searchText.isEmpty else { return store.configuration.plugins }
        let needle = searchText.lowercased()
        return store.configuration.plugins.filter {
            PluginDisplayNames.displayName(for: $0, language: store.activeLanguage)
                .lowercased()
                .contains(needle)
        }
    }

    var body: some View {
        HStack(spacing: 0) {
            // Plugin list sidebar
            VStack(spacing: 0) {
                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 11))
                        .foregroundStyle(.tertiary)
                    TextField(store.activeLanguage == .en ? "Search plugins" : "搜索插件", text: $searchText)
                        .textFieldStyle(.plain)
                        .font(.system(size: 11.5))
                }
                .padding(.horizontal, 8)
                .frame(height: 22)
                .background(Color.black.opacity(0.05))
                .clipShape(RoundedRectangle(cornerRadius: 5))
                .padding(.horizontal, 10)
                .padding(.top, 10)
                .padding(.bottom, 6)

                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(filteredPlugins) { plugin in
                            pluginListRow(plugin)
                                .tag(plugin.id)
                                .onTapGesture {
                                    loadDraft(for: plugin.id)
                                }
                                .onDrag {
                                    draggingPluginID = plugin.id
                                    return NSItemProvider(object: plugin.id.uuidString as NSString)
                                }
                                .onDrop(of: [.text], delegate: PluginDropDelegate(
                                    plugins: $store.configuration.plugins,
                                    targetID: plugin.id,
                                    draggingID: $draggingPluginID,
                                    onDropCompleted: { store.saveConfiguration() }
                                ))
                        }
                    }
                }
                .frame(maxHeight: .infinity)

                Divider()

                // Add/Remove buttons
                HStack(spacing: 4) {
                    Button {
                        choosePlugin()
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 12))
                            .frame(width: 24, height: 24)
                    }
                    .buttonStyle(.borderless)

                    Button {
                        if let id = selectedPluginID {
                            store.removePlugin(id: id)
                            selectedPluginID = nil
                            draft = nil
                        }
                    } label: {
                        Image(systemName: "minus")
                            .font(.system(size: 12))
                            .frame(width: 24, height: 24)
                    }
                    .buttonStyle(.borderless)
                    .disabled(selectedPluginID == nil)

                    Spacer()

                    Button {
                        NSWorkspace.shared.open(store.pluginsDirectoryURL)
                    } label: {
                        Image(systemName: "folder")
                            .font(.system(size: 12))
                            .frame(width: 24, height: 24)
                    }
                    .buttonStyle(.borderless)
                    .help(strings.text(.openPluginsFolder))

                    Button {
                        openPluginHelp()
                    } label: {
                        Image(systemName: "questionmark.circle")
                            .font(.system(size: 12))
                            .frame(width: 24, height: 24)
                    }
                    .buttonStyle(.borderless)
                    .help(strings.text(.pluginAuthoringGuide))
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
            }
            .frame(width: 220)
            .frame(maxHeight: .infinity)
            .background(Color(nsColor: .controlBackgroundColor).opacity(0.7))

            Divider()

            // Plugin detail
            if let draft, draft.id == selectedPluginID {
                VStack(spacing: 0) {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 12) {
                            if let lastError = store.lastError {
                                Text(lastError)
                                    .font(.system(size: 12))
                                    .foregroundStyle(.red)
                                    .padding(10)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .background(Color.red.opacity(0.08))
                                    .clipShape(RoundedRectangle(cornerRadius: 8))
                            }

                            PluginSettingsCard(
                                plugin: draftBinding,
                                enabled: pluginEnabledBinding(draft),
                                pluginsDirectoryURL: store.pluginsDirectoryURL,
                                language: store.activeLanguage,
                                displayName: PluginDisplayNames.displayName(for: draft, language: store.activeLanguage)
                            ) {
                                reloadDraftMetadata()
                            } onRemove: {
                                store.removePlugin(id: draft.id)
                                selectedPluginID = nil
                                self.draft = nil
                            }
                        }
                        .padding(20)
                    }

                    Divider()

                    // Save / Reset buttons
                    HStack {
                        Spacer()
                        Button(strings.text(.reset)) {
                            loadDraft(for: draft.id)
                        }
                        .disabled(!hasChanges)
                        Button(strings.text(.save)) {
                            saveDraft()
                        }
                        .disabled(!hasChanges)
                        .buttonStyle(.borderedProminent)
                    }
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                    .background(Color(nsColor: .windowBackgroundColor).opacity(0.7))
                }
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "puzzlepiece.extension")
                        .font(.system(size: 28))
                        .foregroundStyle(.tertiary)
                    Text(strings.text(.selectPlugin))
                        .font(.system(size: 13))
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(minHeight: 400)
        .onAppear {
            if selectedPluginID == nil {
                selectedPluginID = store.configuration.plugins.first?.id
            }
            if let id = selectedPluginID {
                loadDraft(for: id)
            }
        }
    }

    private var draftBinding: Binding<PluginConfiguration> {
        Binding(
            get: { draft ?? PluginConfiguration(name: "", executablePath: "") },
            set: { draft = $0 }
        )
    }

    private func loadDraft(for id: UUID) {
        selectedPluginID = id
        if let plugin = store.configuration.plugins.first(where: { $0.id == id }) {
            draft = plugin
        }
    }

    private func saveDraft() {
        guard let draft else { return }
        guard let index = store.configuration.plugins.firstIndex(where: { $0.id == draft.id }) else { return }
        store.configuration.plugins[index].name = draft.name
        store.configuration.plugins[index].executablePath = draft.executablePath
        store.configuration.plugins[index].refreshIntervalSeconds = draft.refreshIntervalSeconds
        store.configuration.plugins[index].metadata = draft.metadata
        store.configuration.plugins[index].parameterValues = draft.parameterValues
        self.draft = store.configuration.plugins[index]
        store.saveConfiguration()
    }

    private func reloadDraftMetadata() {
        guard let draft else { return }
        let fileURL = URL(fileURLWithPath: draft.executablePath)
        let metadata = PluginMetadataParser.parse(fileURL: fileURL)
        var updated = draft
        updated.metadata = metadata
        for parameter in metadata?.parameters ?? [] where updated.parameterValues[parameter.name] == nil {
            updated.parameterValues[parameter.name] = parameter.defaultValue ?? ""
        }
        self.draft = updated
    }

    private func pluginListRow(_ plugin: PluginConfiguration) -> some View {
        HStack(spacing: 8) {
            BrandTile(
                iconURL: plugin.metadata?.icon,
                fallbackName: PluginDisplayNames.displayName(for: plugin, language: store.activeLanguage),
                size: 22
            )
            Text(PluginDisplayNames.displayName(for: plugin, language: store.activeLanguage))
                .font(.system(size: 12.5, weight: selectedPluginID == plugin.id ? .semibold : .regular))
                .foregroundStyle(plugin.enabled ? Color.primary : Color.secondary)
                .lineLimit(1)
            Spacer()
            Toggle("", isOn: pluginEnabledBinding(plugin))
                .labelsHidden()
                .toggleStyle(.switch)
                .controlSize(.mini)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(selectedPluginID == plugin.id ? Color.black.opacity(0.06) : Color.clear)
        )
        .contentShape(Rectangle())
    }

    private func pluginEnabledBinding(_ plugin: PluginConfiguration) -> Binding<Bool> {
        Binding(
            get: {
                store.configuration.plugins.first(where: { $0.id == plugin.id })?.enabled ?? false
            },
            set: { newValue in
                store.setPluginEnabled(id: plugin.id, enabled: newValue)
                if draft?.id == plugin.id {
                    draft?.enabled = newValue
                }
            }
        )
    }

    private func choosePlugin() {
        store.ensurePluginsDirectory()
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = false
        panel.directoryURL = store.pluginsDirectoryURL
        if panel.runModal() == .OK, let url = panel.url {
            store.addPlugin(fileURL: url)
            let newID = store.configuration.plugins.last?.id
            selectedPluginID = newID
            if let newID { loadDraft(for: newID) }
        }
    }

    private func openPluginHelp() {
        if let url = Bundle.main.url(forResource: "PluginAuthoringGuide", withExtension: "html") {
            NSWorkspace.shared.open(url)
            return
        }

        let developmentURL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources/PluginAuthoringGuide.html")
        if FileManager.default.fileExists(atPath: developmentURL.path) {
            NSWorkspace.shared.open(developmentURL)
            return
        }

        store.lastError = store.activeLanguage == .en
            ? "Plugin authoring guide was not found"
            : "未找到插件编写说明文档"
    }
}

// MARK: - About View

struct AboutView: View {
    @ObservedObject var store: UsageBoardStore
    @State private var isUserChecking = false
    private var strings: AppLocalization {
        AppLocalization(language: store.activeLanguage)
    }

    private var currentVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? strings.text(.unknownVersion)
    }

    var body: some View {
        HStack(alignment: .top, spacing: 22) {
            AppIconSquircle(size: 88)
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("UsageBoard")
                        .font(.system(size: 20, weight: .bold))
                        .tracking(-0.3)
                    Text(strings.text(.aboutDescription))
                        .font(.system(size: 12))
                        .foregroundStyle(.tertiary)
                }

                HStack(spacing: 10) {
                    Text(strings.text(.version))
                        .font(.system(size: 12.5))
                        .foregroundStyle(.secondary)
                    Text(currentVersion)
                        .font(.system(size: 12.5))
                        .monospacedDigit()
                    Button(store.isUpdating ? strings.text(.checkingUpdate) : strings.text(.checkForUpdates)) {
                        isUserChecking = true
                        store.checkForUpdates()
                    }
                    .controlSize(.regular)
                    .disabled(store.isUpdating)
                    if store.isUpdating {
                        ProgressView()
                            .controlSize(.small)
                    } else if let updateMessage = store.updateMessage {
                        Text(updateMessage)
                            .font(.system(size: 11.5))
                            .lineLimit(1)
                            .foregroundStyle(.tertiary)
                    }
                }
            }
            Spacer()
        }
        .padding(.horizontal, 32)
        .padding(.top, 28)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .onChange(of: store.availableUpdate) { newValue in
            guard isUserChecking, let newValue else { return }
            isUserChecking = false
            showUpdateAlert(newValue)
        }
    }

    private func showUpdateAlert(_ info: UpdateInfo) {
        let alert = NSAlert()
        if store.activeLanguage == .en {
            alert.messageText = "New version \(info.latestVersion) available"
            alert.informativeText = info.notes?.isEmpty == false ? info.notes! : "Current version \(currentVersion), new version \(info.latestVersion).\nDownload and update now?"
            alert.addButton(withTitle: "Update")
            alert.addButton(withTitle: "Cancel")
        } else {
            alert.messageText = "发现新版本 \(info.latestVersion)"
            alert.informativeText = info.notes?.isEmpty == false ? info.notes! : "当前版本 \(currentVersion)，新版本 \(info.latestVersion)。\n是否立即下载并更新？"
            alert.addButton(withTitle: "更新")
            alert.addButton(withTitle: "取消")
        }
        alert.alertStyle = .informational

        if alert.runModal() == .alertFirstButtonReturn {
            store.performUpdate()
        }
    }
}

// MARK: - Shared Components

struct SettingsSection<Content: View>: View {
    var title: String?
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let title {
                Text(title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(.primary)
            }
            VStack(alignment: .leading, spacing: 0) {
                content
            }
            .background(Color(nsColor: .controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }
}

struct SettingsRow<Content: View>: View {
    var label: String
    var hint: String? = nil
    @ViewBuilder var value: Content

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 16) {
            VStack(alignment: .trailing, spacing: 2) {
                Text(label)
                    .font(UB.Font.formLabel)
                    .foregroundStyle(.primary)
                if let hint {
                    Text(hint)
                        .font(.system(size: 11))
                        .foregroundStyle(.tertiary)
                }
            }
            .frame(width: 180, alignment: .trailing)
            value
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 8)
    }
}

struct PluginSettingsCard: View {
    @Binding var plugin: PluginConfiguration
    var enabled: Binding<Bool>
    var pluginsDirectoryURL: URL
    var language: AppLanguage
    var displayName: String
    var onReloadMetadata: () -> Void
    var onRemove: () -> Void

    private var strings: AppLocalization {
        AppLocalization(language: language)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header
            HStack(spacing: 10) {
                BrandTile(iconURL: plugin.metadata?.icon, fallbackName: displayName, size: 28)
                VStack(alignment: .leading, spacing: 2) {
                    Text(displayName)
                        .font(UB.Font.detailTitle)
                    if let desc = plugin.metadata?.localizedDescription(language: language), !desc.isEmpty {
                        Text(desc)
                            .font(.system(size: 11.5))
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                Toggle(strings.text(.enabled), isOn: enabled)
            }

            Divider()

            // Fields
            VStack(alignment: .leading, spacing: 0) {
                pluginRow(strings.text(.name)) {
                    TextField(strings.text(.pluginNamePlaceholder), text: $plugin.name)
                        .textFieldStyle(.roundedBorder)
                }

                pluginRow(strings.text(.script)) {
                    HStack(spacing: 4) {
                        TextField(strings.text(.scriptPathPlaceholder), text: $plugin.executablePath)
                            .textFieldStyle(.roundedBorder)
                        Button {
                            chooseExecutable()
                        } label: {
                            Image(systemName: "folder")
                                .font(.system(size: 12))
                        }
                        .buttonStyle(.borderless)
                        Button {
                            onReloadMetadata()
                        } label: {
                            Image(systemName: "arrow.clockwise")
                                .font(.system(size: 12))
                        }
                        .buttonStyle(.borderless)
                    }
                }

                pluginRow(strings.text(.refreshInterval)) {
                    HStack(spacing: 4) {
                        TextField(strings.text(.seconds), value: $plugin.refreshIntervalSeconds, format: .number)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 80)
                        Text(strings.text(.seconds))
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .background(Color(nsColor: .controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 8))

            // Plugin parameters
            if let metadata = plugin.metadata, !metadata.parameters.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text(strings.text(.pluginParameters).uppercased())
                        .font(.system(size: 11.5, weight: .semibold))
                        .tracking(0.4)
                        .foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(metadata.parameters) { parameter in
                            PluginParameterField(plugin: $plugin, parameter: parameter, language: language)
                        }
                    }
                    .background(Color(nsColor: .controlBackgroundColor))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
            } else {
                Text(strings.text(.noParameterMetadata))
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func pluginRow<Content: View>(_ label: String, @ViewBuilder value: () -> Content) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 13))
                .lineLimit(1)
                .frame(width: 100, alignment: .trailing)
                .foregroundStyle(.primary)
            value()
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 10)
    }

    private func chooseExecutable() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = false
        panel.directoryURL = pluginsDirectoryURL
        if panel.runModal() == .OK, let url = panel.url {
            plugin.executablePath = url.path
        }
    }
}

struct PluginParameterField: View {
    @Binding var plugin: PluginConfiguration
    var parameter: PluginParameterMetadata
    var language: AppLanguage

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                HStack(spacing: 2) {
                    Text(parameter.localizedLabel(language: language))
                        .font(.system(size: 13))
                        .lineLimit(1)
                    if parameter.required {
                        Text("*")
                            .foregroundStyle(.red)
                    }
                }
                .frame(width: 100, alignment: .trailing)
                input
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 10)
    }

    @ViewBuilder
    private var input: some View {
        switch parameter.type {
        case .secret:
            SecureField(parameter.localizedPlaceholder(language: language) ?? "", text: valueBinding)
                .textFieldStyle(.roundedBorder)
        case .integer:
            TextField(parameter.localizedPlaceholder(language: language) ?? "", text: valueBinding)
                .textFieldStyle(.roundedBorder)
                .frame(width: 160)
        case .boolean:
            Toggle("", isOn: boolBinding)
                .labelsHidden()
        case .choice:
            Picker("", selection: valueBinding) {
                ForEach(parameter.options) { option in
                    Text(option.localizedLabel(language: language)).tag(option.value)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
        case .string:
            TextField(parameter.localizedPlaceholder(language: language) ?? "", text: valueBinding)
                .textFieldStyle(.roundedBorder)
        case .directory:
            HStack(spacing: 6) {
                TextField(parameter.localizedPlaceholder(language: language) ?? "", text: valueBinding)
                    .textFieldStyle(.roundedBorder)
                Button {
                    let panel = NSOpenPanel()
                    panel.title = parameter.localizedLabel(language: language)
                    panel.canChooseFiles = false
                    panel.canChooseDirectories = true
                    panel.allowsMultipleSelection = false
                    panel.canCreateDirectories = false
                    let current = valueBinding.wrappedValue
                    if !current.isEmpty {
                        let expanded = NSString(string: current).expandingTildeInPath
                        let url = URL(fileURLWithPath: expanded)
                        panel.directoryURL = url
                    }
                    if panel.runModal() == .OK, let url = panel.url {
                        valueBinding.wrappedValue = url.path
                    }
                } label: {
                    Image(systemName: "folder")
                }
                .buttonStyle(.borderless)
            }
        case .file:
            HStack(spacing: 6) {
                TextField(parameter.localizedPlaceholder(language: language) ?? "", text: valueBinding)
                    .textFieldStyle(.roundedBorder)
                Button {
                    let panel = NSOpenPanel()
                    panel.title = parameter.localizedLabel(language: language)
                    panel.canChooseFiles = true
                    panel.canChooseDirectories = false
                    panel.allowsMultipleSelection = false
                    if panel.runModal() == .OK, let url = panel.url {
                        valueBinding.wrappedValue = url.path
                    }
                } label: {
                    Image(systemName: "doc")
                }
                .buttonStyle(.borderless)
            }
        }
    }

    private var valueBinding: Binding<String> {
        Binding(
            get: { plugin.parameterValues[parameter.name] ?? parameter.defaultValue ?? "" },
            set: { plugin.parameterValues[parameter.name] = $0 }
        )
    }

    private var boolBinding: Binding<Bool> {
        Binding(
            get: {
                let value = plugin.parameterValues[parameter.name] ?? parameter.defaultValue ?? "false"
                return ["1", "true", "yes", "on"].contains(value.lowercased())
            },
            set: { plugin.parameterValues[parameter.name] = $0 ? "true" : "false" }
        )
    }
}

// MARK: - Drag & Drop

struct PluginDropDelegate: DropDelegate {
    @Binding var plugins: [PluginConfiguration]
    let targetID: UUID
    @Binding var draggingID: UUID?
    var onDropCompleted: () -> Void

    func dropUpdated(info: DropInfo) -> DropProposal? {
        DropProposal(operation: .move)
    }

    func performDrop(info: DropInfo) -> Bool {
        guard let draggingID else { return false }
        guard let fromIndex = plugins.firstIndex(where: { $0.id == draggingID }),
              let toIndex = plugins.firstIndex(where: { $0.id == targetID }),
              fromIndex != toIndex else {
            self.draggingID = nil
            return false
        }
        let moved = plugins.remove(at: fromIndex)
        plugins.insert(moved, at: toIndex > fromIndex ? toIndex : toIndex)
        self.draggingID = nil
        onDropCompleted()
        return true
    }
}
