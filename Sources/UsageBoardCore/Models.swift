@preconcurrency import Foundation

public enum DisplayMode: String, Codable, CaseIterable, Identifiable, Sendable {
    case grouped
    case tabs

    public var id: String { rawValue }
}

public enum UsageDisplayStyle: String, Codable, CaseIterable, Identifiable, Sendable {
    case percent
    case ratio

    public var id: String { rawValue }
}

public enum UsageStatus: String, Codable, CaseIterable, Identifiable, Sendable {
    case normal
    case warning
    case critical
    case unknown

    public var id: String { rawValue }
}

public enum PluginParameterType: String, Codable, CaseIterable, Identifiable, Sendable {
    case string
    case secret
    case integer
    case boolean
    case choice

    public var id: String { rawValue }
}

public struct PluginParameterOption: Codable, Equatable, Identifiable, Sendable {
    public var label: String
    public var value: String

    public var id: String { value }

    public init(label: String, value: String) {
        self.label = label
        self.value = value
    }
}

public struct PluginParameterMetadata: Codable, Equatable, Identifiable, Sendable {
    public var name: String
    public var label: String
    public var type: PluginParameterType
    public var required: Bool
    public var placeholder: String?
    public var defaultValue: String?
    public var options: [PluginParameterOption]

    public var id: String { name }

    public init(
        name: String,
        label: String? = nil,
        type: PluginParameterType = .string,
        required: Bool = false,
        placeholder: String? = nil,
        defaultValue: String? = nil,
        options: [PluginParameterOption] = []
    ) {
        self.name = name
        self.label = label ?? name
        self.type = type
        self.required = required
        self.placeholder = placeholder
        self.defaultValue = defaultValue
        self.options = options
    }

    private enum CodingKeys: String, CodingKey {
        case name
        case label
        case type
        case required
        case placeholder
        case defaultValue
        case options
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        name = try container.decode(String.self, forKey: .name)
        label = try container.decodeIfPresent(String.self, forKey: .label) ?? name
        type = try container.decodeIfPresent(PluginParameterType.self, forKey: .type) ?? .string
        required = try container.decodeIfPresent(Bool.self, forKey: .required) ?? false
        placeholder = try container.decodeIfPresent(String.self, forKey: .placeholder)
        defaultValue = try container.decodeIfPresent(String.self, forKey: .defaultValue)
        options = try container.decodeIfPresent([PluginParameterOption].self, forKey: .options) ?? []
    }
}

public struct PluginMetadata: Codable, Equatable, Sendable {
    public var name: String?
    public var description: String?
    public var icon: String?
    public var parameters: [PluginParameterMetadata]

    public init(
        name: String? = nil,
        description: String? = nil,
        icon: String? = nil,
        parameters: [PluginParameterMetadata] = []
    ) {
        self.name = name
        self.description = description
        self.icon = icon
        self.parameters = parameters
    }

    private enum CodingKeys: String, CodingKey {
        case name
        case description
        case icon
        case parameters
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        name = try container.decodeIfPresent(String.self, forKey: .name)
        description = try container.decodeIfPresent(String.self, forKey: .description)
        icon = try container.decodeIfPresent(String.self, forKey: .icon)
        parameters = try container.decodeIfPresent([PluginParameterMetadata].self, forKey: .parameters) ?? []
    }
}

public struct AppConfiguration: Codable, Equatable, Sendable {
    public var schemaVersion: Int
    public var overviewDisplayMode: DisplayMode
    public var plugins: [PluginConfiguration]
    public var launchAtLogin: Bool

    public init(
        schemaVersion: Int = 1,
        overviewDisplayMode: DisplayMode = .tabs,
        plugins: [PluginConfiguration] = [],
        launchAtLogin: Bool = false
    ) {
        self.schemaVersion = schemaVersion
        self.overviewDisplayMode = overviewDisplayMode
        self.plugins = plugins
        self.launchAtLogin = launchAtLogin
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion
        case overviewDisplayMode
        case plugins
        case launchAtLogin
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(Int.self, forKey: .schemaVersion) ?? 1
        overviewDisplayMode = try container.decodeIfPresent(DisplayMode.self, forKey: .overviewDisplayMode) ?? .tabs
        plugins = try container.decodeIfPresent([PluginConfiguration].self, forKey: .plugins) ?? []
        launchAtLogin = try container.decodeIfPresent(Bool.self, forKey: .launchAtLogin) ?? false
    }
}

public struct PluginConfiguration: Codable, Equatable, Identifiable, Sendable {
    public var id: UUID
    public var stateID: String
    public var name: String
    public var enabled: Bool
    public var executablePath: String
    public var refreshIntervalSeconds: Int
    public var metadata: PluginMetadata?
    public var parameterValues: [String: String]

