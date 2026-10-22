# models/note_event.py
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from models.instrument_defs import INSTRUMENTS, InstrumentSpec

FIXED_VELOCITY = 127

@dataclass
class NoteEvent:
    pitch: int
    start_tick: int
    duration_tick: int
    velocity: int = FIXED_VELOCITY
    is_valid_range: bool = True

    def __post_init__(self):
        self.velocity = FIXED_VELOCITY
        self.pitch = max(0, min(127, int(self.pitch)))
        self.start_tick = max(0, int(self.start_tick))
        self.duration_tick = max(1, int(self.duration_tick))

    @property
    def end_tick(self) -> int:
        return self.start_tick + self.duration_tick

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pitch": self.pitch,
            "start_tick": self.start_tick,
            "duration_tick": self.duration_tick,
            "velocity": FIXED_VELOCITY
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NoteEvent":
        return cls(
            pitch=data["pitch"],
            start_tick=data["start_tick"],
            duration_tick=data["duration_tick"],
            velocity=FIXED_VELOCITY
        )


@dataclass
class TrackData:
    name: str
    instrument_id: str = "MELODICA"
    custom_channel: Optional[int] = None  # 0-15 (odpovídá MIDI kanálu 1-16)
    muted: bool = False
    solo: bool = False
    notes: List[NoteEvent] = field(default_factory=list)

    def __post_init__(self):
        if self.custom_channel is None:
            self.custom_channel = self.instrument.default_channel

    @property
    def instrument(self) -> InstrumentSpec:
        return INSTRUMENTS.get(self.instrument_id, INSTRUMENTS["MELODICA"])

    @property
    def midi_channel(self) -> int:
        if self.custom_channel is not None:
            return self.custom_channel & 0x0F
        return self.instrument.default_channel & 0x0F

    def validate_notes(self) -> int:
        spec = self.instrument
        out_of_range_count = 0
        for note in self.notes:
            if spec.id_name == "NONE":
                note.is_valid_range = True
            else:
                in_range = (spec.min_pitch <= note.pitch <= spec.max_pitch)
                note.is_valid_range = in_range
                if not in_range:
                    out_of_range_count += 1
        return out_of_range_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "instrument_id": self.instrument_id,
            "custom_channel": self.midi_channel,
            "muted": self.muted,
            "solo": self.solo,
            "notes": [n.to_dict() for n in self.notes]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrackData":
        track = cls(
            name=data.get("name", "Track"),
            instrument_id=data.get("instrument_id", "MELODICA"),
            custom_channel=data.get("custom_channel", None),
            muted=data.get("muted", False),
            solo=data.get("solo", False),
            notes=[NoteEvent.from_dict(n) for n in data.get("notes", [])]
        )
        track.validate_notes()
        return track