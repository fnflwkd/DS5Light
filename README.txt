DS5 Light

First-time setup: Studio firmware, slots and PC setup (SETUP.md). Existing Studio users do not need to reflash firmware.

한국어 안내 (README_KO.txt)

A small, unofficial Windows audio-haptics preprocessor for DS5Dongle-Studio.
It processes a copy of game audio sent to the dongle, leaving your listening audio and Studio firmware unchanged.

Download and run

Use the Windows x64 release ZIP, extract all files, and run DS5Light.exe. Keep the _internal folder beside it. No Python installation is required for the packaged app.

The intended platform is Windows 10/11 x64. Game-only capture also requires Windows build 20348 or later (including Windows 11); older Windows 10 builds can use whole-device capture. The executable is unsigned. A clean-machine compatibility test has not yet been completed.

Language

On first launch the Windows display language selects Korean; all other languages default to English. Use 한국어 / English at the top right to choose a language. It is saved independently of game presets and takes effect the next time you open the app. Changing it does not restart the audio stream.

Basic use

1. Select Whole device or Selected game only. For game-only capture, start your game, refresh the list and select its actual executable. Other processes' music or video audio should be excluded by this capture mode.
2. Select your input/output in Connection & help. Automatic selection uses the original bridge's selection method.
3. Choose the channel format. Whole-device capture follows the actual Windows endpoint format. For a selected game, choose the requested capture format while stopped. This is not automatic detection of the game's own audio settings.
4. With 5.1 input, front L/R stay at 100%. Rear L/R, Center and LFE can be added separately. Try disabling Center for unwanted dialogue vibration, or LFE for unwanted music bass. Stereo disables these extra-channel controls.
5. Enable the PC suppression filter to use Detail, Balanced or Suppression, or adjust its strength. The filter is off in the shipped default configuration. Disabling it bypasses PC suppression only; channel mixing and Studio processing remain active.
6. Select Start. Save settings in one of the 12 game preset slots when satisfied.

The hard/soft limiter acts on extra-channel summing; it is inactive for stereo. Hard clipping is the default.

The game's normal rumble uses its existing separate path.

Saved settings

Presets: %LOCALAPPDATA%/DS5Light/presets.json. Language: %LOCALAPPDATA%/DS5Light/ui.json. Older Korean presets remain compatible; user-assigned names are not translated. Device settings are not automatically changed. Audio is not recorded or uploaded.

Build from source

Install Python 3.12 x64. The build script also uses the Windows .NET Framework C# compiler. Run powershell -ExecutionPolicy Bypass -File build.ps1 in this directory. It creates a virtual environment, installs the pinned dependencies, runs tests, builds the helper/app and collects third-party notices. Output: dist-0.9.8/DS5Light.

License and status

Free use, modification and free redistribution are permitted under the custom license (LICENSE.txt). Selling the app or integrating it into paid products/services requires separate permission. Using it as a tool for monetized game videos/streams is allowed. This is not an OSI-approved open-source license. See English translation (LICENSE_EN.txt); the Korean original controls. Third-party components retain their own licenses. Keep vendor, THIRD_PARTY notices and relevant documentation when redistributing.

The icon's original source and redistribution permission remain unverified. The application license does not grant rights to that asset. This package is a pre-publication review build.

Microsoft runtime redistribution conditions are included in THIRD_PARTY/upstream/Python-3.12.10-CRT-LICENSE.txt. See sources (SOURCES.md) for component provenance.

Synthetic/unit tests and UI checks do not establish real-game suppression quality, controller feel, latency or FPS impact. Universal music/dialogue removal is not claimed. Version 0.9.0 adds UI localization; audio DSP and channel mixing are unchanged from 0.8.7. No new physical audio/controller test was performed for this update.

Studio presets: Audio Haptics and DS Native (studio-presets/README.txt). Back up your settings before applying.

Studio dongle slots (0.9.8)
Select Refresh in the Studio panel on the right to read names for slots 1–10 from the connected dongle. Empty means an empty slot; Unavailable means its information could not be read. Select the intended device if multiple candidates are listed.
Select a slot, stop audio and press Apply. This loads all settings in that slot, including triggers and gyro. PC presets are separate. The app does not overwrite saved slots or switch automatically.
Do not perform slot operations in the Studio portal concurrently. A timeout does not prove activation failed; check the current settings in the portal. If USB reconnection is required, reconnect the dongle and refresh.

