import Foundation

struct APIClient {
    let serverURL: URL

    private static var encoder: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .useDefaultKeys
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }

    private static var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .useDefaultKeys
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }

    func pair(code: String, deviceName: String) async throws -> PairResponse {
        try await request(
            path: "/api/v1/leah/agent/pair",
            body: PairRequest(code: code.uppercased(), name: deviceName, platform: "macOS"),
            token: nil
        )
    }

    func sync(_ payload: SyncRequest, token: String) async throws -> SyncResponse {
        try await request(path: "/api/v1/leah/agent/sync", body: payload, token: token)
    }

    private func request<Request: Encodable, Response: Decodable>(
        path: String,
        body: Request,
        token: String?
    ) async throws -> Response {
        let url = serverURL.appending(path: path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        request.httpBody = try Self.encoder.encode(body)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw LeahAgentError.server("Resposta inválida do C3PO.")
        }
        guard (200..<300).contains(http.statusCode) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw LeahAgentError.server(detail ?? "C3PO respondeu com erro \(http.statusCode).")
        }
        return try Self.decoder.decode(Response.self, from: data)
    }
}
