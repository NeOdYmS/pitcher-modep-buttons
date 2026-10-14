# Pisound Micro GPIO-to-MIDI bridge

A small Raspberry Pi service that reads the four Pisound Micro buttons directly
through Linux GPIO and exposes them as MIDI CC messages for MODEP/MOD-UI MIDI
Learn. It does not depend on the Pisound Micro Mapper or on a particular
pedalboard.

## Hardware and mapping

The buttons use the GPIO lines named `B03`, `B05`, `B07`, and `B09`. Each line
is configured as an active-low input with a pull-up; the button is considered
pressed when its line is active.

| Button | MIDI message |
| --- | --- |
| B03 | Channel 1, CC20: 127 while pressed, 0 on release |
| B05 | Channel 1, CC21: 127 while pressed, 0 on release |
| B07 | Channel 1, CC22: 127 while pressed, 0 on release |
| B09 | Channel 1, CC23: 127 while pressed, 0 on release |

By default the bridge opens an ALSA virtual MIDI output named `Lezart-Boutons`.
MODEP filters out this software-only port. For MODEP MIDI Learn, use the
`amidithru` relay below, which JACK exposes as a physical MIDI port.

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

The supplied units use MODEP's existing `/usr/bin/amidithru` utility, also used
for TouchOSC and require systemd 249 or newer (`Upholds=`). Check that it is
installed. Adapt `User=lezart` and device
permissions in both units to the local Pi configuration, then install:

```sh
sudo install -m 0755 pitcher-modep-buttons.py /usr/local/bin/pitcher-modep-buttons
sudo install -m 0644 pitcher-modep-buttons.service pitcher-modep-midi.service /etc/systemd/system/
sudo systemctl disable --now pisound-micro-mapper.service
sudo systemctl daemon-reload
sudo systemctl enable --now pitcher-modep-midi.service pitcher-modep-buttons.service
sudo systemctl status pitcher-modep-midi.service pitcher-modep-buttons.service
```

`MIDI_OUTPUT_PORT=Lezart-Buttons-MODEP:Lezart-Buttons-MODEP` selects the relay
by its exact ALSA client/port name, without hard-coding a client number.
Unset this variable for standalone virtual-port mode. Missing or ambiguous
destinations fail explicitly; systemd retries startup. The bridge checks
the destination once per second and exits on disconnection so systemd can
reconnect it after a relay restart. `BindsTo=` stops the bridge when the relay
stops, and `Upholds=` starts it again once the relay is running. This also
reconnects fast restarts where ALSA reuses the same client number.
Stop both units together when intentionally stopping the buttons.

In MODEP aggregated MIDI mode, the relay should appear as
`Lezart Buttons MODEP MIDI 1 (in+out)` and connect automatically to
`mod-midi-merger:in`. JACK port numbers can change; check aliases rather than
assuming `system:midi_capture_N` remains constant. No periodic reboot or
pedalboard edit is required.

Only one process can request these GPIO lines. Do not run the Mapper and this
bridge together.

## Rollback

Stop and disable the bridge, then restore the Mapper:

```sh
sudo systemctl disable --now pitcher-modep-buttons.service pitcher-modep-midi.service
sudo systemctl enable --now pisound-micro-mapper.service
```

The bridge does not edit the Mapper configuration or the MODEP pedalboard.

## Current validation status

All four buttons (B03/CC20, B05/CC21, B07/CC22, B09/CC23) have produced
physical press/release messages in `aseqdump` on the target Pi, routed
through the `amidithru` relay and visible to MODEP. The original B11/B13/B15
wiring reproducibly failed to register any transition even with the bridge's
debounce disabled and with a direct, isolated GPIO read — pointing to a wiring
issue rather than a software bug. The button hardware itself tested fine with
a multimeter. Relay discovery and automatic merger routing have been observed
without restarting audio. End-to-end MIDI Learn still requires a
physical-button check in MODEP.
