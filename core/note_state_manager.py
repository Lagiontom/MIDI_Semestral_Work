# core/note_state_manager.py
import threading
from typing import Dict, Tuple, Optional, List
from models.instrument_defs import INSTRUMENTS
from models.note_event import FIXED_VELOCITY


class NoteStateManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._active_notes: Dict[Tuple[int, int], int] = {}

    def process_note_on(
        self,
        instrument_id: str,
        pitch: int,
        channel_override: Optional[int] = None
    ) -> Optional[bytes]:
        spec = INSTRUMENTS.get(instrument_id)
        if spec and spec.id_name == "NONE":
            return None

        # Povolíme celý MIDI rozsah 0..127 (noty mimo rozsah nástroje se pouze barví červeně v UI,
        # ale do převodníku se odešlou vždy!)
        if not (0 <= pitch <= 127):
            return None

        default_ch = spec.default_channel if spec else 0
        channel = (channel_override if channel_override is not None else default_ch) & 0x0F
        key = (channel, pitch)

        with self._lock:
            current_count = self._active_notes.get(key, 0)
            self._active_notes[key] = current_count + 1

            if spec and spec.mode == "ON_OFF" and current_count > 0:
                return None

            status_byte = 0x90 | channel
            return bytes([status_byte, pitch & 0x7F, FIXED_VELOCITY])

    def process_note_off(
        self,
        instrument_id: str,
        pitch: int,
        channel_override: Optional[int] = None,
        force: bool = False
    ) -> Optional[bytes]:
        spec = INSTRUMENTS.get(instrument_id)
        if spec and spec.id_name == "NONE":
            return None

        if not (0 <= pitch <= 127):
            return None

        default_ch = spec.default_channel if spec else 0
        channel = (channel_override if channel_override is not None else default_ch) & 0x0F
        key = (channel, pitch)

        with self._lock:
            current_count = self._active_notes.get(key, 0)
            if current_count <= 0 and not force:
                # I když nebyla v registru, pošleme jistící Note Off
                status_byte = 0x80 | channel
                return bytes([status_byte, pitch & 0x7F, 0x00])

            if force or current_count <= 1:
                self._active_notes.pop(key, None)
                status_byte = 0x80 | channel
                return bytes([status_byte, pitch & 0x7F, 0x00])
            else:
                self._active_notes[key] = current_count - 1
                return None

    def panic_all_off(self) -> List[bytes]:
        messages: List[bytes] = []
        with self._lock:
            for (channel, pitch) in list(self._active_notes.keys()):
                status_byte = 0x80 | (channel & 0x0F)
                messages.append(bytes([status_byte, pitch & 0x7F, 0x00]))
            self._active_notes.clear()
        return messages