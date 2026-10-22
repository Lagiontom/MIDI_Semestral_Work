# models/instrument_defs.py
from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass(frozen=True)
class InstrumentSpec:
    id_name: str
    display_name: str
    min_pitch: int          # Nejnižší hratelná MIDI nota
    max_pitch: int          # Nejvyšší hratelná MIDI nota
    default_channel: int    # Výchozí MIDI kanál (0-15 v mido = kanál 1-16)
    mode: str               # "ON_OFF" (harmonika/flétna) nebo "DURATION" (metalofon)
    color: str              # Barva not v Piano Rollu (Hex)

# Definice cílových mechatronických nástrojů
INSTRUMENTS: Dict[str, InstrumentSpec] = {
    "MELODICA": InstrumentSpec(
        id_name="MELODICA",
        display_name="Foukací harmonika (32 kl.)",
        min_pitch=53,       # F3 (MIDI 53)
        max_pitch=84,       # C6 (MIDI 84) -> celkem přesně 32 kláves
        default_channel=0,  # MIDI Kanál 1
        mode="ON_OFF",      # Solenoid drží klávesu po celou dobu trvání noty
        color="#3B8ED0"     # Modrá
    ),
    "METALLOPHONE": InstrumentSpec(
        id_name="METALLOPHONE",
        display_name="Metalofon",
        min_pitch=60,       # C4 (lze upravit dle osazených kamenů)
        max_pitch=84,       # C6 (2 oktávy)
        default_channel=1,  # MIDI Kanál 2
        mode="DURATION",    # Krátký úder kladívka s pružinou
        color="#2FA572"     # Zelená
    ),
    "PAN_FLUTE": InstrumentSpec(
        id_name="PAN_FLUTE",
        display_name="Panova flétna",
        min_pitch=60,       # C4
        max_pitch=83,       # B5
        default_channel=2,  # MIDI Kanál 3
        mode="ON_OFF",      # Ventily drží přívod vzduchu po dobu noty
        color="#E0A82E"     # Žlutá/Oranžová
    ),
    "NONE": InstrumentSpec(
        id_name="NONE",
        display_name="Nepřiřazeno (Mute)",
        min_pitch=0,
        max_pitch=127,
        default_channel=15,
        mode="NONE",
        color="#6E6E6E"     # Šedá
    )
}

# Předdefinované intervaly pro nástroj "Akordové razítko" (v půltónech od základního tónu)
CHORD_TEMPLATES: Dict[str, List[int]] = {
    "Jedna nota (Tužka)": [0],
    "Dur kvintakord (Major)": [0, 4, 7],
    "Moll kvintakord (Minor)": [0, 3, 7],
    "Septakord (Dom 7)": [0, 4, 7, 10],
    "Molový septakord (Min 7)": [0, 3, 7, 10],
    "Power akord (Kvinta)": [0, 7],
    "Oktáva": [0, 12]
}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def midi_to_note_name(pitch: int) -> str:
    """Převede MIDI číslo noty (0-127) na textový název (např. 60 -> C4)."""
    if not (0 <= pitch <= 127):
        return "---"
    octave = (pitch // 12) - 1
    note = NOTE_NAMES[pitch % 12]
    return f"{note}{octave}"

def is_black_key(pitch: int) -> bool:
    """Vrátí True, pokud MIDI nota odpovídá černé klávese na klavíru."""
    return (pitch % 12) in (1, 3, 6, 8, 10)