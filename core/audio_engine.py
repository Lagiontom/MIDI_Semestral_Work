# core/audio_engine.py
import ctypes
from ctypes import byref, c_void_p, c_uint


class AudioEngine:
    """
    Přehrává tóny na reproduktorech PC přes Windows Multimedia API (winmm.dll).
    Neblokuje externí USB-MIDI převodník pro knihovnu mido.
    """

    GM_INSTRUMENTS = {
        "MELODICA": 22,      # Harmonica
        "METALLOPHONE": 12,  # Marimba / Xylophone
        "PAN_FLUTE": 75,     # Pan Flute
        "NONE": 0            # Acoustic Grand Piano
    }

    def __init__(self):
        self.initialized = False
        self.player = None  # Zpětná kompatibilita
        self.enabled = True
        self.h_midi = c_void_p()
        self._winmm = None
        self._current_programs = {}
        self._init_midi()

    def _init_midi(self) -> None:
        try:
            self._winmm = ctypes.windll.winmm
            # Otevřeme přímo zařízení ID 0 (Microsoft GS Wavetable Synth),
            # NIKOLIV MIDI_MAPPER (0xFFFFFFFF), který ve Windows 11 vrací chybu 1 a blokuje USB-MIDI!
            res = self._winmm.midiOutOpen(byref(self.h_midi), c_uint(0), 0, 0, 0)
            if res == 0:
                self.initialized = True
                self._send_short_msg(0xC0, 0, 0)
            else:
                # Pokud je zařízení 0 obsazené (např. je to samotný USB-MIDI převodník),
                # necháme interní AudioEngine vypnutý, aby měl mido 100% volný přístup k převodníku!
                self.initialized = False
        except Exception:
            self.initialized = False

    def _send_short_msg(self, status: int, data1: int, data2: int = 0) -> None:
        if not (self.initialized and self._winmm and self.h_midi):
            return
        msg = (status & 0xFF) | ((data1 & 0x7F) << 8) | ((data2 & 0x7F) << 16)
        self._winmm.midiOutShortMsg(self.h_midi, c_uint(msg))

    def note_on(self, instrument_id: str, pitch: int, channel: int = 0, velocity: int = 127) -> None:
        if not (self.enabled and self.initialized):
            return
        try:
            ch = channel & 0x0F
            gm_prog = self.GM_INSTRUMENTS.get(instrument_id, 0)
            if self._current_programs.get(ch) != gm_prog:
                self._send_short_msg(0xC0 | ch, gm_prog, 0)
                self._current_programs[ch] = gm_prog
            self._send_short_msg(0x90 | ch, int(pitch) & 0x7F, int(velocity) & 0x7F)
        except Exception:
            pass

    def note_off(self, pitch: int, channel: int = 0) -> None:
        if not (self.enabled and self.initialized):
            return
        try:
            ch = channel & 0x0F
            self._send_short_msg(0x80 | ch, int(pitch) & 0x7F, 0)
        except Exception:
            pass

    def all_notes_off(self) -> None:
        if not self.initialized:
            return
        try:
            for ch in range(16):
                self._send_short_msg(0xB0 | ch, 123, 0)
        except Exception:
            pass

    def close(self) -> None:
        self.all_notes_off()
        if self.initialized and self._winmm and self.h_midi:
            try:
                self._winmm.midiOutReset(self.h_midi)
                self._winmm.midiOutClose(self.h_midi)
            except Exception:
                pass
            self.initialized = False