#!/usr/bin/env python3
"""Read Pisound Micro buttons and send MIDI CCs to MODEP."""

import glob
import signal
import time

import gpiod
import rtmidi
from gpiod.line import Bias, Direction, Value


BUTTONS = (("B03", 20), ("B07", 21), ("B11", 22), ("B15", 23))
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
    raise RuntimeError("GPIO lines B03/B07/B11/B15 were not found.")


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
        midi.open_virtual_port("Lezart-Boutons")
        midi_open = True
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
