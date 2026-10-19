# Getting started with DS5 Light

[한국어](SETUP_KO.md) · [Application guide](README.txt)

## First-time walkthrough

Have a Studio-compatible dongle, DualSense, Windows PC and the extracted release ZIP ready. Existing Studio users can skip firmware installation.

1. **Prepare Studio:** Follow the official instructions below only if Studio is not installed. A working setup does not need resetting or reflashing for DS5 Light. Back up existing settings first.
2. **Find the two profiles:** Open studio-presets in the extracted ZIP. Use Audio-Haptics.profile.json and DS-Native.profile.json. Do not use the full-slot Restore command for these files.
3. **Store both in Studio:** Open the [Studio configuration portal](https://artzox.github.io/DS5Dongle-Studio/ds5-config-portal.html) and use Connect. For older firmware, use the portal paired with that release. Back up your own slots. Use Import Profile for Audio-Haptics.profile.json, then Save to Device. In Slots, save the current settings to a slot you choose and name it Audio Haptics. Repeat with DS-Native.profile.json in a different slot. Saving over an occupied slot replaces that slot. Specific slot numbers are not required.
4. **Start audio haptics:** Activate Audio Haptics in Studio. Open DS5Light.exe. Turn on the PC suppression filter and choose Balanced. The shipped default has the filter off, so enable it for additional suppression.
5. **Select the game:** Start your game. While DS5 Light is stopped, choose Selected game only, Refresh, and the actual game executable. Choose the needed channel format, then Start. Whole device includes all apps playing on that endpoint and is also an option when game-only capture is unavailable. Channel-format details are explained below.
6. **Save and switch back:** Save PC settings in a game preset. For native-haptics games, stop or close DS5 Light and activate DS Native in Studio. Switching the PC filter off alone does not stop forwarding audio.

DS Native is the contributor's configuration. To restore your own previous setup exactly, use your own backup or preserved slot. Imported profiles also contain trigger/device settings. See the [profile instructions](studio-presets/README.txt).

## Relationship to Studio
DS5 Light is an **unofficial companion PC preprocessor for DS5Dongle-Studio**, not a modified Studio firmware distribution. It reuses portions of Studio's ds5audio bridge, with the original MIT notices retained in vendor/.

Signal path: copy of game audio → DS5 Light channel selection and PC filter → Studio audio-haptics processing on the dongle → controller. Your listening audio stays on its existing output. Turning the PC filter off does not disable Studio filtering.

## 1. Prepare Studio
- Already using Studio? Keep your working firmware and matching portal. DS5 Light does not require a new UF2 or a reset.
- New to Studio? You need compatible dongle hardware and a DualSense. Follow the upstream [Quick start](https://github.com/artzox/DS5Dongle-Studio#quick-start) and [releases](https://github.com/artzox/DS5Dongle-Studio/releases) to install the firmware for your board and connect your controller. Use the portal paired with that firmware release.
- Firmware is not bundled here. A flash_nuke reset is not a routine installation/update requirement. Back up existing slots in the portal before changing settings.

## 2. Prepare a Studio slot
PC presets and Studio dongle slots are **separate**. Loading a preset in DS5 Light does not activate a Studio slot.

Importing the supplied profile already includes the values below; you do not need to enter them again. To preserve existing slots, save the two profiles in separate empty slots.

| Studio setting | Baseline for this app's path | Purpose |
|---|---|---|
| Auto-Haptics Mode | Mix | Combine audio-derived haptics with normal game rumble |
| Auto-Haptics DSP Source | ch0/1 | Analyze the processed audio pair sent by the PC |
| Native Passthrough in Mix | 0% | Avoid additionally passing the duplicate audio pair through the separate haptic path |
| Converted Rumble Strength | Keep your preference; initial reference 50 | Controls normal game rumble separately from audio-derived haptics |
| Auto-mute Speaker (Mix) | On | Suppress copied game audio from the controller speaker |
| Effect Leak Volume | Start at 0 | Baseline does not use speaker effect leak |

Native Passthrough at 0 does not turn off normal rumble. This is a non-native-game setup. Keep separate existing profiles for games with genuine native haptic streams or controller-speaker effects.

### Filter values in the included Audio Haptics profile
Start with the supplied profile as your baseline, then tune it for individual games. You can choose any available slot number.

| Setting | Included profile |
|---|---:|
| Intensity | 100 |
| Smoothness | 30 |
| Noise Gate | 25 |
| LP Cutoff | 80 Hz |
| Filter Slope | 24 dB/oct |
| Frequency Split Crossover | 50 Hz |
| Low Band Gain | 100 |
| High Band Gain | 40 |
| Haptics Gain | approximately 1.3 |

Speaker Volume and Speaker Gain are both 0 in the supplied profile. They are already included in its JSON; no separate change is needed. See the [profile instructions](studio-presets/README.txt) for application details.

## 3. Run on the PC
1. Keep game audio playing through your usual speakers/headphones.
2. Extract the entire Windows x64 ZIP and run DS5Light.exe, retaining the _internal folder.
3. Choose Whole device or Selected game only. For game-only capture, start the game, refresh and select its actual executable. Whole-device capture also includes other apps playing on that endpoint.
4. Check the input and DualSense output under Connection & help. Compare your Windows/game channel setup with the app's requested/actual capture format. The app does not automatically read in-game audio settings.
5. Select Start. **The PC filter is off by default.** Enable it and start with Balanced if you want additional suppression. Rear, Center and LFE switches apply to 6ch input only.
6. Save your PC settings in a game preset slot. Ensure the corresponding Studio slot is also active when using it later.


### Choose the channel format

- **Whole device:** The actual Windows capture format determines whether 5.1 or stereo is available. Automatic device selection detects the format after starting.
- **Selected game only:** While stopped, choose `5.1 channels (Home theater)` or `2 channels (Stereo)` to match your game audio setting. This requests a capture format; it does not detect the game's internal setting.
- Rear L/R, Center and LFE can be toggled with actual 6ch input and are disabled for 2ch. All three are enabled in the shipped default configuration.
- Game-only capture requires Windows build 20348 or later. Use Whole device on unsupported Windows 10 builds.

## 4. Adjust haptics and troubleshoot
- Try disabling Center for dialogue vibration or LFE for music bass. Dialogue/music can also exist in other channels.
- Suppression strength is not a vibration-volume control. More suppression can also weaken effects. Change one setting at a time, including when tuning Studio strength.
- No haptics? Check the active Studio slot, Mix, ch0/1, dongle connection, output selection and filter bypass.

