# Fetching behind a TLS-inspecting proxy (corporate network)

On some networks a security appliance performs **TLS inspection**: it terminates
outbound HTTPS and re-signs the connection with an **organization root CA**. If that
root isn't in the CA bundle your tools use, fetches fail with:

```
SSL certificate problem: self-signed certificate in certificate chain
```

On the NREL / National Laboratory of the Rockies network this is **Netskope**
(`netskope.nrel.gov`), chaining to the **NREL Root CA**. That root is legitimate and is
already deployed to the macOS System keychain by MDM — the tools just aren't picking it
up. `hpc-oda datasets fetch` will surface the same error with a pointer to this page.

The fix is **not** to disable verification. Instead, build a CA bundle that includes
your org's root and point the standard `SSL_CERT_FILE` at it (curl, git, pip, and the
`hpc-oda` fetch backend all honor it).

## 1. Build a combined CA bundle

Combine `certifi`'s public roots with the org root from the keychain:

```bash
mkdir -p ~/.hpc_oda
{
  cat "$(python -c 'import certifi; print(certifi.where())')"
  security find-certificate -a -c "NREL Root CA" -p /Library/Keychains/System.keychain
} > ~/.hpc_oda/ca-bundle.pem
```

(Replace `"NREL Root CA"` with your org's root CN if different; `security find-certificate
-a -p /Library/Keychains/System.keychain | openssl ...` can list what's there.)

A refresh script is handy after `certifi` upgrades — e.g. `~/.hpc_oda/refresh-ca-bundle.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
out="$HOME/.hpc_oda/ca-bundle.pem"; mkdir -p "$HOME/.hpc_oda"
tmp="$(mktemp)"
security find-certificate -a -c "NREL Root CA" -p /Library/Keychains/System.keychain > "$tmp"
cat "$(python -c 'import certifi; print(certifi.where())')" "$tmp" > "$out"; rm -f "$tmp"
echo "Wrote $out ($(grep -c 'BEGIN CERT' "$out") certs)"
```

## 2. Point your tools at it

Add to your shell profile (`~/.zshrc`):

```bash
if [ -f "$HOME/.hpc_oda/ca-bundle.pem" ]; then
  export SSL_CERT_FILE="$HOME/.hpc_oda/ca-bundle.pem"      # OpenSSL (curl, python/urllib, the hpc-oda fetch backend)
  export CURL_CA_BUNDLE="$HOME/.hpc_oda/ca-bundle.pem"     # curl (explicit)
  export REQUESTS_CA_BUNDLE="$HOME/.hpc_oda/ca-bundle.pem" # pip / requests
  export GIT_SSL_CAINFO="$HOME/.hpc_oda/ca-bundle.pem"     # git / git-LFS over https
fi
```

For a single command without touching your profile:

```bash
SSL_CERT_FILE=~/.hpc_oda/ca-bundle.pem hpc-oda datasets fetch <descriptor>
```

## 3. Verify

```bash
curl -sS -I --max-time 20 https://data.openei.org/files/5860/eagle_data.parquet | head -1
SSL_CERT_FILE=~/.hpc_oda/ca-bundle.pem python -c \
  "import urllib.request as u; print(u.urlopen(u.Request('https://data.openei.org/files/5860/eagle_data.parquet', method='HEAD'), timeout=20).status)"
```

Both should print `200`. Once set, `hpc-oda datasets fetch`/`prepare` reach the
previously-blocked hosts (OEDI, the Parallel Workloads Archive, Atlas, data.nlr.gov, …).

## Notes

- **Zenodo works without this** because the proxy bypasses it, so its real public cert
  validates against `certifi` alone — which is why the first curated datasets are all
  Zenodo-hosted (see [`../datasets/curation-status.md`](../datasets/curation-status.md)).
- The bundle is a **superset** of `certifi`, so nothing that worked before breaks.
- `SSL_CERT_FILE` fixes verification, not routing. If your network also requires an
  explicit HTTP proxy, set `HTTPS_PROXY` as usual (urllib honors it).
