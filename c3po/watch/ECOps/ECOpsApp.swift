import SwiftUI
import WatchKit

final class ExtensionDelegate: NSObject, WKExtensionDelegate {
    func didRegisterForRemoteNotifications(withDeviceToken deviceToken: Data) {
        Task { await AppModel.shared.receivedDeviceToken(deviceToken) }
    }

    func didFailToRegisterForRemoteNotificationsWithError(_ error: Error) {
        Task { @MainActor in AppModel.shared.status = "APNs unavailable" }
    }

    func didReceiveRemoteNotification(
        _ userInfo: [AnyHashable: Any],
        fetchCompletionHandler completionHandler: @escaping (WKBackgroundFetchResult) -> Void
    ) {
        Task {
            await AppModel.shared.refreshMetric()
            completionHandler(.newData)
        }
    }
}

@main
struct ECOpsApp: App {
    @WKExtensionDelegateAdaptor(ExtensionDelegate.self) var delegate
    @StateObject private var model = AppModel.shared

    var body: some Scene {
        WindowGroup { ContentView().environmentObject(model) }
    }
}
