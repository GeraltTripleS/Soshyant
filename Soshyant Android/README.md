# Soshyant Expert for Android

A native, text-only Android client for the existing Soshyant Expert server. The phone calls your computer's authenticated APIs over the same Wi-Fi. It does not run a language model or require a cloud API key on the phone.

## Install and connect

1. Keep **Soshyant Expert** running on the computer as usual.
2. Run **START-WIFI.bat** in this folder. Enter the computer's Wi-Fi IPv4 address when prompted. The prepared address and port are written to `dist/PHONE-CONNECTION.txt`.
3. Transfer **dist/SoshyantExpert-1.1.0.apk** and **dist/server-ca.crt** to the Android phone through a trusted channel, such as USB. Install the APK using Android's package installer. Android may ask you to allow installation from the file application you use.
4. Connect the phone to the same Wi-Fi. In the app, enter the HTTPS address shown by the gateway window, press **Import server CA certificate**, and select `server-ca.crt`. Compare the displayed CA fingerprint with the computer's connection file if needed.
5. Press **Test connection**, then sign in with an account created in the desktop application's Users page. Create the initial administrator on the computer first; there are no default credentials.

The gateway normally uses **port 8096**. It keeps the existing desktop address on port 8095 unchanged. Keep both the main server and gateway running; closing the gateway stops phone access. Windows Firewall may ask whether to allow the server process on your private network. This project does not change firewall rules automatically. Guest Wi-Fi/client isolation or a VPN can prevent devices on the same Wi-Fi from reaching each other.

The phone's address must point to the **computer**, not `localhost` or `127.0.0.1`. If DHCP changes the computer's address, rerun the gateway with the new address and update the phone's saved address. The existing private CA is retained, so the same imported CA can validate the renewed server certificate. No OS-wide trust root is installed by the setup script.

## Updating to 1.1

Close and restart the main server (`Soshyant Expert/START.bat`) and the Wi-Fi gateway (`START-WIFI.bat`) to load the new APIs. Install `dist/SoshyantExpert-1.1.0.apk` over your existing app; keep the same signing key and do not uninstall first. The server address, selected language and imported public CA are retained. Sign in again if asked.

Use **History** to search chat titles. Tap **⋮** next to a conversation (or beside the current chat title) to rename, share or delete it. Deletion requires confirmation, is restricted to your own chats, and is blocked during an active answer. It removes the messages, feedback and saved answer job copies from the server; existing backups and previously exported copies remain. Sharing opens Android's chooser so you decide where to send the text.

## Features

- HTTPS connection check and app-specific private CA import, with normal hostname validation.
- Sign in/out using server sessions and CSRF protection. Passwords and cookies are held in memory, not saved to phone storage. Reopening after process termination requires signing in again.
- New conversations, conversation history, request progress, cancellation, and resuming polling after a network interruption.
- Searchable chat titles, rename and confirmed permanent deletion.
- Copy answers, share answers or whole conversations, and save conversations as UTF-8 text files, including source references.
- Helpful/incorrect feedback with an optional note for the administrator.
- Message timestamps and native heading, bold, bullet and code formatting.
- Grounded answers with expandable cited passages, source titles, locations and document version numbers.
- English by default and Persian, including response-language selection and RTL layout.
- A notice when the server's selected LLM is an API provider. The computer then sends answer context to that provider under the administrator's configuration; using Wi-Fi alone does not make that mode offline.

Document uploads, model administration, API keys and user administration remain in the desktop web application. The phone has no microphone permission, speech-to-text, text-to-speech, analytics, WebView or third-party runtime libraries. Screenshots are blocked by the Android secure-window flag because documents can be confidential.

## Security and server boundary

The gateway in `../Soshyant Expert/expert/mobile_gateway.py` binds the chosen IPv4 interface and terminates TLS. It forwards only chat/login/history/status APIs to the existing **loopback** HTTP server; administrative routes are excluded. Cookies, account ownership, roles and CSRF are still checked by the real server. The gateway restricts Host and Origin, adds Secure to response cookies and rejects upstream redirects. TLS 1.2 or newer is required.

The CA and server private keys stay in `../Soshyant Expert/data/mobile-tls`. **Share only `server-ca.crt`, never `.key` files.** Protect that directory like other server credentials. No “trust all certificates” or permissive hostname verifier exists in the client.

## Build

The signed pilot APK is in `dist`. This is a development/pilot signing identity, not a Play Store release. Retain `.tools/pilot-signing.jks` for compatible local updates; use your own protected release signing process for external distribution.

- On this Windows computer, run **BUILD-APK.bat**. It uses the bundled server Python, the installed JDK and Google's SDK tools cached inside `.tools`. The first build downloads the pinned official Android platform/build tools and verifies their published package checksums. Subsequent builds can use that cache offline. No Gradle installation is needed for this route.
- Alternatively open this folder in Android Studio. The project uses AGP 8.13.2, Gradle 8.13 and compile/target SDK 35. Use a compatible embedded JDK. Minimum Android version: **8.0 / API 26**.
- `tools/test_client.py` tests the exact Java API transport in the APK against an isolated real HTTPS gateway and temporary test data. Its JSON dependency is used only on the host for tests, not included in the app.

## Verification and limits

The APK compiles and its v2/v3 signatures verify. Java integration tests passed HTTPS/private-CA trust, rejection of untrusted or wrongly named certificates, secure session cookies, CSRF-protected asks, job polling, citations, history, logout and gateway route restrictions. Gateway Host/Origin rejection was also tested. The user successfully tested version 1.0 on a real phone. The 1.1 changes are compiled and integration-tested here; their physical-phone UI acceptance test remains.

This version targets SDK 35. Per [Android's local network permission documentation](https://developer.android.com/privacy-and-security/local-network-permission), the new SDK-37 local-network permission is not requested for lower target SDKs. Updating to target SDK 37 needs that permission flow. See also [Android certificate trust](https://developer.android.com/privacy-and-security/security-config) and the [AGP compatibility table](https://developer.android.com/build/releases/agp-8-13-0-release-notes).

Long-running jobs may continue on the server if Android stops the app. Reopen the app and conversation history to view completed answers. An external API provider may still finish and bill a request already in progress after cancellation. No user capacity or response-time guarantee is claimed.
