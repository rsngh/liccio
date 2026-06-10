#!/usr/bin/env bash
# Set up the stateful CLI coding agents (Claude Code, Codex, Gemini CLI) the ACP metarouter
# can route over. Idempotent — safe to run on every session start.
#
# Scriptable (handled here): npm-install the Codex + Gemini CLIs, point node at the container's
# TLS-proxy CA bundle, set Gemini headless trust, and report availability/auth.
# NOT scriptable (need a browser, run once per fresh container): the Codex (ChatGPT) and Claude
# (subscription) OAuth logins — instructions are printed at the end.
set -u

CA=/etc/ssl/certs/ca-certificates.crt
[ -f "$CA" ] && export NODE_EXTRA_CA_CERTS="$CA"
export GEMINI_CLI_TRUST_WORKSPACE=true

log() { printf '[setup-cli-agents] %s\n' "$*"; }

# 1. Install the npm-distributed CLIs if missing (Claude Code is preinstalled in this image).
need=()
command -v codex  >/dev/null 2>&1 || need+=("@openai/codex")
command -v gemini >/dev/null 2>&1 || need+=("@google/gemini-cli")
if [ "${#need[@]}" -gt 0 ]; then
  log "installing: ${need[*]}"
  npm install -g "${need[@]}" >/dev/null 2>&1 || log "WARN: npm install failed (registry/network?) — install manually"
else
  log "codex + gemini already installed"
fi

# 2. Report availability + auth status (non-fatal).
for b in claude codex gemini; do
  if command -v "$b" >/dev/null 2>&1; then log "$b: $("$b" --version 2>/dev/null | head -1)"; else log "$b: MISSING"; fi
done
command -v codex >/dev/null 2>&1 && log "codex auth: $(codex login status 2>&1 | tail -1)"

# 3. Subscription logins (browser required — cannot run headless):
cat <<'EOF'
[setup-cli-agents] One-time subscription logins per fresh container (need a browser):
  Codex  (ChatGPT sub) : codex login --device-auth     # prints a URL + one-time code
  Claude (subscription): claude setup-token            # prints an OAuth URL; paste the returned code
  API-key fallbacks    : printenv OPENAI_API_KEY | codex login --with-api-key ; Claude reads ANTHROPIC_API_KEY
  Gemini               : uses GEMINI_API_KEY from the env — no login needed
NOTE: to bill the Claude *subscription* (not the API), Claude Code must run with ANTHROPIC_API_KEY
UNSET. The ACP harness does this automatically (src/acp/agents/vendor_native.py: vendor_env).
EOF
