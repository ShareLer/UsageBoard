@preconcurrency import Foundation

private struct AnyCodingKey: CodingKey {
    var stringValue: String
    var intValue: Int?

    init(stringValue: String) {
        self.stringValue = stringValue
        self.intValue = nil
    }

    init?(intValue: Int) {
        self.stringValue = String(intValue)
        self.intValue = intValue
    }
}

public enum AppLanguage: String, Codable, CaseIterable, Identifiable, Sendable {
    case zhHans = "zh-Hans"
    case en

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .zhHans: return "中文"
        case .en: return "English"
        }
    }
}

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
    case directory
    case file

    public var id: String { rawValue }
}

public struct PluginParameterOption: Codable, Equatable, Identifiable, Sendable {
    public var label: String
    public var labelTranslations: [String: String]
    public var value: String

    public var id: String { value }

    public init(label: String, value: String, labelTranslations: [String: String] = [:]) {
        self.label = label
        self.labelTranslations = labelTranslations
        self.value = value
    }

    private enum CodingKeys: String, CodingKey {
        case label
        case value
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let dynamicContainer = try decoder.container(keyedBy: AnyCodingKey.self)
        label = try container.decode(String.self, forKey: .label)
        value = try container.decode(String.self, forKey: .value)
        labelTranslations = Self.decodeTranslations(prefix: "label@", from: dynamicContainer)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: AnyCodingKey.self)
        try container.encode(label, forKey: AnyCodingKey(stringValue: CodingKeys.label.rawValue))
        try container.encode(value, forKey: AnyCodingKey(stringValue: CodingKeys.value.rawValue))
        try Self.encodeTranslations(labelTranslations, prefix: "label@", to: &container)
    }

    public func localizedLabel(language: AppLanguage) -> String {
        Self.localizedValue(base: label, translations: labelTranslations, language: language)
    }
}

public struct PluginParameterMetadata: Codable, Equatable, Identifiable, Sendable {
    public var name: String
    public var label: String
    public var labelTranslations: [String: String]
    public var type: PluginParameterType
    public var required: Bool
    public var placeholder: String?
    public var placeholderTranslations: [String: String]
    public var defaultValue: String?
    public var options: [PluginParameterOption]

    public var id: String { name }

    public init(
        name: String,
        label: String? = nil,
        labelTranslations: [String: String] = [:],
        type: PluginParameterType = .string,
        required: Bool = false,
        placeholder: String? = nil,
        placeholderTranslations: [String: String] = [:],
        defaultValue: String? = nil,
        options: [PluginParameterOption] = []
    ) {
        self.name = name
        self.label = label ?? name
        self.labelTranslations = labelTranslations
        self.type = type
        self.required = required
        self.placeholder = placeholder
        self.placeholderTranslations = placeholderTranslations
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
        let dynamicContainer = try decoder.container(keyedBy: AnyCodingKey.self)
        name = try container.decode(String.self, forKey: .name)
        label = try container.decodeIfPresent(String.self, forKey: .label) ?? name
        labelTranslations = Self.decodeTranslations(prefix: "label@", from: dynamicContainer)
        type = try container.decodeIfPresent(PluginParameterType.self, forKey: .type) ?? .string
        required = try container.decodeIfPresent(Bool.self, forKey: .required) ?? false
        placeholder = try container.decodeIfPresent(String.self, forKey: .placeholder)
        placeholderTranslations = Self.decodeTranslations(prefix: "placeholder@", from: dynamicContainer)
        defaultValue = try container.decodeIfPresent(String.self, forKey: .defaultValue)
        options = try container.decodeIfPresent([PluginParameterOption].self, forKey: .options) ?? []
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: AnyCodingKey.self)
        try container.encode(name, forKey: AnyCodingKey(stringValue: CodingKeys.name.rawValue))
        try container.encode(label, forKey: AnyCodingKey(stringValue: CodingKeys.label.rawValue))
        try Self.encodeTranslations(labelTranslations, prefix: "label@", to: &container)
        try container.encode(type, forKey: AnyCodingKey(stringValue: CodingKeys.type.rawValue))
        try container.encode(required, forKey: AnyCodingKey(stringValue: CodingKeys.required.rawValue))
        try container.encodeIfPresent(placeholder, forKey: AnyCodingKey(stringValue: CodingKeys.placeholder.rawValue))
        try Self.encodeTranslations(placeholderTranslations, prefix: "placeholder@", to: &container)
        try container.encodeIfPresent(defaultValue, forKey: AnyCodingKey(stringValue: CodingKeys.defaultValue.rawValue))
        try container.encode(options, forKey: AnyCodingKey(stringValue: CodingKeys.options.rawValue))
    }

    public func localizedLabel(language: AppLanguage) -> String {
        Self.localizedValue(base: label, translations: labelTranslations, language: language)
    }

    public func localizedPlaceholder(language: AppLanguage) -> String? {
        let translated = placeholderTranslations[language.rawValue]?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let translated, !translated.isEmpty {
            return placeholderTranslations[language.rawValue]
        }
        return placeholder
    }
}

