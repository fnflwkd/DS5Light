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
