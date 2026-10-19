# DS5 Light

[한국어 소개](PRODUCT_KO.md) · [Setup guide](SETUP.md) · [User guide (TXT)](README.txt)

A lightweight Windows audio-haptics preprocessor for **[DS5Dongle-Studio](https://github.com/artzox/DS5Dongle-Studio)**.

DS5 Light adds adaptive filtering to the copy of game audio sent to your dongle. It aims to reduce unwanted vibration from music and dialogue while retaining the timing and texture of game effects. Your listening audio stays unchanged.

## Features

- Capture a selected game's audio or an entire output device.
- Choose Detail, Balanced or Suppression, with adjustable suppression strength.
- Include rear L/R, Center and LFE separately with 5.1 input.
- Save game settings in 12 preset slots.
- Switch between Korean and English UI.
- Use the included **Audio Haptics** and **DS Native** Studio profiles.

## How the filter works

The filter considers how sound changes over time, adding another layer before Studio's own processing:

1. **Adaptive background estimation:** Track the recent energy level in four frequency bands. Sound that stays near its background level receives more attenuation than sound rising above it.
2. **Transient protection:** Compare sudden level increases with recent changes to reduce attenuation around new impacts, shots and other brief events. A sudden sound does not bypass the filter completely.
3. **Limited, smooth attenuation:** Adjust each band's gain gradually, using shared left/right control. The filter reduces levels rather than applying an automatic output boost.

This is CPU-based signal processing, with no large AI model or GPU inference in the default path. It does not identify or separate individual instruments or voices: music transients can pass through, and sustained effects can also be reduced. Results depend on the game, audio mix and Studio settings.

## Requirements

- Windows 10/11 x64. Selected-game capture requires Windows build 20348 or later; earlier Windows 10 builds can use whole-device capture.
- A supported dongle running DS5Dongle-Studio and a DualSense controller.
- A working Studio audio-haptics setup. Start with the supplied Audio Haptics profile.

## Download and start

Use the **Windows-x64 ZIP** from this repository's Releases section, rather than GitHub's source-code ZIP. Extract the entire archive and run `DS5Light.exe`; no Python installation is needed for the packaged app.

1. Follow the [setup guide](SETUP.md) to store the supplied profiles in Studio.
2. Activate **Audio Haptics** in Studio and open DS5 Light.
3. Select your game, turn on the PC suppression filter, choose **Balanced**, and select **Start**.
4. For native-haptics games, stop DS5 Light and activate **DS Native** in Studio.

The PC filter is off in the shipped default configuration. Channel-format selection does not automatically read the game's internal audio settings.

[Studio profile instructions](studio-presets/README.txt) · [Build instructions](README.txt) · [Component sources](SOURCES.md)

## Attributions and licenses

DS5 Light is an unofficial companion to [DS5Dongle-Studio](https://github.com/artzox/DS5Dongle-Studio), independently maintained rather than an official Studio release. Thank you to the upstream developers and contributors.

| Project / component | License | Use in DS5 Light |
|---|---|---|
| [DS5Dongle-Studio](https://github.com/artzox/DS5Dongle-Studio) | MIT | Portions of the `ds5audio.py` audio bridge; original notices for awalol and artzox are retained |
| [NumPy](https://numpy.org/) | BSD-3-Clause; bundled components have additional notices | Numerical array processing |
| [SciPy](https://scipy.org/) | BSD-3-Clause; bundled components have additional notices | Digital filters and signal processing |
| [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) | Apache-2.0 for the fork's contributions; retained PyAudio/PortAudio MIT notices | Windows audio capture and playback |
| [Python](https://www.python.org/) | PSF license and included component notices | Packaged runtime |
| [PyInstaller](https://pyinstaller.org/) | GPL-2.0-or-later with the distribution exception; component terms also apply | Application packaging |
| DS5 Light's own code | [Custom free-use license](LICENSE.txt) | Application UI, processing and integration; sales and paid integration restricted |

This table summarizes the main components, not every bundled dependency. Original Studio notices are in [vendor/LICENSE-Studio.txt](vendor/LICENSE-Studio.txt). See [SOURCES.md](SOURCES.md), [upstream notices](licenses/upstream), and the release's `THIRD_PARTY` directory for detailed provenance and license texts. Third-party licenses remain in force; the restrictions on DS5 Light's own code do not override them.

Background-estimation concepts were also informed by [noisereduce](https://github.com/timsainb/noisereduce). Its implementation is not copied into the runtime; this is design reference, not an additional code dependency.

## License

Free use, modification and free redistribution are permitted under the [DS5 Light license](LICENSE.txt). Selling the program or integrating it into paid products or services requires separate permission. Using it as a tool for monetized game videos or streams is allowed.

[English license translation](LICENSE_EN.txt) · [Distribution policy](DISTRIBUTION_POLICY_KO.md)

The Korean license text controls. This custom license is not an OSI-approved open-source license. It does not grant rights to third-party assets; the current icon's original source and redistribution permission remain unverified.
