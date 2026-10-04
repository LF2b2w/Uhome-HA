# Uhome (U-Tec)

A Home Assistant custom integration for U-tec (Ultraloq) locks, lights, switches, and plugs, built on U-tec's OpenAPI.

**Community-maintained. Not made, endorsed, or supported by U-tec or Xthings. Uses each user's own OpenAPI credentials.** Please send integration problems to this repository's [issues](https://github.com/LF2b2w/Uhome-HA/issues), not to U-tec support.

| | |
| --- | --- |
| Devices | Locks, lights, switches, Wi-Fi smart plugs |
| Talks to | U-tec cloud API, plus an optional webhook or Nabu Casa cloudhook |
| Install | [HACS](#install) custom integration |
| Credentials | Xthings Home app, My Account → OpenAPI |

## Community responsibility

This section is the why behind some of the defaults. It's short, and it matters.

### One API, shared by everyone

Every install of this integration talks to the same U-tec cloud API. Your polls, my polls, and everyone else's land on the same servers, next to U-tec's own app traffic. Each of us brings our own credentials, but the capacity behind them is shared.

### We're in a good spot, and we'd like to keep it

Right now U-tec offers a self-service OpenAPI: you switch it on in the app, you get your own credentials, there's no paid tier, and there are no published rate limits. That's generous, and it rests on trust that third-party clients will behave reasonably. A lot of us have real money in U-tec locks, lights, switches, and plugs, and Home Assistant is how we use them. That access is worth protecting.

Staying responsible is how we keep it that way. If that trust gets broken, on purpose or by accident, the reasonable response from any vendor is limits or revoked access. Other smart-home communities have been through exactly that:

- **Tado** (2025) added daily API caps after "a small fraction of very frequent API users" drove a disproportionate share of its server costs ([home-assistant/core#151223](https://github.com/home-assistant/core/issues/151223)).
- **Haier** (2024) sent the hOn integration developer a takedown notice over 10-second polling. It was resolved by moving to 60 seconds ([hOn FAQ](https://github.com/Andre0512/hon/blob/main/takedown_faq.md)).
- **Chamberlain myQ** (2023) blocked third-party access entirely, and Home Assistant removed the integration ([HA blog](https://www.home-assistant.io/blog/2023/11/06/removal-of-myq-integration/)).

None of that was U-tec, and we'd like it to stay that way.

### Fair use

Most shared services work on fair use: what one customer uses should stay in proportion to what was provisioned for them. U-tec hasn't published a number, so we hold ourselves to a sensible one. A lock, a light, or a plug doesn't need to be asked how it's doing every second, all day.

There's good precedent for communities doing this themselves. Elinor Ostrom won the 2009 Nobel Prize in Economics for showing, in the Academy's words, "how common property can be successfully managed by user associations" ([Nobel press release](https://www.nobelprize.org/prizes/economic-sciences/2009/press-release/)). Shared resources last when the people using them agree on sensible rules and keep to them, without anyone having to impose them from above. A polling floor and some light accounting are our version of that.

### Sensible polling

- The polling interval is 10 to 3600 seconds, default 20. One poll is one bulk request for all your devices.
- If push works for you, 300 to 600 seconds is plenty.
- If you rely on polling, the 20-second default (or 30) with Adaptive Aggressive on is a good balance, and lock commands still confirm in seconds.
- For scale: 20 seconds is about 4,300 requests a day per install, 30 seconds about 2,900, and the 10-second floor about 8,600. A 1-second interval would be 86,400.

### Fast feedback without the heavy load

You don't need a fast interval to get fast feedback:

- **Adaptive Aggressive** polls only the lock you just operated, quickly at first, then backing off, and stops as soon as the state is confirmed. That's at most 9 polls per command.
- **Passage mode** locks ignore lock commands. If the last reported mode is Passage, Home Assistant first asks U-tec for that one lock's current mode. Only if the fresh answer confirms Passage is the lock command skipped (logged as a warning and counted under API commands skipped). If the answer says otherwise, or the check fails or times out, the command is sent as usual. When in doubt, send the command.
- **Debug Polling Mode** gives you 1-second polling for 2 minutes when you're testing, then turns itself off. A session is about 120 requests. Leaving 1 second on all day would be 86,400.

### See your own footprint

The **U-Tec Integration** device has diagnostic sensors showing what your install asks of the API: total requests, requests in the last hour, requests per device per hour, queries, commands, discoveries, failures, and pushes. If a number looks high, it probably is. Details are in [API usage sensors](#api-usage-sensors).

## What you get

- Lock, unlock, and passage-mode state
- Door state, when the lock has a door sensor
- Battery level and battery status
- On and off for switches, plugs, and bulbs that expose the switch capability
- SwitchLevel for dimming until U-tec ships a real light capability
- Adaptive Aggressive confirmation for locks when a push never arrives
- Debug Polling Mode for short, self-ending 1-second test sessions
- API usage sensors on the U-Tec Integration device

The U-tec API does not currently expose Wi-Fi bridge modules or Air Portal devices.

## Adaptive Aggressive

U-tec can register a webhook or a Nabu Casa cloudhook. Those pushes often never arrive, so Home Assistant otherwise learns a lock or unlock only on the next idle poll.

Adaptive Aggressive is off until you turn it on. After a lock or unlock from Home Assistant it polls only that lock:

1. The command is sent as usual.
2. A confirmation burst polls on the `ADAPTIVE_AGGRESSIVE_DELAYS` schedule: 1s, 1s, 1s, 1s, 2s, 3s, 5s, 8s, 13s (at most 9 polls, about 35 seconds).
3. The burst stops when the API reports the commanded state, a push carrying `st.lock` matches it, the schedule runs out, the next delay would be at least the idle poll interval, or polls keep failing (two errors in a row, or the regular poll failure threshold).
4. Lights, switches, and every other device stay on the idle interval. Passage mode is skipped, because the lock ignores the command.

A confirmed burst is remembered for one idle interval, capped at `CONFIRMATION_WINDOW_CAP` (60 seconds). A later poll or push that contradicts that confirmation is not applied. The burst is re-armed and the fresh poll wins. A new lock or unlock clears the confirmation, so the new command is not treated as a contradiction. A battery or door push cannot confirm a burst.

When a burst poll is what catches the change (not a push or a regular poll), it is logged at WARNING with the device name, the new state, the seconds since the command, and how many burst polls it took:

```
Adaptive Aggressive caught Front Door (abc123) changing to locked 4.0s after the command, on burst poll 4 of 9 (intervals: 1+1+1+1s)
```

If the burst gives up, the integration logs a warning and fires `u_tec_lock_command_failed` with `device_id`, `expected_locked`, `attempts`, and `reason`. Burst polls use their own signal, so optimistic lock updates keep their grace period instead of flickering on the first poll.

### Recommended lock settings

- Polling interval: 20 seconds (the default) to 30. Kind to the API, and longer than the 13-second final step, so the full confirmation sequence runs. At the 10-second floor the 13-second step is skipped.
- Optimistic updates for locks: off. Show what the API confirmed.
- Adaptive Aggressive: on, for every lock or only the ones you operate from Home Assistant.

Configure → Adaptive Aggressive, after the integration is set up.

## Debug Polling Mode

For testing, Debug Polling Mode gives you 1-second polling for a short window:

- Start it with the **Start debug polling** button on the U-Tec Integration device, or the `u_tec.start_debug_polling` action. Stop it early with **Stop debug polling** or `u_tec.stop_debug_polling`.
- It polls every second for 2 minutes, about 120 requests, then goes back to your configured interval on its own. Pressing start again while it runs does not extend it.
- While it runs, Adaptive Aggressive, push state, and optimistic updates are paused, so what you see is raw polled state. Pushes still count in the push sensors and update Last Push.
- It ends early if polls fail enough to mark entities unavailable.
- It is never saved. A restart or reload always comes back at your configured interval.
- Start, stop, the reason, and the request count are logged at WARNING. The **Debug polling** diagnostic binary sensor shows whether a session is running, when it ends, and how many requests it made.

## API usage sensors

All on the **U-Tec Integration** device, all diagnostic. Counters live in memory and start from zero after a restart or a reload of the integration. Totals are `total_increasing`, so long-term statistics handle the reset.

| Sensor | What it counts | Default |
| --- | --- | --- |
| API requests | Every request this install made | On |
| API requests (last hour) | Rolling 60 minutes | On |
| API requests per device (last hour) | The above divided by your device count | On |
| API state queries | Regular polls, confirmation polls, initial state fetches | On |
| API commands | Lock, unlock, on, off, dimming | On |
| API commands skipped (passage mode) | Lock commands not sent because a fresh check confirmed Passage mode | On |
| API discoveries | Device discovery, every 5 minutes | On |
| API failures | Errors, including U-tec's HTTP 200 error replies | On |
| Pushes received | Authenticated pushes that reached Home Assistant | On |
| API last response time | Latency of the latest request, in ms | Off |
| API last response | When the latest request finished | Off |
| Pushes applied / Pushes ignored | Pushes that changed state, and ones that didn't (keepalives, unselected devices, debug mode) | Off |
| API commands sent (per device) | Commands sent to that one device | Off |
| Adaptive Aggressive bursts | Confirmation bursts started, including re-checks | On |
| Adaptive Aggressive polls | Burst polls made (one per interval) | On |
| Adaptive Aggressive changes caught | State changes a burst poll saw before any push or regular poll | On |
| Adaptive Aggressive average time to detect | Seconds from command to the burst poll that caught the change | On |
| Adaptive Aggressive average polls to detect | Burst polls it took, on average, to catch the change | Off |
| Adaptive Aggressive bursts ended by push | Bursts a push notification answered first | On |
| Adaptive Aggressive bursts ended by failures | Bursts stopped because polls kept failing | On |
| Adaptive Aggressive bursts that ran out | Bursts that used the whole schedule without seeing the change | On |

The diagnostics download includes the same numbers, plus per-device query and command counts and, for Adaptive Aggressive, bursts ended by a regular poll, confirmations where nothing had changed (locking a door that was already locked), cancelled bursts, and the last catch.

## Install

### HACS

1. In HACS, add this repository as an integration.
2. Search for U-Tec and install it.
3. Restart Home Assistant.

### Manual

Copy `custom_components/u_tec` into your Home Assistant `custom_components` directory and restart.

## Credentials

You need API credentials before setup. They come from the Xthings Home app (formerly U-Home), version 3.5.5 or later. No developer-portal request.

1. Open the Xthings Home app and go to My Account.
2. Tap OpenAPI.
3. Activate OpenAPI, choose your role and products, then tap Activate Openapi.

![Steps to enable OpenAPI in the app](images/api_enable_steps.png)

Set `RedirectUri` to `https://my.home-assistant.io/redirect/oauth` exactly. Do not replace the hostname. Confirm `Scope` is `OpenAPI`, then save.

![API credentials screen](images/api_credentials.png)

The integration needs the Client ID and Client Secret. Details are in the [Developer API documentation](https://doc.api.u-tec.com/#intro). API problems go to [Xthings support](https://developer.xthings.com/hc/en-us/requests/new). See [issue #36](https://github.com/LF2b2w/Uhome-HA/issues/36) for the credential flow. Screenshots courtesy of @geofox784.

Home Assistant must know its own URL before the next step. Settings → System → Network, and set the Home Assistant URL. A local install is usually `http://homeassistant.local:8123`. Push delivery also needs external access, normally Nabu Casa.

## Configure

1. Settings → Devices & services → Integrations.
2. Add integration, search for U-Tec, and enter the Client ID and Client Secret.
3. Sign in on the U-Tec [OAuth page](https://oauth.u-tec.com/login/auth) and authorize the connection.
4. Link the account when Home Assistant asks.

Rotate credentials from the integration's Reconfigure action. You do not need to remove the integration. Polling interval, optimistic updates, and Adaptive Aggressive are on Configure after setup.

## Polling interval

Configure → Polling Interval. The minimum is 10 seconds. A value below 10 saved under 0.6.1 is raised to 10 when the integration loads, with a warning in the log. A `scan_interval` below 10 in `configuration.yaml` is treated as 10.

## Troubleshooting

- **Lock state is slow to update.** Push is often unreliable. Turn on Adaptive Aggressive rather than lowering the interval. Check **Pushes received**: if it never moves, push isn't reaching you.
- **Entities flap to unavailable.** Two failed polls in a row mark entities unavailable until the next good poll or push. **API failures** shows how often that's happening. Intermittent U-tec 500 errors do happen.
- **A warning about the poll interval at startup.** Your saved interval was below the 10-second minimum and was raised to 10. Nothing else to do.
- **Debug logs.** Settings → Devices & services → U-Tec → Enable debug logging, reproduce the problem, then disable it to download the log. Logger: `custom_components.u_tec`.
- **Diagnostics.** The integration's ⋮ menu → Download diagnostics includes device state, coordinator health, debug polling, and API usage. Credentials are redacted.

## Help

Questions and setup notes live in the [FAQ discussion](https://github.com/LF2b2w/Uhome-HA/discussions/2). Bugs go on [Issues](https://github.com/LF2b2w/Uhome-HA/issues). Pull requests are welcome. Changes that affect how much this integration polls or retries are worth a second reviewer.

MIT licensed. See [LICENSE](./LICENSE).

Made by @LF2b2w, with contributions from the community. Not affiliated with U-tec or Xthings.
