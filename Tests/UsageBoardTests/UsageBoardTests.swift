@preconcurrency import Foundation
#if canImport(XCTest)
import XCTest
@testable import UsageBoardCore

final class UsageBoardTests: XCTestCase {
    func testConfigurationDecodesDefaultsAndSaves() throws {
        let data = #"{"plugins":[{"name":"A","executablePath":"/bin/echo"}]}"#.data(using: .utf8)!
        let configuration = try UsageBoardJSON.decoder().decode(AppConfiguration.self, from: data)
        XCTAssertEqual(configuration.schemaVersion, 1)
        XCTAssertEqual(configuration.overviewDisplayMode, .tabs)
        XCTAssertEqual(configuration.plugins.first?.refreshIntervalSeconds, 300)

        let url = FileManager.default.temporaryDirectory.appendingPathComponent("usageboard-\(UUID().uuidString).json")
        let store = ConfigStore(fileURL: url)
        try store.save(configuration)
        let reloaded = try store.load()
        XCTAssertEqual(reloaded.plugins.first?.name, "A")
    }

    func testPluginsDirectoryIsNextToConfigurationFile() {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("usageboard-\(UUID().uuidString)", isDirectory: true)
        let store = ConfigStore(fileURL: directory.appendingPathComponent("config.json"))

        XCTAssertEqual(store.pluginsDirectoryURL(), directory.appendingPathComponent("plugins", isDirectory: true))
    }

