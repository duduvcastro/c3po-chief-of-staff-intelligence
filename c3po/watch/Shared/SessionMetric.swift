import Foundation

struct SessionMetric: Codable {
    let sessionDate: String
    let wins: Int
    let decided: Int
    let winRatePercent: Double
    let display: String
    let generatedAt: String

    enum CodingKeys: String, CodingKey {
        case wins, decided, display
        case sessionDate = "session_date"
        case winRatePercent = "win_rate_percent"
        case generatedAt = "generated_at"
    }

    static let empty = SessionMetric(
        sessionDate: "", wins: 0, decided: 0, winRatePercent: 0,
        display: "0W/0 · 0,0%", generatedAt: ""
    )
}

enum SharedMetricStore {
    static let suite = "group.com.eduardocastro.ecops"
    static let key = "session_metric"

    static func save(_ metric: SessionMetric) {
        guard let data = try? JSONEncoder().encode(metric) else { return }
        UserDefaults(suiteName: suite)?.set(data, forKey: key)
    }

    static func load() -> SessionMetric {
        guard let data = UserDefaults(suiteName: suite)?.data(forKey: key),
              let metric = try? JSONDecoder().decode(SessionMetric.self, from: data)
        else { return .empty }
        return metric
    }
}
