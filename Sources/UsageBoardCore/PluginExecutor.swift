@preconcurrency import Foundation

public struct PluginExecutor: Sendable {
    public var timeoutSeconds: TimeInterval

    public init(timeoutSeconds: TimeInterval = 15) {
        self.timeoutSeconds = timeoutSeconds
    }

    public func run(configuration: PluginConfiguration, displayName: String) -> PluginSnapshot {
        guard configuration.enabled else {
            return PluginSnapshot(id: configuration.id, pluginName: configuration.name, displayName: displayName, iconURL: configuration.metadata?.icon)
        }

        guard !configuration.executablePath.isEmpty else {
            return failed(configuration: configuration, displayName: displayName, message: "未配置可执行路径")
        }

        let process = Process()
        let executableURL = URL(fileURLWithPath: configuration.executablePath)
        let pluginArguments = pluginParameterArguments(configuration: configuration)
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
            return failed(configuration: configuration, displayName: displayName, message: "插件执行超时")
        }

        let outputData = stdout.fileHandleForReading.readDataToEndOfFile()
        let errorData = stderr.fileHandleForReading.readDataToEndOfFile()
        if process.terminationStatus != 0 {
            let stderrText = String(data: errorData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
            return failed(configuration: configuration, displayName: displayName, message: stderrText?.isEmpty == false ? stderrText! : "插件退出码 \(process.terminationStatus)")
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
                iconURL: configuration.metadata?.icon
            )
        } catch {
            return failed(configuration: configuration, displayName: displayName, message: "JSON 解析失败：\(error.localizedDescription)")
        }
    }

    public func pluginParameterArguments(configuration: PluginConfiguration) -> [String] {
        configuration.parameterValues
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
}