    func testBundledPluginInstallerCreatesSymlinks() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("usageboard-\(UUID().uuidString)", isDirectory: true)
        let source = root.appendingPathComponent("source", isDirectory: true)
        let destination = root.appendingPathComponent("plugins", isDirectory: true)
        try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)

        let bundled = source.appendingPathComponent("glm-usage-plugin.py")
        let existing = destination.appendingPathComponent("glm-usage-plugin.py")
        let newPlugin = source.appendingPathComponent("tavily-usage-plugin.py")
        try "bundled".data(using: .utf8)!.write(to: bundled)
        try "user-edited".data(using: .utf8)!.write(to: existing)
        try "new".data(using: .utf8)!.write(to: newPlugin)

        let installed = try BundledPluginInstaller(
            sourceDirectoryURL: source,
            destinationDirectoryURL: destination
        )
        .installIfNeeded()

        XCTAssertEqual(installed.map(\.lastPathComponent), ["glm-usage-plugin.py", "tavily-usage-plugin.py"])
        let linkTarget = try FileManager.default.destinationOfSymbolicLink(atPath: existing.path)
        XCTAssertEqual(URL(fileURLWithPath: linkTarget).resolvingSymlinksInPath(), bundled.resolvingSymlinksInPath())
        XCTAssertEqual(try String(contentsOf: destination.appendingPathComponent("tavily-usage-plugin.py")), "new")
    }

    func testPluginOutputDecodesAndFormatsUsage() throws {
        let json = """
        {
          "schemaVersion": 1,
          "updatedAt": "2026-04-29T00:00:00Z",
          "items": [
            {
              "id": "requests",
              "name": "Requests",
              "used": 1200,
              "limit": 1500,
              "displayStyle": "percent",
              "resetAt": "2026-04-29T00:05:00Z",
              "status": "normal"
            }
          ]
        }
        """.data(using: .utf8)!

        let output = try UsageBoardJSON.decoder().decode(PluginOutput.self, from: json)
        let item = try XCTUnwrap(output.items.first)
        XCTAssertEqual(item.progress, 0.8)
        XCTAssertEqual(item.displayValue(), "80%")
        let now = ISO8601DateFormatter().date(from: "2026-04-29T00:00:00Z")!
        let text = item.resetText(now: now)
        XCTAssertFalse(text.isEmpty)
        XCTAssertNotEqual(text, "--")
    }

    func testProgressHandlesBoundsAndRatio() {
        let overLimit = UsageItem(id: "a", name: "A", used: 2, limit: 1, displayStyle: .percent)
        let noLimit = UsageItem(id: "b", name: "B", used: 2, limit: 0, displayStyle: .percent)
        let ratio = UsageItem(id: "c", name: "C", used: 2, limit: 1500, displayStyle: .ratio)

        XCTAssertEqual(overLimit.progress, 1)
        XCTAssertEqual(overLimit.displayValue(), "100%")
        XCTAssertEqual(noLimit.progress, 0)
        XCTAssertEqual(noLimit.displayValue(), "0%")
        XCTAssertEqual(ratio.displayValue(), "2 / 1500")
        XCTAssertEqual(ratio.resetText(), "--")
    }

    func testResetTextShowsStaticDateTime() {
        let now = ISO8601DateFormatter().date(from: "2026-04-29T00:00:00Z")!
        let resetAt = ISO8601DateFormatter().date(from: "2026-04-30T01:02:03Z")!
        let item = UsageItem(id: "a", name: "A", used: 1, limit: 2, displayStyle: .ratio, resetAt: resetAt)

        let text = item.resetText(now: now)
        XCTAssertFalse(text.isEmpty)
        XCTAssertNotEqual(text, "--")
        XCTAssertEqual(item.resetText(now: resetAt), "--")
    }

    func testPluginMetadataParserReadsCommentBlock() throws {
        let script = """
        #!/usr/bin/env python3
        # UsageBoardPlugin:
        # {
        #   "schemaVersion": 1,
        #   "name": "GLM",
        #   "parameters": [
        #     {"name": "API_KEY", "label": "Api Key", "type": "string", "required": true},
        #     {
        #       "name": "PROVIDER",
        #       "label": "Provider",
        #       "type": "choice",
        #       "defaultValue": "GLM",
        #       "options": [
        #         {"label": "GLM", "value": "GLM"},
        #         {"label": "ZAI", "value": "ZAI"}
        #       ]
        #     }
        #   ]
        # }
        # /UsageBoardPlugin
        print("ok")
        """

        let metadata = try XCTUnwrap(PluginMetadataParser.parse(text: script))
        XCTAssertEqual(metadata.name, "GLM")
        XCTAssertEqual(metadata.parameters.first?.name, "API_KEY")
        XCTAssertEqual(metadata.parameters.first?.type, .string)
        XCTAssertEqual(metadata.parameters.first?.required, true)
        XCTAssertEqual(metadata.parameters.last?.type, .choice)
        XCTAssertEqual(metadata.parameters.last?.options.map(\.value), ["GLM", "ZAI"])
    }

    func testDuplicatePluginNamesGetNumbered() {
        let first = PluginConfiguration(name: "OpenAI", executablePath: "/bin/echo")
        let second = PluginConfiguration(name: "OpenAI", executablePath: "/bin/echo")
        let third = PluginConfiguration(name: "Other", executablePath: "/bin/echo")

        let names = PluginDisplayNames.make(for: [first, second, third])
        XCTAssertEqual(names[first.id], "OpenAI")
        XCTAssertEqual(names[second.id], "OpenAI 2")
        XCTAssertEqual(names[third.id], "Other")
    }

    func testPluginParameterValuesBecomeArguments() {
        let executor = PluginExecutor()
        let configuration = PluginConfiguration(
            name: "GLM",
            executablePath: "/tmp/glm.py",
            parameterValues: [
                "API_KEY": "secret",
                "PROVIDER": "ZAI",
                "EMPTY": ""
            ]
        )

        XCTAssertEqual(
            executor.pluginParameterArguments(configuration: configuration),
            ["--usageboard-param", "API_KEY=secret", "--usageboard-param", "PROVIDER=ZAI"]
        )
    }

    func testUpdateVersionComparison() {
        XCTAssertTrue(UpdateChecker.isVersion("1.2.0", newerThan: "1.1.9"))
        XCTAssertTrue(UpdateChecker.isVersion("1.2.1", newerThan: "1.2.0"))
        XCTAssertFalse(UpdateChecker.isVersion("1.2.0", newerThan: "1.2.0"))
        XCTAssertFalse(UpdateChecker.isVersion("1.1.9", newerThan: "1.2.0"))
    }

    func testPluginExecutorReportsInvalidJSON() {
        let configuration = PluginConfiguration(
            name: "Bad",
            executablePath: "/bin/echo"
        )

        let snapshot = PluginExecutor(timeoutSeconds: 2).run(configuration: configuration, displayName: "Bad")
        guard case .failed(let message) = snapshot.state else {
            XCTFail("Expected failed snapshot")
            return
        }
        XCTAssertTrue(message.contains("JSON 解析失败"))
    }
}
#else
struct UsageBoardTestsPlaceholder {}
#endif
