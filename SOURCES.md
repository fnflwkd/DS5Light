# Sources and rights

- **Studio bridge:** [artzox/DS5Dongle-Studio](https://github.com/artzox/DS5Dongle-Studio), commit `8613a5388baa77f8d9e389b20069d6918e3067a1`. Functions from `vendor/ds5audio_original.py` are loaded via AST. The original MIT notice is preserved in `vendor/LICENSE-Studio.txt`.
- **DSP:** Independently implemented adaptive band-level background estimation, change detection and gain smoothing. Background-estimation concepts were informed by [noisereduce](https://github.com/timsainb/noisereduce); its implementation is not copied into the runtime.
- **Process capture:** C# implementation using Microsoft's application-loopback API; [official documentation/sample](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/).
- **PyAudioWPatch 0.2.12.8:** Exact source and wheel provenance is recorded in `licenses/PyAudioWPatch-0.2.12.8/PROVENANCE.json`; Apache text and original PyAudio/PortAudio notices are retained.
- **Dependencies:** See `requirements*.txt` and the built release's `THIRD_PARTY/manifest.json`. Third-party components retain their own terms.
- **Icon:** AI-edited version of a user-provided image. Original source and redistribution permission are unverified. Excluded from the app's own license.
- Separate StudioProxy evaluation code, research source archives, videos, conversations and unrelated device backups are excluded from this repository.
- **Localization (0.9.0):** UI-only English strings and an independent language preference. Audio DSP, channel mixing, capture and preset schema are unchanged from 0.8.7. English license translation does not replace the controlling Korean original.

- `studio-presets/` contains user-authorized Audio Haptics and DS Native single profiles, with source provenance and application instructions.

## Studio slot support (0.9.1)
Independent host implementation of Studio commands 0x0a (info) and 0x09 (activate), feature reports 0x80/0x84. No save/reconnect commands. Reviewed local Studio source snapshots (their exact upstream commit is not established by these files):
- `studio-src_cmd.cpp` SHA256 `0fbb1616c8531e03c3b1d5480371ded68bec632dcf54f10c7f6a3d045c815365`
- `studio-src_config.h` SHA256 `f25a40c416615efb8d28ecc52560e881b9e63025f4a2a2f9dc1c2c059ad0b857`
- `studio-ds5-config-portal.html` SHA256 `db8027d497fcbf463def816180113b723f547d45c31169aad76cc79be0744f15`

HID access: hidapi Python package 0.15.0 (https://github.com/trezor/cython-hidapi). Included original license texts are collected in THIRD_PARTY.

DS5 Light uses cython-hidapi under its BSD-style license option; all supplied license texts are retained.

DS5 Light uses cython-hidapi under its BSD-style license option; all supplied license texts are retained.


## 0.9.2 Studio Intensity control
The existing local Studio cmd.cpp snapshot maps field 0x13 to auto_haptics_gain. Command 0x04 reads it and 0x01 updates current RAM settings; report 0x81 returns the response. This app verifies the value by reading it back and does not issue config-save (0x02), slot-save (0x08), or forced reconnect (0x03).
The local bt.cpp snapshot switches USB identity or disconnects USB when the controller disconnects. The dialog checks candidate USB presence approximately every two seconds after a successful Studio response; this is not an independent Bluetooth telemetry stream. On 2026-10-23, actual Intensity read/write/readback was tested at 100 → 99 → 100, restoring the original value. Actual controller power-off/on behavior has not been tested for 0.9.2. No upstream source was copied for this addition.


## 0.9.3 Native gain and shared trigger reduction
Same local Studio snapshots: cmd.cpp field 0x01 is little-endian float haptics_gain (1–2); field 0xc0 is uint8 trigger_reduce (0–10). config.cpp validates those ranges. audio.cpp uses haptics_gain both for native channel 2/3 and audio-derived haptics; it is not a native-only volume control. state_mgr.cpp writes trigger_reduce to the high nibble of output byte 36 with AllowMotorPowerLevel, preserving the rumble nibble. This shared motor reduction preserves each trigger effect; at_strength (custom R2 effect) was deliberately not used. Zero adds no override; force restoration timing requires live gameplay testing.
On 2026-10-23, actual reads and same-value writes/readbacks passed for gain 1.2999999523162842 and reduction 0. No saved slot, trigger shape, rumble setting, or firmware was changed. Physical native-haptic/trigger strength differences have not been measured. The custom protocol implementation uses no copied upstream source for these controls.


## 0.9.4 Battery display
Local cmd.cpp snapshot: read-only field 0x68 exposes input report byte 52 without clearing it; it can be stale while the controller is off. The local portal decodes low nibble × 10 as percent and upper nibble as charge state, treating raw zero as no data. The app uses that mapping, labels unknown charge states explicitly, and validates levels 0–10. It queries slot info for Studio identity before the battery read. No battery settings or notifications are changed.
Battery/USB presence checks run every 300 seconds while visible, once on startup and on explicit refresh/target change. Settings-window presence checks also use 300 seconds from 0.9.4. The last-read timestamp makes the sampling delay explicit; physical disconnect detection may take about five minutes. HID transactions are serialized across app-owned settings and battery workers. This cannot coordinate with an external Studio portal.


## 0.9.5 Process sorting and PC session persistence
Independent ctypes implementation using Windows Tool Help process enumeration and GetProcessTimes; no new third-party dependency. CPU sorting uses two process-time samples separated by a 0.5-second wait, checks creation timestamps to reject PID reuse, and divides by logical CPU count. It is an on-demand estimate, not Windows Task Manager's frequency-adjusted CPU/GPU telemetry. GPU sorting was not added. The audio capture/processing code is unchanged. A separate validated, atomically replaced last_settings.json restores PC choices without starting audio or writing Studio settings.


## 0.9.6 Direct strength UI
The slot activation protocol is unchanged. Fixed disabled strength controls after slot activation by re-reading strength values when USB reconnection is not required. The settings dialog reads once on opening/refresh/selection and has no idle polling. Slider release applies only the changed control, using the existing preflight/write/readback protocol; keyboard edits are debounced 300 ms. Partial read failures disable only affected controls. No default slider values are sent during startup. Battery polling is unchanged.

## 0.9.7 Current slot and trigger limitation (2026-10-24)
Studio cmd.cpp command 0x67 supplies current slot index, edited flag and UTF-8 name; command 0x05 supplies firmware text. These are commands, not configuration field IDs. Added independent read-only protocol handling with unknown-slot and unsupported-response states; slot activation remains unchanged. Actual read: firmware 1.42.0, index 3 (04 Audio Haptics), edited=true. Source UI selected that slot without activating it or starting audio.

Primary upstream release: https://github.com/awalol/DS5Dongle/releases/tag/v0.7.2-hotfix (release commit c3308ae; accessed 2026-10-24). Its trigger_reduce note explicitly states that not every trigger effect responds to the built-in motor power reduction field. Studio documents its shared reduction as ported from this feature: https://github.com/artzox/DS5Dongle-Studio#trigger-strength-reduction-new-in-1420 . These references explain a limitation, not a measured force result for this controller. No source was copied from the release.

Local state_mgr.cpp applies the override when constructing an output packet; main.cpp can skip unchanged output while speaker audio is active. Delayed output refresh is a possible additional cause, not a confirmed diagnosis. The user's custom-effect 0/10 comparison showed little perceived difference. This release does not claim to fix physical force reduction and does not rewrite custom trigger effects. UI and both manuals now describe 10 as a maximum reduction request rather than guaranteed minimum force.

## 0.9.8 Integrated UI and gain bound
Same local Studio config.cpp snapshot, validate_config_body: haptics_gain below 1.0, above 2.0 or NaN resets to 1.0. The native protocol remains 1–2; only UI presentation changes to 100–200%. No unsupported 300% write or firmware edit. Studio activation and strength write methods, DSP, audio routing and PC preset schema are unchanged. Battery icon uses existing sample data with no new HID polling. Real trigger force and audio performance were not retested for this UI change.
