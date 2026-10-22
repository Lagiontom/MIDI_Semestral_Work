# core/validator.py
from typing import List, Tuple
from models.instrument_defs import INSTRUMENTS, CHORD_TEMPLATES
from models.note_event import NoteEvent, TrackData, FIXED_VELOCITY

class MidiValidator:
    """
    Zajišťuje validaci fyzického rozsahu (např. 32 kláves harmoniky),
    automatickou oktávovou transpozici (Auto-Correct) a generování akordů.
    """

    @staticmethod
    def validate_track(track: TrackData) -> int:
        """Označí noty mimo rozsah příznakem is_valid_range = False a vrátí jejich počet."""
        return track.validate_notes()

    @staticmethod
    def auto_correct_track(track: TrackData) -> Tuple[int, int]:
        """
        Posune všechny noty mimo rozsah o celé oktávy (+12 / -12 půltónů) tak,
        aby se vešly do fyzického rozsahu nástroje (např. 53..84 pro harmoniku).
        Vrací tuple: (počet_opravených_not, počet_stále_nevalidních_not).
        """
        spec = track.instrument
        if spec.id_name == "NONE":
            return (0, 0)

        min_p, max_p = spec.min_pitch, spec.max_pitch
        fixed_count = 0

        # 1. Globální optimální oktávový posun celé stopy (pokud je většina not mimo)
        if track.notes:
            avg_pitch = sum(n.pitch for n in track.notes) / len(track.notes)
            center_pitch = (min_p + max_p) / 2.0
            octave_shift = round((center_pitch - avg_pitch) / 12.0) * 12
        else:
            octave_shift = 0

        # 2. Individuální posun jednotlivých not po oktávách do cílového okna
        for note in track.notes:
            orig_pitch = note.pitch
            new_pitch = orig_pitch

            if not (min_p <= new_pitch <= max_p):
                # Zkusíme nejprve globální posun, pokud pomůže
                if min_p <= (new_pitch + octave_shift) <= max_p:
                    new_pitch += octave_shift
                else:
                    # Jinak posouváme po jednotlivých oktávách nahoru nebo dolů
                    while new_pitch < min_p and (new_pitch + 12) <= 127:
                        new_pitch += 12
                    while new_pitch > max_p and (new_pitch - 12) >= 0:
                        new_pitch -= 12

                # Oříznutí na nejbližší platnou oktávu, pokud by tón přeskočil úzký rozsah
                if new_pitch < min_p and (new_pitch + 12) <= max_p:
                    new_pitch += 12
                elif new_pitch > max_p and (new_pitch - 12) >= min_p:
                    new_pitch -= 12

                if new_pitch != orig_pitch:
                    note.pitch = new_pitch
                    fixed_count += 1

        # 3. Odstranění případných přesných duplicit vzniklých transpozicí
        unique_notes: List[NoteEvent] = []
        seen = set()
        for n in sorted(track.notes, key=lambda x: (x.start_tick, x.pitch)):
            key = (n.pitch, n.start_tick)
            if key not in seen:
                seen.add(key)
                unique_notes.append(n)
        track.notes = unique_notes

        remaining_invalid = track.validate_notes()
        return (fixed_count, remaining_invalid)

    @staticmethod
    def create_chord_notes(
        root_pitch: int,
        start_tick: int,
        duration_tick: int,
        chord_name: str,
        instrument_id: str = "MELODICA"
    ) -> List[NoteEvent]:
        """
        Vygeneruje skupinu not (akord) pro nástroj 'Akordové razítko'.
        Respektuje fixní velocity 127 a rovnou vyhodnotí platnost rozsahu.
        """
        intervals = CHORD_TEMPLATES.get(chord_name, [0])
        spec = INSTRUMENTS.get(instrument_id, INSTRUMENTS["MELODICA"])
        created: List[NoteEvent] = []

        for offset in intervals:
            pitch = root_pitch + offset
            if 0 <= pitch <= 127:
                in_range = True if spec.id_name == "NONE" else (spec.min_pitch <= pitch <= spec.max_pitch)
                created.append(
                    NoteEvent(
                        pitch=pitch,
                        start_tick=start_tick,
                        duration_tick=duration_tick,
                        velocity=FIXED_VELOCITY,
                        is_valid_range=in_range
                    )
                )
        return created