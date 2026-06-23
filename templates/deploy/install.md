# Deploy — systemd units + install

All on the client VM. Replace `sdr-flo` / paths / `<client>` as needed. Relay + reliability + intelligence are separate units so each restarts independently.

## env (`/opt/sdr-flo/.env`, root 0600)
See [env.example](env.example). Never commit real secrets.

## Relay service
`/etc/systemd/system/sdr-flo-relay.service`
```ini
[Unit]
Description=SDR Flo relay (channel capture -> brain -> reply)
After=network-online.target
[Service]
WorkingDirectory=/opt/sdr-flo/agent
EnvironmentFile=/opt/sdr-flo/.env
ExecStart=/usr/bin/python3 /opt/sdr-flo/agent/agent_service.py
Restart=always
[Install]
WantedBy=multi-user.target
```

## Intelligence timers (daily + weekly)
`/etc/systemd/system/sdr-flo-intelligence-daily.service`
```ini
[Unit]
Description=SDR Flo intelligence - daily scoreboard + soft optimize
After=network-online.target
[Service]
Type=oneshot
WorkingDirectory=/opt/sdr-flo/intelligence
EnvironmentFile=/opt/sdr-flo/intelligence/intel.env
ExecStart=/usr/bin/python3 /opt/sdr-flo/intelligence/intelligence.py daily
```
`/etc/systemd/system/sdr-flo-intelligence-daily.timer`
```ini
[Unit]
Description=SDR Flo intelligence daily at midnight
[Timer]
OnCalendar=*-*-* 00:00:00
Persistent=true
[Install]
WantedBy=timers.target
```
Weekly = same with `intelligence.py weekly` and `OnCalendar=Sun *-*-* 00:30:00`.

`intel.env`: `INTEL_DRY=1` (shadow / report-only) — flip to `0` for live self-optimization.

## Reliability timers (optional, from the Setter Flo core)
convo-sync (10m), follow-up (15m), reminders (30m), health (20m) — add as the client needs them.

## Bring it up
```bash
systemctl daemon-reload
systemctl enable --now sdr-flo-relay.service
systemctl enable --now sdr-flo-intelligence-daily.timer sdr-flo-intelligence-weekly.timer
systemctl list-timers 'sdr-flo-*' --no-pager
```

## Go-live order
1. `RELAY_LIVE=false` → dry-run the gauntlet (compose + log, no sends).
2. Point the channel webhook (GHL workflow, etc.) at `http://<relay>:<port>/inbound`.
3. `RELAY_LIVE=true`, restart relay, watch the first real convos on ONE channel.
4. Leave intelligence in shadow (`INTEL_DRY=1`) for the first cycle; review the report; flip to `0`.