Studio strength (0.9.8)
The Studio panel reads current values once when the app opens. Release a slider to apply. This controls Studio Intensity (0–200%), separately from PC suppression. Strength can be applied while audio is running.
Only current dongle settings change; saved slots are not overwritten. Loading another slot restores that slot’s strength. Do not assume changes persist across power cycles.
Turn on DualSense and confirm a Studio response before using the controls. The Studio panel does not poll connection or strength while idle. A failed operation disables controls. Turn it on again and select Refresh. Do not change settings concurrently in the portal.

Native haptics / adaptive triggers (0.9.8)
Studio settings automatically reads current values; then use the sliders. Failed reads or writes disable the affected controls. Only current settings change; saved slots are not overwritten.
Native haptics gain: Studio range 1.00–2.00×. This shared gain also affects audio-derived haptics; it does not provide attenuation below 1×.
Adaptive-trigger reduction: one shared setting for both sides, 0–10. Zero means no added reduction; 10 requests maximum reduction. Depending on the effect, reduction may be weak or unavailable. Each side retains its effect shape. This is not a strength percentage or a guaranteed complete off switch.
Older firmware support may differ. Read the current value again after any failure. After returning to zero, actual force restoration must be checked against subsequent game trigger output.

Battery display (0.9.8)
The main footer shows Studio battery level (10% steps), charge state and last-read time. It reads once after launch, then checks battery and connection every five minutes. This is the last sampled value; connection changes can take about five minutes to appear. Click the display to refresh immediately.
Automatic checks pause while minimized and resume when due after restoring the window. Failed/disconnected reads hide the cached percentage. With multiple candidates, select a device in Studio settings. That panel has no periodic polling; applying settings separately verifies a device response.
Battery access is read-only, outside the audio thread, with no animations, notifications or battery log storage. Concurrent portal queries can cause a failed read.

Process sorting and last settings (0.9.8)
Choose Name A–Z or CPU usage below the game selector. CPU is a roughly 0.5-second, on-refresh estimate normalized across logical CPUs; there is no continuous monitoring. Inaccessible/exited processes show CPU —. GPU sorting is not included in this version.
PC options are automatically saved shortly after changes and again on normal exit. Capture scope, game exe name, channels, devices, filters, sort order, selected PC slot and expanded details are restored next launch. This is separate from preset slots, in LocalAppData/DS5Light/last_settings.json.
The game is matched by exe name; multiple matches require manual selection. Old PIDs are never saved or reused. Press Start to begin audio. Studio slots and strengths are not applied automatically. Unreadable settings files are preserved. To reset, close the app and rename last_settings.json as a backup.
The language selector is labeled Language. Language changes still apply on the next launch.

Direct strength adjustment (0.9.8)
Mouse changes apply once on release; keyboard changes apply shortly after the last key release. Dragging only updates the display. Unchanged values are not sent; writes are verified by reading back.
Current values are read on opening, manual refresh, device selection and after slot activation when reconnection is unnecessary. There is no idle strength polling. Battery checks remain every five minutes. Slot activation commands and storage behavior are unchanged.

Current Studio slot (0.9.8)
Reading selects the currently loaded slot in the list. Edited indicates current settings differ from the saved slot. If the current slot cannot be identified, slot 01 is not selected as a fallback; select manually. Reading never activates a slot.

Integrated layout (0.9.8)
Studio controls now occupy the right side of the main window. Order: Overall haptics strength (Gain), Audio-haptics strength, Adaptive-trigger strength reduction. Gain is displayed as 100–200%. The inspected Studio firmware resets out-of-range gain to 100%; 300% is not supported.
DS5 Light presets save and restore PC capture, channel and filter options only. They do not save or restore Studio Gain, Intensity, trigger reduction or selected dongle slot. Loading a PC preset leaves current dongle values unchanged. Explicitly applying a Studio slot loads that slot's strengths.
A static four-cell battery icon reuses the existing five-minute sample: 1–25%=one cell, 26–50%=two, 51–75%=three, 76–100%=four. Unknown readings show ?. Click to refresh. No animation or additional polling is added.
