# core/track_router.py
from typing import List, Dict, Optional
from models.note_event import NoteEvent, TrackData, FIXED_VELOCITY
from core.note_state_manager import NoteStateManager
from hardware.serial_manager import SerialHardwareManager
from core.audio_engine import AudioEngine

class TrackRouter:
    def __init__(
        self,
        state_manager: NoteStateManager,
        serial_manager: SerialHardwareManager,
        audio_engine: Optional[AudioEngine] = None
    ):
        self.state_manager = state_manager
        self.serial_manager = serial_manager
        self.audio_engine = audio_engine
        self._recording_notes: Dict[int, int] = {}

    def is_track_audible(self, track: TrackData, all_tracks: List[TrackData]) -> bool:
        if track.instrument_id == "NONE" or track.muted:
            return False
        any_solo = any(t.solo for t in all_tracks)
        if any_solo and not track.solo:
            return False
        return True

    def trigger_note_on(
        self,
        instrument_id: str,
        pitch: int,
        channel: Optional[int] = None,
        is_recording: bool = False,
        current_tick: int = 0
    ) -> bool:
        if is_recording:
            self._recording_notes[pitch] = current_tick

        ch = (channel if channel is not None else 0) & 0x0F

        # 1. Přehrajeme tón v PC (AudioEngine)
        if self.audio_engine:
            self.audio_engine.note_on(instrument_id, pitch, ch, FIXED_VELOCITY)

        # 2. Odešleme na sériový port do STM32 (pokud je v rozsahu a není duplicitní)
        raw_bytes = self.state_manager.process_note_on(instrument_id, pitch, ch)
        if raw_bytes:
            self.serial_manager.send_raw_midi(raw_bytes)
        return raw_bytes is not None

    def trigger_note_off(
        self,
        instrument_id: str,
        pitch: int,
        channel: Optional[int] = None,
        is_recording: bool = False,
        current_tick: int = 0,
        active_track: Optional[TrackData] = None
    ) -> Optional[NoteEvent]:
        ch = (channel if channel is not None else 0) & 0x0F

        # 1. Vypneme tón v PC (AudioEngine)
        if self.audio_engine:
            self.audio_engine.note_off(pitch, ch)

        # 2. Odešleme Note Off do STM32
        raw_bytes = self.state_manager.process_note_off(instrument_id, pitch, ch)
        if raw_bytes:
            self.serial_manager.send_raw_midi(raw_bytes)

        created_note: Optional[NoteEvent] = None
        if is_recording and pitch in self._recording_notes:
            start_t = self._recording_notes.pop(pitch)
            duration = max(120, current_tick - start_t)
            if active_track is not None:
                spec = active_track.instrument
                in_range = True if spec.id_name == "NONE" else (spec.min_pitch <= pitch <= spec.max_pitch)
                created_note = NoteEvent(
                    pitch=pitch,
                    start_tick=start_t,
                    duration_tick=duration,
                    velocity=FIXED_VELOCITY,
                    is_valid_range=in_range
                )
                active_track.notes.append(created_note)
                active_track.notes.sort(key=lambda n: (n.start_tick, n.pitch))

        return created_note

    def panic_stop_all(self) -> None:
        self._recording_notes.clear()
        if self.audio_engine:
            self.audio_engine.all_notes_off()
        off_messages = self.state_manager.panic_all_off()
        self.serial_manager.send_batch(off_messages)