public struct PluginMetadata: Codable, Equatable, Sendable {
    public var name: String?
    public var nameTranslations: [String: String]
    public var description: String?
    public var descriptionTranslations: [String: String]
    public var icon: String?
    public var parameters: [PluginParameterMetadata]

    public init(
        name: String? = nil,
        nameTranslations: [String: String] = [:],
        description: String? = nil,
        descriptionTranslations: [String: String] = [:],
        icon: String? = nil,
        parameters: [PluginParameterMetadata] = []
    ) {
        self.name = name
        self.nameTranslations = nameTranslations
        self.description = description
        self.descriptionTranslations = descriptionTranslations
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
        let dynamicContainer = try decoder.container(keyedBy: AnyCodingKey.self)
        name = try container.decodeIfPresent(String.self, forKey: .name)
        nameTranslations = Self.decodeTranslations(prefix: "name@", from: dynamicContainer)
        description = try container.decodeIfPresent(String.self, forKey: .description)
        descriptionTranslations = Self.decodeTranslations(prefix: "description@", from: dynamicContainer)
        icon = try container.decodeIfPresent(String.self, forKey: .icon)
        parameters = try container.decodeIfPresent([PluginParameterMetadata].self, forKey: .parameters) ?? []
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: AnyCodingKey.self)
        try container.encodeIfPresent(name, forKey: AnyCodingKey(stringValue: CodingKeys.name.rawValue))
        try Self.encodeTranslations(nameTranslations, prefix: "name@", to: &container)
        try container.encodeIfPresent(description, forKey: AnyCodingKey(stringValue: CodingKeys.description.rawValue))
        try Self.encodeTranslations(descriptionTranslations, prefix: "description@", to: &container)
        try container.encodeIfPresent(icon, forKey: AnyCodingKey(stringValue: CodingKeys.icon.rawValue))
        try container.encode(parameters, forKey: AnyCodingKey(stringValue: CodingKeys.parameters.rawValue))
    }

    public func localizedName(language: AppLanguage) -> String? {
        Self.localizedOptionalValue(base: name, translations: nameTranslations, language: language)
    }

    public func localizedDescription(language: AppLanguage) -> String? {
        Self.localizedOptionalValue(base: description, translations: descriptionTranslations, language: language)
    }
}

public struct AppConfiguration: Codable, Equatable, Sendable {
    public var schemaVersion: Int
    public var language: AppLanguage
    public var overviewDisplayMode: DisplayMode
    public var plugins: [PluginConfiguration]
    public var launchAtLogin: Bool

    public init(
        schemaVersion: Int = 1,
        language: AppLanguage = .zhHans,
        overviewDisplayMode: DisplayMode = .tabs,
        plugins: [PluginConfiguration] = [],
        launchAtLogin: Bool = false
    ) {
        self.schemaVersion = schemaVersion
        self.language = language
        self.overviewDisplayMode = overviewDisplayMode
        self.plugins = plugins
        self.launchAtLogin = launchAtLogin
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion
        case language
        case overviewDisplayMode
        case plugins
        case launchAtLogin
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(Int.self, forKey: .schemaVersion) ?? 1
        language = try container.decodeIfPresent(AppLanguage.self, forKey: .language) ?? .zhHans
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
    public var chart: PluginChart?

    public init(updatedAt: Date, items: [UsageItem], badge: String? = nil, chart: PluginChart? = nil) {
        self.updatedAt = updatedAt
        self.items = items
        self.badge = badge
        self.chart = chart
    }
}

public struct PluginChart: Codable, Equatable, Sendable {
    public var kind: String
    public var period: String
    public var bucketUnit: String
    public var buckets: [PluginChartBucket]
    public var message: String?

