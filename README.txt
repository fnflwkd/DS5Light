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

Install Python 3.12 x64. The build script also uses the Windows .NET Framework C# compiler. Run powershell -ExecutionPolicy Bypass -File build.ps1 in this directory. It creates a virtual environment, installs the pinned dependencies, runs tests, builds the helper/app and collects third-party notices. Output: dist-0.9.1/DS5Light.

License and status

Free use, modification and free redistribution are permitted under the custom license (LICENSE.txt). Selling the app or integrating it into paid products/services requires separate permission. Using it as a tool for monetized game videos/streams is allowed. This is not an OSI-approved open-source license. See English translation (LICENSE_EN.txt); the Korean original controls. Third-party components retain their own licenses. Keep vendor, THIRD_PARTY notices and relevant documentation when redistributing.

The icon's original source and redistribution permission remain unverified. The application license does not grant rights to that asset. This package is a pre-publication review build.

Microsoft runtime redistribution conditions are included in THIRD_PARTY/upstream/Python-3.12.10-CRT-LICENSE.txt. See sources (SOURCES.md) for component provenance.

Synthetic/unit tests and UI checks do not establish real-game suppression quality, controller feel, latency or FPS impact. Universal music/dialogue removal is not claimed. Version 0.9.0 adds UI localization; audio DSP and channel mixing are unchanged from 0.8.7. No new physical audio/controller test was performed for this update.

Studio presets: Audio Haptics and DS Native (studio-presets/README.txt). Back up your settings before applying.

Studio dongle slots (0.9.1)
Select Studio slots, then Read / Refresh to read names for slots 1–10 from the connected dongle. Empty means an empty slot; Unavailable means its information could not be read. Select the intended device if multiple candidates are listed.
Select a slot, stop audio and press Apply. This loads all settings in that slot, including triggers and gyro. PC presets are separate. The app does not overwrite saved slots or switch automatically.
Do not perform slot operations in the Studio portal concurrently. A timeout does not prove activation failed; check the current settings in the portal. If USB reconnection is required, reconnect the dongle and refresh.
