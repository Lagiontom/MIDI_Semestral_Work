# core/sequencer.py
import time
import threading
from typing import List, Callable, Set, Tuple
from models.note_event import TrackData
from core.track_router import TrackRouter

class RealtimeSequencer:
    """
    Real-time sekvencér běžící v samostatném vlákně.
    Neposílá čáru z cizího vlákna přímo do Tkinteru a přehraje celou nastavenou délku stopy.
    """

    def __init__(
        self,
        router: TrackRouter,
        on_tick_callback: Callable[[int], None],
        on_playback_finished: Callable[[], None]
    ):
        self.router = router
        self.on_tick_callback = on_tick_callback
        self.on_playback_finished = on_playback_finished

        self.bpm: float = 120.0
        self.ticks_per_beat: int = 480
        self.total_bars: int = 8  # Výchozí délka stopy = 8 taktů

        self.is_playing: bool = False
        self.is_paused: bool = False
        self.is_recording: bool = False
        self.current_tick: int = 0

        self._thread: threading.Thread = None
        self._stop_event = threading.Event()
        # Aktivně hrající noty: (track_index, id_noty, pitch, inst_id, channel)
        self._playing_notes: Set[Tuple[int, int, int, str, int]] = set()

    @property
    def max_ticks(self) -> int:
        """Celková délka stopy v MIDI ticích (1 takt = 4 doby)."""
        return self.total_bars * 4 * self.ticks_per_beat

    def set_total_bars(self, bars: int) -> None:
        self.total_bars = max(1, min(200, int(bars)))

    def start(self, tracks: List[TrackData], record_mode: bool = False) -> None:
        if self.is_playing and not self.is_paused:
            return

        self.is_recording = record_mode
        if self.is_paused:
            self.is_paused = False
            return

        self.is_playing = True
        self.is_paused = False
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run_loop,
            args=(tracks,),
            daemon=True
        )
        self._thread.start()

    def pause(self) -> None:
        if self.is_playing:
            self.is_paused = not self.is_paused
            if self.is_paused:
                self._release_active_notes()

    def stop(self) -> None:
        self.is_playing = False
        self.is_paused = False
        self.is_recording = False
        self._stop_event.set()
        self.current_tick = 0
        self._release_active_notes()
        self.router.panic_stop_all()

    def _release_active_notes(self) -> None:
        for _, _, pitch, inst_id, ch in list(self._playing_notes):
            try:
                self.router.trigger_note_off(inst_id, pitch, channel=ch)
            except Exception:
                pass
        self._playing_notes.clear()

    def _run_loop(self, tracks: List[TrackData]) -> None:
        last_time = time.perf_counter()

        # Zjistíme konec poslední noty, abychom případně přehráli i delší MIDI soubor
        last_note_tick = 0
        for t in tracks:
            for n in t.notes:
                if n.end_tick > last_note_tick:
                    last_note_tick = n.end_tick

        target_end_tick = max(self.max_ticks, last_note_tick)

        while not self._stop_event.is_set() and self.is_playing:
            now = time.perf_counter()
            dt = now - last_time
            last_time = now

            if self.is_paused:
                time.sleep(0.015)
                continue

            # Přepočet uplynulého času na MIDI ticky podle BPM
            ticks_per_sec = (self.bpm / 60.0) * self.ticks_per_beat
            delta_ticks = dt * ticks_per_sec
            self.current_tick += int(max(1, round(delta_ticks)))

            # Aktualizace konce, pokud uživatel v průběhu změnil počet taktů
            target_end_tick = max(self.max_ticks, last_note_tick)

            # Kontrola konce stopy (při nahrávání REC automaticky prodlužujeme, jinak zastavíme na konci)
            if not self.is_recording and self.current_tick >= target_end_tick:
                self.current_tick = target_end_tick
                try:
                    self.on_tick_callback(self.current_tick)
                except Exception:
                    pass
                self.is_playing = False
                self._release_active_notes()
                try:
                    self.on_playback_finished()
                except Exception:
                    pass
                break

            # Odbavení not v aktuálním ticku (chráněno proti výjimkám, aby čára nikdy nezamrzla)
            try:
                self._process_notes(tracks, self.current_tick)
            except Exception as e:
                print(f"[Sequencer] Chyba při zpracování not: {e}")

            # Posun žluté čáry v UI
            try:
                self.on_tick_callback(self.current_tick)
            except Exception:
                pass

            time.sleep(0.012)  # ~80 FPS pro plynulý pohyb čáry

    def _process_notes(self, tracks: List[TrackData], tick: int) -> None:
        still_playing: Set[Tuple[int, int, int, str, int]] = set()

        for t_idx, track in enumerate(tracks):
            if not self.router.is_track_audible(track, tracks):
                continue

            inst_id = track.instrument_id
            ch = track.midi_channel

            for note in track.notes:
                if note.start_tick <= tick < note.end_tick:
                    key = (t_idx, id(note), note.pitch, inst_id, ch)
                    still_playing.add(key)
                    if key not in self._playing_notes:
                        self._playing_notes.add(key)
                        self.router.trigger_note_on(inst_id, note.pitch, channel=ch)

        # Vypnutí not, které v tomto kroku dozněly
        ended = self._playing_notes - still_playing
        for key in ended:
            _, _, pitch, inst_id, ch = key
            self.router.trigger_note_off(inst_id, pitch, channel=ch)
            self._playing_notes.discard(key)

    def ticks_to_time_str(self, tick: int) -> str:
        ticks_per_sec = (self.bpm / 60.0) * self.ticks_per_beat
        if ticks_per_sec <= 0:
            return "00:00:000"
        total_sec = tick / ticks_per_sec
        mins = int(total_sec // 60)
        secs = int(total_sec % 60)
        ms = int((total_sec - int(total_sec)) * 1000)
        return f"{mins:02d}:{secs:02d}:{ms:03d}"