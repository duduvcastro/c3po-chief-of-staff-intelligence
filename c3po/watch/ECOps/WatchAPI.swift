import Foundation

struct WatchRegistration: Encodable {
    let deviceToken: String
    let categories: [String]

    enum CodingKeys: String, CodingKey {
        case categories
        case deviceToken = "device_token"
    }
}

enum WatchAPIError: Error { case missingConfiguration, invalidResponse }

final class WatchAPI {
    static let shared = WatchAPI()
    private init() {}

    private func request(path: String, method: String = "GET", body: Data? = nil) throws -> URLRequest {
        guard let base = SecureStore.get(account: "server"),
              let token = SecureStore.get(account: "token"),
              let url = URL(string: base)?.appending(path: path)
        else { throw WatchAPIError.missingConfiguration }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.httpBody = body
        request.timeoutInterval = 3
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        return request
    }

    func register(deviceToken: String, categories: [String]) async throws {
        let body = try JSONEncoder().encode(WatchRegistration(
            deviceToken: deviceToken, categories: categories
        ))
        let (_, response) = try await URLSession.shared.data(for: try request(
            path: "/api/v1/watch/register", method: "POST", body: body
        ))
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            throw WatchAPIError.invalidResponse
        }
    }

    func fetchMetric() async throws -> SessionMetric {
        let (data, response) = try await URLSession.shared.data(for: try request(
            path: "/api/v1/watch/complication"
        ))
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            throw WatchAPIError.invalidResponse
        }
        return try JSONDecoder().decode(SessionMetric.self, from: data)
    }
}
