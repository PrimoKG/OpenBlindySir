# Trust the local HTTPS certificate

[Français](certificat-local.md). This guide covers private **LAN** hosting with Caddy.
Local HTTPS encrypts traffic, but phones do not initially trust its certificate
authority. That warning alone does not imply malware. Keep browser HTTPS protection
enabled and keep the LAN private.

## Export and verify

From the project folder, the host runs:

```powershell
./tools/docker-host.ps1 -Action certificate
```

On macOS/Linux: `./tools/docker-host.sh certificate`.
The launcher exports the public CA as `.local/docker/root.crt` and prints its
**file SHA-256**. For non-Docker PC hosting, use the public certificate reported
by the PC launcher; see [deployment](deployment.md). Preserve the original CA:
regeneration requires participants to install the replacement.

Receive the file through a known channel and verify its file hash with the host.
On Windows, `Get-FileHash -Algorithm SHA256 ./root.crt` computes the same value.
Phones without a verification tool can receive the file directly from the host
in person. Only install the host's verified certificate: trusting a CA can also
trust other sites signed with its private key. That key must remain private.

Share **only `root.crt`**. Never share `root.key`, `intermediate.key`, Caddy volumes,
`.env` files, passwords or state backups.

## Windows: Edge and Chrome

1. Open `root.crt` → **Install Certificate** → **Current User**.
2. Select **Place all certificates in the following store** →
   **Trusted Root Certification Authorities**.
3. Check the CA identity and approve only the file received from the host.
4. Restart the browser and open the exact LAN URL provided by the host.

Firefox may use its own store: Settings → Privacy & Security → Certificates →
View Certificates → Authorities → Import.

## iPhone / iPad

1. Open the received `root.crt`. Install its profile through Settings → General
   → VPN & Device Management (or **Profile Downloaded**).
2. Open Settings → General → About → **Certificate Trust Settings**.
3. Enable full trust for the local CA and reopen Safari.

Installing the profile alone may not enable SSL trust. See
[Apple's official instructions](https://support.apple.com/en-us/102390).
Managed devices may restrict certificate installation; their administrator controls it.

## Android

Search Settings for **Install a certificate**. Typical path: Security & privacy →
More security settings → Encryption & credentials → Install a certificate →
**CA certificate**. Select `root.crt`, confirm the CA, then reopen the browser.
Names and restrictions vary by manufacturer/version; do not select Wi-Fi or VPN
certificates. A user-certificate notification after installation is expected.

## Remove trust and troubleshoot

- After the event, remove the root from the Windows store, remove the iOS profile
  and trust setting, or delete the Android user CA.
- The URL must match `OBS_ADDRESS` and the certificate. Changing IP addresses may
  require configuration changes and a restart.
- Expiration, incorrect device clocks, a different CA or missing explicit trust can
  still cause alerts. Resolve the cause instead of routinely bypassing warnings.
- Browser audio requires HTTPS and a user gesture. Use **Test my audio** after sleep
  or an output-device change.

A controlled domain and publicly trusted certificate can avoid manual installation
in the future. This deployment keeps its existing LAN setup.
