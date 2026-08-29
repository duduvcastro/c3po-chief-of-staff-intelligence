# EC Ops watchOS

The generated Xcode project is intentionally not committed. Install Xcode and
XcodeGen, then run `xcodegen generate` in this directory. Signing and the APNs
capability are configured locally with the approved Apple Developer account.

The first launch accepts the production HTTPS URL and the one-time device
credential issued by the owner-only API. Both values remain local; the device
credential is stored in the watchOS Keychain.
