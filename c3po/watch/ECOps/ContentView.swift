import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        NavigationStack {
            Form {
                Section("Connection") {
                    TextField("https://server", text: $model.server)
                        .textInputAutocapitalization(.never)
                    SecureField("Device token", text: $model.deviceCredential)
                    Button("Activate alerts") { Task { await model.activate() } }
                    Text(model.status).font(.caption2).foregroundStyle(.secondary)
                }
                Section("Categories") {
                    ForEach(AppModel.categoryKeys, id: \.self) { category in
                        Toggle(category.replacingOccurrences(of: "_", with: " "), isOn: Binding(
                            get: { model.categories.contains(category) },
                            set: { enabled in
                                if enabled { model.categories.insert(category) }
                                else { model.categories.remove(category) }
                            }
                        ))
                    }
                }
            }
            .navigationTitle("EC Ops")
            .task { await model.refreshMetric() }
        }
    }
}