    public init(
        kind: String = "line",
        period: String,
        bucketUnit: String,
        buckets: [PluginChartBucket],
        message: String? = nil
    ) {
        self.kind = kind
        self.period = period
        self.bucketUnit = bucketUnit
        self.buckets = buckets
        self.message = message
    }
}

public struct PluginChartBucket: Codable, Equatable, Identifiable, Sendable {
    public var id: String
    public var label: String
    public var segments: [PluginChartSegment]

    public init(id: String, label: String, segments: [PluginChartSegment]) {
        self.id = id
        self.label = label
        self.segments = segments
    }

    public var total: Double {
        segments.reduce(0) { $0 + max($1.tokens, 0) }
    }
}

public struct PluginChartSegment: Codable, Equatable, Identifiable, Sendable {
    public var model: String
    public var tokens: Double

    public init(model: String, tokens: Double) {
        self.model = model
        self.tokens = tokens
    }

    public var id: String { model }
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

    public func resetText(now: Date = Date(), language: AppLanguage = .zhHans) -> String {
        guard let resetAt, resetAt > now else { return "--" }
        let calendar = Calendar.current
        let time = resetAt.formatted(date: .omitted, time: .shortened)
        if calendar.isDate(resetAt, inSameDayAs: now) {
            return language == .en ? "Today \(time)" : "今天 \(time)"
        }
        if let tomorrow = calendar.date(byAdding: .day, value: 1, to: now), calendar.isDate(resetAt, inSameDayAs: tomorrow) {
            return language == .en ? "Tomorrow \(time)" : "明天 \(time)"
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

private extension Decodable {
    static func decodeTranslations(prefix: String, from container: KeyedDecodingContainer<AnyCodingKey>) -> [String: String] {
        var translations: [String: String] = [:]
        for key in container.allKeys where key.stringValue.hasPrefix(prefix) {
            let language = String(key.stringValue.dropFirst(prefix.count))
            guard !language.isEmpty, let value = try? container.decode(String.self, forKey: key) else { continue }
            translations[language] = value
        }
        return translations
    }
}

private extension Encodable {
    static func encodeTranslations(
        _ translations: [String: String],
        prefix: String,
        to container: inout KeyedEncodingContainer<AnyCodingKey>
    ) throws {
        for (language, value) in translations where !language.isEmpty {
            try container.encode(value, forKey: AnyCodingKey(stringValue: "\(prefix)\(language)"))
        }
    }
}

private extension Equatable {
    static func localizedOptionalValue(base: String?, translations: [String: String], language: AppLanguage) -> String? {
        let raw = translations[language.rawValue]
        if let raw, !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return raw
        }
        return base
    }

    static func localizedValue(base: String, translations: [String: String], language: AppLanguage) -> String {
        localizedOptionalValue(base: base, translations: translations, language: language) ?? base
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
    public var chart: PluginChart?

    public init(
        id: UUID,
        pluginName: String,
        displayName: String,
        state: PluginSnapshotState = .idle,
        items: [UsageItem] = [],
        updatedAt: Date? = nil,
        badge: String? = nil,
        iconURL: String? = nil,
        chart: PluginChart? = nil
    ) {
        self.id = id
        self.pluginName = pluginName
        self.displayName = displayName
        self.state = state
        self.items = items
        self.updatedAt = updatedAt
        self.badge = badge
        self.iconURL = iconURL
        self.chart = chart
    }
}

public struct PluginCachedState: Codable, Equatable, Sendable {
    public var updatedAt: Date
    public var items: [UsageItem]
    public var badge: String?
    public var chart: PluginChart?

    public init(updatedAt: Date, items: [UsageItem], badge: String? = nil, chart: PluginChart? = nil) {
        self.updatedAt = updatedAt
        self.items = items
        self.badge = badge
        self.chart = chart
    }
}
