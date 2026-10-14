# Pisound Micro GPIO-to-MIDI bridge

A small Raspberry Pi service that reads the four Pisound Micro buttons directly
through Linux GPIO and exposes them as MIDI CC messages for MODEP/MOD-UI MIDI
Learn. It does not depend on the Pisound Micro Mapper or on a particular
pedalboard.

## Hardware and mapping

The buttons use the GPIO lines named `B03`, `B07`, `B11`, and `B15`. Each line
is configured as an active-low input with a pull-up; the button is considered
pressed when its line is active.

| Button | MIDI message |
| --- | --- |
| B03 | Channel 1, CC20: 127 while pressed, 0 on release |
| B07 | Channel 1, CC21: 127 while pressed, 0 on release |
| B11 | Channel 1, CC22: 127 while pressed, 0 on release |
| B15 | Channel 1, CC23: 127 while pressed, 0 on release |

The bridge opens an ALSA virtual MIDI output named `Lezart-Boutons`. Learn the
corresponding CC on a MODEP parameter to assign a button.

## Debounce

The script samples the GPIO lines every 5 ms. A press or release is emitted
only after the new state has remained unchanged for 25 ms. This stable-state
debounce suppresses short mechanical bounce transitions on both edges; it also
adds up to 25 ms of response delay.

## Requirements

- Raspberry Pi OS/Debian on the Pisound Micro hardware
- Python 3
- Python bindings for libgpiod 2.x (`gpiod`)
- `python-rtmidi` with ALSA support (`rtmidi`)
- ALSA MIDI utilities such as `aconnect` and `aseqdump` for diagnosis

On Debian-based systems, install the distribution packages where available:

```sh
sudo apt install python3-gpiod python3-rtmidi alsa-utils
```

The script uses the libgpiod 2.x Python API. Check `python3 -c 'import
gpiod; print(gpiod.__version__)'` if GPIO API errors occur.

## Install and run

The Pisound Micro Mapper and this bridge cannot own the same GPIO lines at the
same time. Keep the Mapper configuration file; stop its service before testing
the bridge:

```sh
sudo systemctl stop pisound-micro-mapper.service
sudo install -m 0755 pitcher-modep-buttons.py /usr/local/bin/pitcher-modep-buttons
sudo /usr/local/bin/pitcher-modep-buttons
```

Run it in the foreground first. The process reports the selected GPIO chip and
prints each debounced CC transition. Stop it with `Ctrl-C`. If GPIO permission
is denied, run it as root for the initial check; for a persistent service,
configure the service user with access to the GPIO device and ALSA MIDI.

To verify the MIDI output, list ALSA sequencer ports and watch the bridge port:

```sh
aconnect -l
aseqdump -l
```

Use the port shown for `Lezart-Boutons` with `aseqdump -p <client:port>`, then
press and release each button. Expect exactly one CC value 127 on press and one
value 0 on release after debounce.

## systemd

After the foreground test succeeds, a system service can run the installed
script. Adapt `User` and device permissions to the local Pi configuration:

```ini
[Unit]
Description=Pisound Micro GPIO to MIDI bridge
After=local-fs.target

[Service]
Type=simple
User=lezart
ExecStart=/usr/local/bin/pitcher-modep-buttons
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
```

Save as `/etc/systemd/system/pitcher-modep-buttons.service`, then enable and
start it:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now pitcher-modep-buttons.service
sudo systemctl status pitcher-modep-buttons.service
```

Only one process can request these GPIO lines. Do not run the Mapper and this
bridge together.

## Rollback

Stop and disable the bridge, then restore the Mapper:

```sh
sudo systemctl disable --now pitcher-modep-buttons.service
sudo systemctl enable --now pisound-micro-mapper.service
```

The bridge does not edit the Mapper configuration or the MODEP pedalboard.

## Current validation status

The code and its GPIO/MIDI configuration are documented here, but this
repository does not claim a successful physical-button test. Verify GPIO
ownership, the virtual ALSA MIDI port, all four CCs, and MODEP MIDI Learn on
the target Pi before relying on it.
