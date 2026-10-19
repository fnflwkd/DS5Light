Choose a Studio preset

한국어 (README_KO.txt)

| File | Portal action | Scope |
| Audio-Haptics.profile.json | Import Profile | Audio-haptics setup for DS5 Light; save to a slot you choose |
| DS-Native.profile.json | Import Profile | Contributor's native-game setup; save to a slot you choose |

Generated from the later user-provided ds5dongle-slots.json, not the initial handoff backup or a fresh device read. Included Audio Haptics values: Intensity 100, Smoothness 30, Gate 25, LPF 80Hz, Split 50Hz/100/40, Slope 24, Haptics Gain approximately 1.3, Speaker Volume/Gain 0. These preserve that backup, not a universal recommendation for every device.

Back up first
Use Back up all slots in your own portal. Export Profile can additionally preserve your current active configuration. DS Native is the contributor's preset, not a restoration of your personal previous settings.

Single profiles (recommended)
1. If DS5 Light is running, stop it; connect the Studio portal.
2. Import the chosen .profile.json. Respond to the macro-selection prompt deliberately. Both supplied profiles originally disable all macros.
3. Review settings and choose Save to Device.
4. Save the current device configuration into a slot you choose. Repeat for the other profile in another slot. Later, activate the appropriate slot to switch.
5. Activate Audio Haptics before starting DS5 Light. When switching to DS Native for a game's genuine native haptics, also stop DS5 Light. Turning only its PC filter off does not stop audio forwarding.

Each profile includes all its trigger, device, gyro and other settings, not just audio settings. Both profiles have zero active custom trigger states, so unused state-storage data is omitted from the single-profile exports; regular trigger fields are retained. Other files containing custom effects may write those effects during import itself.

Validation
Both single profiles were compared with the source backup. Formats were checked against the local portal's Import Profile code. No hardware import, save or haptics test was performed. Firmware/portal versions may differ. See PROVENANCE.json for the source hash.
