# 07 — Deployment

Per-client, single-tenant. One AI Flo engine per VM, an isolated profile per agent, systemd for lifecycle, Codex or client Max for reasoning (**zero API credits**).

## The engine
AI Flo v3 = DigitalFlo's fork of Nous Hermes Agent (MIT), client-facing name **"AI Flo" / "the v3 agent"** (never "Hermes").

> **FLO V4 (2026-07-01):** the engine fork is now the **v4 line** (Hermes 0.18 base) and ships `flo-core/` — the versioned framework layer. New installs compose the profile home with `flo-core/bin/flo-compose` (CORE + `sdr` profile + niche + client.yaml) instead of hand-writing SOUL/config/skills; this repo's templates (relay, channels, intelligence, watchdog, deploy) remain the canonical deterministic layer the `sdr` profile installs. Runbook: engine repo `flo-core/docs/ONBOARDING.md`. Installed at `/opt/ai-flo-v3` (path may be versioned, e.g. `/opt/<client>-v3-vX.Y.Z`). Gateway: `python -m hermes_cli.main gateway run --replace`. Customize via `skills/`, `plugins/`, `SOUL.md`, `config.yaml`, `.env` — never fork engine source unless required (every engine patch is a rebase cost). See the engine repo's `README.DIGITALFLO.md`.

## Profiles & isolation
Each agent gets a separate **`HERMES_HOME`** with its own `SOUL.md`, `skills/`, `config.yaml`, `.env`, sessions, state. Multiple agents share one engine binary but never share memory — "separate profile so conversations don't mix" is a hard-won rule. A **new setter** = a new profile home + its own service (and, for non-native channels, its own relay on its own port). Adding one:
1. `mkdir -p /opt/<client>/profiles/<agent>/` and write `SOUL.md`, `skills/`, `config.yaml`, `.env`.
2. Add a systemd service with `Environment=HERMES_HOME=/opt/<client>/profiles/<agent>` (or run the relay against that home).
3. Enable + start; verify the live agent is untouched.

## Channel-native vs relay
The gateway binds **Telegram / Discord / Slack / Signal** natively. **IG / FB / TikTok / SMS / iMessage / email / voice** come through the **relay** (or Photon/Retell adapters). Don't try to make a gateway speak a non-native channel — use the relay. See [02-channels.md](02-channels.md) and [../templates/relay/](../templates/relay/).

## VMs (Proxmox)
Per-client VM (or a pod on a shared host). Access via the PVE host: `ssh root@<pve-host>` then `qm guest exec <vmid> -- bash -c '<cmd>'`.
> **Quoting gotcha:** parens `(` `)` in `echo` break `bash -c`. For anything non-trivial, write a script, `base64` it, and pipe: `echo <B64> | base64 -d | bash`.
Snapshot before major changes (`qm snapshot`), roll back with `qm rollback`.

## systemd lifecycle (not pm2, not manual)
- The agent gateway / relay: `Restart=always`.
- Timers for the reliability engines: conversation-sync (10m), follow-up (15m), reminders (30m), health (20m).
- Timers for intelligence: daily 00:00 + weekly Sun 00:30, `Persistent=true`.
Templates in [../templates/deploy/](../templates/deploy/).

## Auth doctrine — zero API credits
- **Codex** (`provider: openai-codex`, `model: gpt-5.5`, ChatGPT backend) via device OAuth — no API key, no credits. `fallback_providers: []`. Config an auxiliary Codex client so a fallback provider never silently reappears. A model-guard timer can re-pin the config if it drifts.
- **OR the client's own Claude Max** via a local CLI bridge (e.g. `claude-cli-openai-bridge` on `:8787`) reading the client's OAuth — the client's subscription pays, the VM gets $0 API cost.
- **Never** put `ANTHROPIC_API_KEY` (or any metered key) on a client VM.
- **One seat per client.** No shared Max/Codex across clients.

## Per-client install checklist
1. VM (clone template) + Tailscale + engine at `/opt/...`.
2. Profile home + `SOUL.md` (offer, persona, **objective**) + `skills/appointment-setter` + Codex/Max auth.
3. Supabase project (the spine) + creds in `.env` (0600).
4. Channels the client uses: GHL location (IG/FB/TikTok/SMS), Photon line (iMessage), Twilio (SMS fallback), Gmail (email), Retell agent+number (voice), Google Calendar (booking).
5. Relay service + the channel webhooks → `:PORT/inbound`.
6. Reliability timers + intelligence layer (shadow mode).
7. Dry-run the gauntlet; flip live one channel at a time; keep the prior system as warm rollback.

## Secrets
Only in the profile `.env` (root-owned, 0600), Vercel/host env, and the vault credentials file. Never in git. This repo ships placeholders/env names only.
