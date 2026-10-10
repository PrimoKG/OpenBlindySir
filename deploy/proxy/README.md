# Pinned Caddy security build

The `proxy` Docker target keeps Caddy **2.11.7** and its standard modules, built
with **Go 1.26.9** and **golang.org/x/net 0.60.0**. These versions address the Go
advisories found by the local scan on 10 October 2026, before the official Caddy
image incorporated them. The binary identifies as `v2.11.7-openblindysir.1`.

`go.mod` and `go.sum` pin the resolved module graph. The build uses
`-mod=readonly`, checksum verification and a digest-pinned compiler image.
The runtime retains the existing Caddy image configuration and local CA volumes;
the Go compiler and module cache are not copied into it. CGO is disabled.

For the next proxy update, review the upstream Caddy release and Go advisories,
update the pinned module graph/compiler together, build the `proxy` target, scan
that exact image locally, validate both Caddyfiles, and exercise verified HTTPS
and WSS with synthetic clients before replacing the runtime. Do not remove the
local CA volumes or bypass client certificate validation during an update.

The Windows build-context allowlist and `.dockerignore` include only these two
lockfiles from this directory. Installation from an offline pack needs no Go
toolchain on the host.
