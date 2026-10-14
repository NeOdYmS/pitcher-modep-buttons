#!/usr/bin/env python3
"""Read Pisound Micro buttons and send MIDI CCs to MODEP."""

import glob
import os
import signal
import time

import gpiod
import rtmidi
from gpiod.line import Bias, Direction, Value


BUTTONS = (("B03", 20), ("B05", 21), ("B07", 22), ("B09", 23))
CHANNEL = 0
DEBOUNCE_SECONDS = 0.025
POLL_SECONDS = 0.005


class Button:
    def __init__(self, pressed):
        self.stable = pressed
        self.candidate = pressed
        self.changed_at = time.monotonic()

    def update(self, pressed, now):
        if pressed != self.candidate:
            self.candidate = pressed
            self.changed_at = now
        if self.candidate == self.stable or now - self.changed_at < DEBOUNCE_SECONDS:
            return None
        self.stable = self.candidate
        return self.stable


def find_button_chip():
    names = {name for name, _ in BUTTONS}
    for path in sorted(glob.glob("/dev/gpiochip[0-9]*")):
        chip = gpiod.Chip(path)
        try:
            offsets = {
                chip.get_line_info(offset).name: offset
                for offset in range(chip.get_info().num_lines)
            }
        finally:
            chip.close()
        if names.issubset(offsets):
            return path, {name: offsets[name] for name, _ in BUTTONS}
    raise RuntimeError("GPIO lines B03/B05/B07/B09 were not found.")


def main():
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    chip_path, button_offsets = find_button_chip()
    offsets = [button_offsets[name] for name, _ in BUTTONS]
    config = {
        offset: gpiod.LineSettings(
            direction=Direction.INPUT,
            bias=Bias.PULL_UP,
            active_low=True,
        )
        for offset in offsets
    }
    gpio = gpiod.request_lines(
        chip_path,
        consumer="Lezart-Boutons",
        config=config,
    )
    midi = None
    midi_open = False
    try:
        midi = rtmidi.MidiOut(rtmidi.API_LINUX_ALSA, "Lezart-Boutons")
        destination = os.environ.get("MIDI_OUTPUT_PORT")
        destination_port = None
        if destination:
            matches = [
                (index, port)
                for index, port in enumerate(midi.get_ports())
                if port.rsplit(" ", 1)[0] == destination
            ]
            if len(matches) != 1:
                raise RuntimeError(
                    f"Expected one MIDI destination {destination!r}, found {len(matches)}."
                )
            index, destination_port = matches[0]
            midi.open_port(index, "Lezart-Boutons")
        else:
            midi.open_virtual_port("Lezart-Boutons")
        midi_open = True
        next_port_check = time.monotonic() + 1
        buttons = [
            Button(value == Value.ACTIVE)
            for value in gpio.get_values(offsets)
        ]
        print(
            f"GPIO {chip_path}; MIDI channel 1; CC20-23 ready. "
            "Press sends 127, release sends 0.",
            flush=True,
        )

        while running:
            now = time.monotonic()
            if destination_port is not None and now >= next_port_check:
                if destination_port not in midi.get_ports():
                    raise RuntimeError(f"MIDI destination disconnected: {destination!r}")
                next_port_check = now + 1
            values = gpio.get_values(offsets)
            for index, ((name, cc), value) in enumerate(zip(BUTTONS, values)):
                pressed = buttons[index].update(value == Value.ACTIVE, now)
                if pressed is None:
                    continue
                midi_value = 127 if pressed else 0
                midi.send_message([0xB0 | CHANNEL, cc, midi_value])
                edge = "press" if pressed else "release"
                print(f"{name} CC{cc}={midi_value} ({edge})", flush=True)
            time.sleep(POLL_SECONDS)
        print("Button MIDI bridge stopped.", flush=True)
    finally:
        gpio.release()
        if midi is not None:
            if midi_open:
                midi.close_port()
            midi.delete()


if __name__ == "__main__":
    main()
