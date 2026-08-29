import Foundation
import UserNotifications
import WatchKit
import WidgetKit

@MainActor
final class AppModel: ObservableObject {
    static let shared = AppModel()
    static let categoryKeys = [
        "kill_criterion", "job_failure", "governance_critical", "mesa_reading",
        "disk_threshold", "security_login", "sell_win", "hourly_win_rate",
    ]

    @Published var server = ""
    @Published var deviceCredential = ""
    @Published var categories = Set(categoryKeys)
    @Published var status = "Not configured"
    private var apnsToken: String?

    private init() {
        server = SecureStore.get(account: "server") ?? ""
        deviceCredential = SecureStore.get(account: "token") ?? ""
    }

    func activate() async {
        guard let url = URL(string: server), url.scheme == "https",
              !deviceCredential.isEmpty else {
            status = "Enter server and device token"
            return
        }
        SecureStore.set(server.trimmingCharacters(in: CharacterSet(charactersIn: "/")), account: "server")
        SecureStore.set(deviceCredential, account: "token")
        do {
            let granted = try await UNUserNotificationCenter.current().requestAuthorization(
                options: [.alert, .sound]
            )
            guard granted else { status = "Notifications denied"; return }
            WKExtension.shared().registerForRemoteNotifications()
            status = "Waiting for APNs"
            if let apnsToken { try await register(apnsToken) }
        } catch {
            status = "Activation failed"
        }
    }

    func receivedDeviceToken(_ token: Data) async {
        let value = token.map { String(format: "%02x", $0) }.joined()
        apnsToken = value
        do { try await register(value) } catch { status = "Registration failed" }
    }

    func refreshMetric() async {
        guard let metric = try? await WatchAPI.shared.fetchMetric() else { return }
        SharedMetricStore.save(metric)
        WidgetCenter.shared.reloadAllTimelines()
    }

    private func register(_ token: String) async throws {
        try await WatchAPI.shared.register(deviceToken: token, categories: categories.sorted())
        status = "Active"
        await refreshMetric()
    }
}
