# Client Zero inbound SDR readiness — 2026-09-27

Target: Byram's Client Zero installation. This is a point-in-time read-only audit, not a deployment or acceptance receipt.

## Observed runtime

| Item | Observation | Evidence limit |
| --- | --- | --- |
| Team pod | `ig-ghl-relay.service` and `ai-flo-agent@sales-flo.service` active on `digitalflo-team-pod-01` | Process state only |
| GHL relay | Listening on port 8821, `RELAY_LIVE=true`, message type `IG` | No current matched inbound/outbound provider receipt |
| GHL credential | Read-only location lookup returned HTTP 200 using the relay's configured token | Confirms location API access, not Instagram connection or message delivery |
| Recent Instagram inbox | GHL search returned ten Instagram conversations; three latest messages were inbound and had no matching relay turns | Those three contacts had neither the relay enable tag nor a configured keyword, so the current gate intentionally skipped them |
| Relay source | `/opt/ig-ghl-relay/agent_service.py`, SHA-256 `3995e5e09c961445dcb37aee70a6292a24f72edafb95f43caca617330d7e70d0` | Diverges from this repo's improved template |
| Relay log | Last modified about 37 hours before audit | No current conversation proof |
| Social adapter | `social-sdr-zernio.service` inactive; its dedicated runtime env absent | No social cutover proof |
| Sales Flo model | Top profile contains `provider: zai` and a `gpt-4o-mini` fallback; relay names `grok-4.6` through a bridge | Subscription-only behavior and actual provider acceptance unproven |
| iMessage | `setter-flo-imessage.service` active; bridge timer recently completed successfully and reported zero new messages across one lead | A live inbound, reply receipt, and human view remain unverified |
| Calls and direct Meta | Retell and Meta keys absent from the GHL relay env; no matching voice service found on the team pod | Other hosts and provider accounts were not ruled out |

The historical Sales Flo desktop Tailscale address timed out during this audit. The team pod is the only Sales runtime reached and checked here.

The current GHL gate does not cover ordinary Instagram DMs unless a workflow adds the enable tag or the lead opens with a configured campaign keyword. Expanding coverage requires an explicit account and lead-eligibility policy so private or human-owned conversations stay out of automation.

## Channel acceptance receipts needed

| Channel | Required controlled proof before unattended replies |
| --- | --- |
| Instagram DM via GHL | Verify the exact Instagram account and GHL location; receive one real inbound message; match contact, channel, reply, provider message ID, readback, and human view. |
| Instagram comments | Verify the account, webhook subscription, keyword campaign, public/private reply permissions and consent; match comment ID to provider reply IDs and DM readback. |
| iMessage | Verify the dedicated Client Zero line and paired device; receive one real inbound event; send only with channel-specific consent and capture a provider receipt and human view. |
| Phone calls | Verify the inbound number and voice provider route; capture one controlled inbound call, transcript or event, handoff, CRM attribution, and a real booking receipt if booking is exercised. |

## Cutover sequence

1. Confirm the Client Zero identities, numbers, channel owners, and approved subscription model. Remove paid API fallback from the target runtime with a preserved config and tested rollback.
2. Compare the deployed GHL relay with this repo's template. Stage the receipt and channel fixes as a reviewed artifact; preserve its current state and avoid a second writer.
3. Run controlled account-specific tests in shadow mode. Check exact inbound/outbound IDs and provider readback before enabling one channel at a time.
4. Send the major-update handoff to My Flo, verify day-to-day behavior, and obtain Byram's acceptance. A client-fleet release is a later separate action.

No production service, provider setting, public account, or customer message was changed during this audit.
