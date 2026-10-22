# core/midi_parser.py
import os
import mido
from typing import List, Tuple, Dict
from models.note_event import NoteEvent, TrackData, FIXED_VELOCITY

class MidiFileParser:
    """
    Načítá standardní .mid soubory do interní struktury TrackData
    a umožňuje zpětný export do .mid s fixovanou velocity 127.
    """

    @staticmethod
    def load_midi_file(filepath: str) -> Tuple[List[TrackData], float, int]:
        """
        Načte .mid soubor a vrátí: (seznam_stop, bpm, ticks_per_beat).
        """
        mid = mido.MidiFile(filepath)
        ticks_per_beat = mid.ticks_per_beat or 480
        bpm = 120.0
        tracks_out: List[TrackData] = []

        for idx, midi_track in enumerate(mid.tracks):
            abs_tick = 0
            # Mapa otevřených not: (channel, pitch) -> seznam start_ticků
            open_notes: Dict[Tuple[int, int], List[int]] = {}
            notes: List[NoteEvent] = []
            track_name = midi_track.name.strip() if midi_track.name else f"CH{idx+1:02d}"

            for msg in midi_track:
                abs_tick += msg.time

                if msg.type == "set_tempo":
                    bpm = round(mido.tempo2bpm(msg.tempo), 1)

                elif msg.type == "note_on" and msg.velocity > 0:
                    key = (getattr(msg, "channel", 0), msg.note)
                    open_notes.setdefault(key, []).append(abs_tick)

                elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                    key = (getattr(msg, "channel", 0), msg.note)
                    if key in open_notes and open_notes[key]:
                        start_t = open_notes[key].pop(0)
                        duration = max(1, abs_tick - start_t)
                        notes.append(
                            NoteEvent(
                                pitch=msg.note,
                                start_tick=start_t,
                                duration_tick=duration,
                                velocity=FIXED_VELOCITY
                            )
                        )

            # Uzavření případných neukončených not na konci stopy
            for (_, pitch), starts in open_notes.items():
                for st in starts:
                    notes.append(
                        NoteEvent(
                            pitch=pitch,
                            start_tick=st,
                            duration_tick=ticks_per_beat // 2,
                            velocity=FIXED_VELOCITY
                        )
                    )

            if notes:
                notes.sort(key=lambda n: (n.start_tick, n.pitch))
                # První stopu s notami defaultně nasměrujeme na Foukací harmoniku
                default_inst = "MELODICA" if len(tracks_out) == 0 else "METALLOPHONE"
                t_data = TrackData(
                    name=f"CH{len(tracks_out)+1:02d} {track_name}",
                    instrument_id=default_inst,
                    notes=notes
                )
                t_data.validate_notes()
                tracks_out.append(t_data)

        # Pokud byl soubor prázdný, vytvoříme alespoň jednu čistou stopu
        if not tracks_out:
            base_name = os.path.splitext(os.path.basename(filepath))[0]
            tracks_out.append(TrackData(name=f"CH01 {base_name}", instrument_id="MELODICA"))

        return tracks_out, bpm, ticks_per_beat

    @staticmethod
    def export_midi_file(filepath: str, tracks: List[TrackData], bpm: float, ticks_per_beat: int = 480) -> None:
        """
        Vyexportuje aktivní stopy do standardního .mid souboru (všechny noty s velocity 127).
        """
        mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)

        # Meta stopa pro tempo
        meta_track = mido.MidiTrack()
        meta_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
        mid.tracks.append(meta_track)

        for track in tracks:
            if track.muted or track.instrument_id == "NONE":
                continue

            m_track = mido.MidiTrack()
            m_track.append(mido.MetaMessage("track_name", name=track.name, time=0))
            ch = track.midi_channel & 0x0F

            # Rozložení NoteEvent na bodové události (tick, typ, pitch)
            events = []
            for note in track.notes:
                events.append((note.start_tick, 1, note.pitch))  # 1 = Note On
                events.append((note.end_tick, 0, note.pitch))    # 0 = Note Off

            # Seřazení: nejprve podle času, při shodě času nejprve Note Off (0) před Note On (1)
            events.sort(key=lambda e: (e[0], e[1]))

            last_tick = 0
            for tick, ev_type, pitch in events:
                delta = max(0, tick - last_tick)
                last_tick = tick
                if ev_type == 1:
                    m_track.append(mido.Message("note_on", channel=ch, note=pitch, velocity=FIXED_VELOCITY, time=delta))
                else:
                    m_track.append(mido.Message("note_off", channel=ch, note=pitch, velocity=0, time=delta))

            mid.tracks.append(m_track)

        mid.save(filepath)