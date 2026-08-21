import SwiftUI

@main
struct LeahCloudAgentApp: App {
    @StateObject private var model = AgentModel()

    var body: some Scene {
        WindowGroup("Leah Cloud") {
            ContentView(model: model)
                .frame(minWidth: 480, minHeight: 430)
        }
    }
}

struct ContentView: View {
    @ObservedObject var model: AgentModel

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            HStack(spacing: 14) {
                Image(nsImage: NSImage(named: "AppIcon") ?? NSImage())
                    .resizable().scaledToFit().frame(width: 58, height: 58)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Leah Cloud Agent").font(.title2.bold())
                    Text("Calendário e Lembretes do seu Mac").foregroundStyle(.secondary)
                }
            }

            if model.isPaired {
                GroupBox("Conexão") {
                    VStack(alignment: .leading, spacing: 12) {
                        permissionRow("Calendário", granted: model.calendarAuthorized)
                        permissionRow("Lembretes", granted: model.remindersAuthorized)
                        Divider()
                        LabeledContent("Estado", value: model.status)
                        if let date = model.lastSync {
                            LabeledContent("Última sincronização", value: date.formatted(date: .omitted, time: .standard))
                        }
                    }.padding(8)
                }
                HStack {
                    Button("Autorizar novamente") { model.authorizeAgain() }
                    Button("Sincronizar agora") { Task { await model.syncNow() } }
                        .disabled(model.isWorking)
                    Spacer()
                    Button("Desconectar", role: .destructive) { model.disconnect() }
                }
            } else {
                GroupBox("Conectar este Mac") {
                    VStack(alignment: .leading, spacing: 12) {
                        TextField("Endereço do C3PO", text: $model.server)
                        TextField("Código de 8 caracteres", text: $model.pairingCode)
                            .textFieldStyle(.roundedBorder)
                        Text("O código é gerado dentro da aba Leah Cloud e expira em 10 minutos.")
                            .font(.caption).foregroundStyle(.secondary)
                    }.padding(8)
                }
                Button("Autorizar e conectar") { model.connect() }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.pairingCode.replacingOccurrences(of: " ", with: "").count != 8 || model.isWorking)
                Text(model.status).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(26)
    }

    private func permissionRow(_ label: String, granted: Bool) -> some View {
        HStack {
            Image(systemName: granted ? "checkmark.circle.fill" : "exclamationmark.square.fill")
                .foregroundStyle(granted ? .green : .orange)
            Text(label)
            Spacer()
            Text(granted ? "Autorizado" : "Pendente").foregroundStyle(.secondary)
        }
    }
}