    public init(
        id: UUID = UUID(),
        stateID: String = UUID().uuidString,
        name: String,
        enabled: Bool = true,
        executablePath: String,
        refreshIntervalSeconds: Int = 300,
        metadata: PluginMetadata? = nil,
        parameterValues: [String: String] = [:]
    ) {
        self.id = id
        self.stateID = stateID
        self.name = name
        self.enabled = enabled
        self.executablePath = executablePath
        self.refreshIntervalSeconds = refreshIntervalSeconds
        self.metadata = metadata
        self.parameterValues = parameterValues
    }

    private enum CodingKeys: String, CodingKey {
        case stateID
        case name
        case enabled
        case executablePath
        case refreshIntervalSeconds
        case metadata
        case parameterValues
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = UUID()
        stateID = try container.decodeIfPresent(String.self, forKey: .stateID) ?? UUID().uuidString
        name = try container.decodeIfPresent(String.self, forKey: .name) ?? "Untitled"
        enabled = try container.decodeIfPresent(Bool.self, forKey: .enabled) ?? true
        executablePath = try container.decodeIfPresent(String.self, forKey: .executablePath) ?? ""
        refreshIntervalSeconds = try container.decodeIfPresent(Int.self, forKey: .refreshIntervalSeconds) ?? 300
        metadata = try container.decodeIfPresent(PluginMetadata.self, forKey: .metadata)
        parameterValues = try container.decodeIfPresent([String: String].self, forKey: .parameterValues) ?? [:]
    }
}

public struct PluginOutput: Decodable, Equatable, Sendable {
    public var updatedAt: Date
    public var items: [UsageItem]
    public var badge: String?

    public init(updatedAt: Date, items: [UsageItem], badge: String? = nil) {
        self.updatedAt = updatedAt
        self.items = items
        self.badge = badge
    }
}

public struct UsageItem: Codable, Equatable, Identifiable, Sendable {
    public var id: String
    public var name: String
    public var used: Double
    public var limit: Double
    public var displayStyle: UsageDisplayStyle
    public var resetAt: Date?
    public var status: UsageStatus
    public var color: String?

    public init(
        id: String,
        name: String,
        used: Double,
        limit: Double,
        displayStyle: UsageDisplayStyle,
        resetAt: Date? = nil,
        status: UsageStatus = .unknown,
        color: String? = nil
    ) {
        self.id = id
        self.name = name
        self.used = used
        self.limit = limit
        self.displayStyle = displayStyle
        self.resetAt = resetAt
        self.status = status
        self.color = color
    }

    public var progress: Double {
        guard limit > 0 else { return 0 }
        return min(max(used / limit, 0), 1)
    }

    public func displayValue() -> String {
        switch displayStyle {
        case .percent:
            return "\(Int((progress * 100).rounded()))%"
        case .ratio:
            return "\(UsageItem.formatNumber(used)) / \(UsageItem.formatNumber(limit))"
        }
    }

    public func resetText(now: Date = Date()) -> String {
        guard let resetAt, resetAt > now else { return "--" }
        let calendar = Calendar.current
        let time = resetAt.formatted(date: .omitted, time: .shortened)
        if calendar.isDate(resetAt, inSameDayAs: now) {
            return "今天 \(time)"
        }
        if let tomorrow = calendar.date(byAdding: .day, value: 1, to: now), calendar.isDate(resetAt, inSameDayAs: tomorrow) {
            return "明天 \(time)"
        }
        let date = resetAt.formatted(.dateTime.month(.defaultDigits).day(.defaultDigits))
        return "\(date) \(time)"
    }

    private static func formatNumber(_ value: Double) -> String {
        if value.rounded() == value {
            return String(Int(value))
        }
        return String(format: "%.2f", value)
    }
}

public enum PluginSnapshotState: Equatable, Sendable {
    case idle
    case loading
    case ready
    case failed(String)
}

public struct PluginSnapshot: Equatable, Identifiable, Sendable {
    public var id: UUID
    public var pluginName: String
    public var displayName: String
    public var state: PluginSnapshotState
    public var items: [UsageItem]
    public var updatedAt: Date?
    public var badge: String?
    public var iconURL: String?

    public init(
        id: UUID,
        pluginName: String,
        displayName: String,
        state: PluginSnapshotState = .idle,
        items: [UsageItem] = [],
        updatedAt: Date? = nil,
        badge: String? = nil,
        iconURL: String? = nil
    ) {
        self.id = id
        self.pluginName = pluginName
        self.displayName = displayName
        self.state = state
        self.items = items
        self.updatedAt = updatedAt
        self.badge = badge
        self.iconURL = iconURL
    }
}

public struct PluginCachedState: Codable, Equatable, Sendable {
    public var updatedAt: Date
    public var items: [UsageItem]
    public var badge: String?

    public init(updatedAt: Date, items: [UsageItem], badge: String? = nil) {
        self.updatedAt = updatedAt
        self.items = items
        self.badge = badge
    }
}
