@preconcurrency import Foundation

public struct PluginExecutor: Sendable {
    public var timeoutSeconds: TimeInterval

    public init(timeoutSeconds: TimeInterval = 15) {
        self.timeoutSeconds = timeoutSeconds
    }

    public func run(configuration: PluginConfiguration, displayName: String, language: AppLanguage = .zhHans) -> PluginSnapshot {
        guard configuration.enabled else {
            return PluginSnapshot(id: configuration.id, pluginName: configuration.name, displayName: displayName, iconURL: configuration.metadata?.icon)
        }

        guard !configuration.executablePath.isEmpty else {
            return failed(configuration: configuration, displayName: displayName, message: text(.missingExecutablePath, language: language))
        }

        let process = Process()
        let executableURL = URL(fileURLWithPath: configuration.executablePath)
        let pluginArguments = pluginParameterArguments(configuration: configuration, language: language)
        if executableURL.pathExtension.lowercased() == "py" {
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = ["python3", configuration.executablePath] + pluginArguments
        } else {
            process.executableURL = executableURL
            process.arguments = pluginArguments
        }
        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        do {
            try process.run()
        } catch {
            return failed(configuration: configuration, displayName: displayName, message: error.localizedDescription)
        }

        let finished = wait(process: process, timeoutSeconds: timeoutSeconds)
        if !finished {
            process.terminate()
            return failed(configuration: configuration, displayName: displayName, message: text(.timeout, language: language))
        }

        let outputData = stdout.fileHandleForReading.readDataToEndOfFile()
        let errorData = stderr.fileHandleForReading.readDataToEndOfFile()
        if process.terminationStatus != 0 {
            let stderrText = String(data: errorData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
            return failed(configuration: configuration, displayName: displayName, message: stderrText?.isEmpty == false ? stderrText! : text(.exitCode(process.terminationStatus), language: language))
        }

        do {
            let pluginOutput = try UsageBoardJSON.decoder().decode(PluginOutput.self, from: outputData)
            return PluginSnapshot(
                id: configuration.id,
                pluginName: configuration.name,
                displayName: displayName,
                state: .ready,
                items: pluginOutput.items,
                updatedAt: pluginOutput.updatedAt,
                badge: pluginOutput.badge,
                iconURL: configuration.metadata?.icon,
                chart: pluginOutput.chart
            )
        } catch {
            return failed(configuration: configuration, displayName: displayName, message: "\(text(.jsonParseFailed, language: language))\(error.localizedDescription)")
        }
    }

    public func pluginParameterArguments(configuration: PluginConfiguration, language: AppLanguage? = nil) -> [String] {
        var values = configuration.parameterValues
        if let language {
            values["USAGEBOARD_LANGUAGE"] = language.rawValue
        }

        return values
            .filter { !$0.value.isEmpty }
            .sorted { $0.key < $1.key }
            .flatMap { ["--usageboard-param", "\($0.key)=\($0.value)"] }
    }

    private func wait(process: Process, timeoutSeconds: TimeInterval) -> Bool {
        let deadline = Date().addingTimeInterval(timeoutSeconds)
        while process.isRunning {
            if Date() >= deadline { return false }
            Thread.sleep(forTimeInterval: 0.05)
        }
        return true
    }

    private func failed(configuration: PluginConfiguration, displayName: String, message: String) -> PluginSnapshot {
        PluginSnapshot(
            id: configuration.id,
            pluginName: configuration.name,
            displayName: displayName,
            state: .failed(message),
            items: [],
            updatedAt: Date(),
            iconURL: configuration.metadata?.icon
        )
    }

    private enum Message {
        case missingExecutablePath
        case timeout
        case exitCode(Int32)
        case jsonParseFailed
    }

    private func text(_ message: Message, language: AppLanguage) -> String {
        switch (message, language) {
        case (.missingExecutablePath, .en):
            return "Executable path is not configured"
        case (.missingExecutablePath, .zhHans):
            return "未配置可执行路径"
        case (.timeout, .en):
            return "Plugin execution timed out"
        case (.timeout, .zhHans):
            return "插件执行超时"
        case (.exitCode(let code), .en):
            return "Plugin exited with code \(code)"
        case (.exitCode(let code), .zhHans):
            return "插件退出码 \(code)"
        case (.jsonParseFailed, .en):
            return "JSON parsing failed: "
        case (.jsonParseFailed, .zhHans):
            return "JSON 解析失败："
        }
    }
}
