// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "LeahCloudAgent",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "LeahCloudAgent", targets: ["LeahCloudAgent"])],
    targets: [.executableTarget(name: "LeahCloudAgent")]
)
