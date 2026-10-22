# ui/piano_roll.py
import customtkinter as ctk
import tkinter as tk
from typing import Callable, Optional
from models.instrument_defs import midi_to_note_name, is_black_key
from models.note_event import TrackData, NoteEvent
from core.validator import MidiValidator


class PianoRollCanvas(ctk.CTkFrame):
    """
    Plně posouvatelný Piano Roll s okamžitým vykreslováním not při kliknutí myší.
    """

    def __init__(
        self,
        parent,
        on_notes_modified: Callable[[], None],
        on_preview_note: Optional[Callable[[int], None]] = None
    ):
        super().__init__(parent, corner_radius=0)
        self.on_notes_modified = on_notes_modified
        self.on_preview_note = on_preview_note

        self.current_track: Optional[TrackData] = None
        self.current_tool = "DRAW"
        self.current_chord = "Jedna nota (Tužka)"
        self.snap_div = 8
        self.zoom_x = 0.35
        self.row_height = 20
        self.keys_width = 80
        self.total_rows = 128
        self.total_bars = 8

        self.current_tick = 0
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.keys_canvas = tk.Canvas(
            self,
            width=self.keys_width,
            bg="#202020",
            highlightthickness=0
        )
        self.keys_canvas.grid(row=0, column=0, sticky="ns")

        self.grid_canvas = tk.Canvas(
            self,
            bg="#181818",
            highlightthickness=0,
            cursor="cross"
        )
        self.grid_canvas.grid(row=0, column=1, sticky="nsew")

        self.v_scroll = ctk.CTkScrollbar(self, orientation="vertical", command=self._on_vscroll)
        self.v_scroll.grid(row=0, column=2, sticky="ns")

        self.h_scroll = ctk.CTkScrollbar(self, orientation="horizontal", command=self.grid_canvas.xview)
        self.h_scroll.grid(row=1, column=1, sticky="ew")

        self.grid_canvas.configure(
            yscrollcommand=self._on_mouse_yscroll,
            xscrollcommand=self.h_scroll.set
        )
        self.keys_canvas.configure(yscrollcommand=self._on_mouse_yscroll)

        # Události myši
        self.grid_canvas.bind("<ButtonPress-1>", self._on_grid_left_click)
        self.grid_canvas.bind("<ButtonPress-3>", self._on_grid_right_click)
        self.keys_canvas.bind("<ButtonPress-1>", self._on_key_click)

        self.grid_canvas.bind("<MouseWheel>", self._on_mousewheel_y)
        self.keys_canvas.bind("<MouseWheel>", self._on_mousewheel_y)
        self.grid_canvas.bind("<Shift-MouseWheel>", self._on_mousewheel_x)

    def _on_vscroll(self, *args) -> None:
        self.grid_canvas.yview(*args)
        self.keys_canvas.yview(*args)

    def _on_mouse_yscroll(self, first, last) -> None:
        self.v_scroll.set(first, last)
        self.keys_canvas.yview_moveto(first)

    def _on_mousewheel_y(self, event) -> None:
        delta = int(-1 * (event.delta / 120))
        self.grid_canvas.yview_scroll(delta * 3, "units")
        self.keys_canvas.yview_scroll(delta * 3, "units")

    def _on_mousewheel_x(self, event) -> None:
        delta = int(-1 * (event.delta / 120))
        self.grid_canvas.xview_scroll(delta * 5, "units")

    def set_total_bars(self, bars: int) -> None:
        self.total_bars = max(1, min(200, int(bars)))
        self.redraw()

    def set_track(self, track: Optional[TrackData], auto_scroll: bool = True) -> None:
        self.current_track = track
        self.redraw()
        if auto_scroll and track is not None:
            self.after(30, self.scroll_to_instrument_range)

    def scroll_to_instrument_range(self) -> None:
        if not self.current_track:
            return
        spec = self.current_track.instrument
        if spec.id_name == "NONE":
            center_pitch = 68
        else:
            center_pitch = (spec.min_pitch + spec.max_pitch) // 2

        total_height = self.total_rows * self.row_height
        target_y = (127 - center_pitch) * self.row_height
        canvas_h = max(300, self.grid_canvas.winfo_height())

        fraction = max(0.0, min(1.0, (target_y - canvas_h / 2) / total_height))
        self.grid_canvas.yview_moveto(fraction)
        self.keys_canvas.yview_moveto(fraction)

    def set_tool_params(self, tool: str, chord_name: str, snap_div: int) -> None:
        # Normalizace názvu nástroje (kdyby přišlo cokoliv jiného než ERASE, kreslíme)
        if "ERASE" in str(tool).upper() or "GUMA" in str(tool).upper():
            self.current_tool = "ERASE"
        else:
            self.current_tool = "DRAW"
        self.current_chord = chord_name
        old_snap = self.snap_div
        self.snap_div = max(1, int(snap_div))
        if old_snap != self.snap_div:
            self.redraw()
        else:
            self.redraw_notes()

    def set_playhead(self, tick: int) -> None:
        self.current_tick = tick
        self.redraw_playhead()

    def _draw_single_note_item(self, note: NoteEvent, spec) -> None:
        """Pomocná metoda, která nakreslí jeden obdélníček noty s tagem 'note_block'."""
        x1 = note.start_tick * self.zoom_x
        x2 = note.end_tick * self.zoom_x
        y1 = (127 - note.pitch) * self.row_height
        y2 = y1 + self.row_height

        fill_col = spec.color if note.is_valid_range else "#D9534F"
        outline_col = "#FFFFFF" if not note.is_valid_range else "#101010"

        self.grid_canvas.create_rectangle(
            x1, y1 + 1, max(x1 + 6, x2), y2 - 1,
            fill=fill_col, outline=outline_col, width=1, tags=("note_block",)
        )
        self.grid_canvas.create_text(
            x1 + 4, y1 + self.row_height / 2,
            text=midi_to_note_name(note.pitch),
            anchor="w", fill="white", font=("Segoe UI", 8, "bold"), tags=("note_block",)
        )

    def redraw_notes(self) -> None:
        """Smaže a okamžitě znovu vykreslí pouze obdélníčky not (bez sahání na pozadí mřížky)."""
        self.grid_canvas.delete("note_block")
        if not self.current_track:
            return
        spec = self.current_track.instrument
        for note in self.current_track.notes:
            self._draw_single_note_item(note, spec)
        self.redraw_playhead()
        self.grid_canvas.update_idletasks()

    def redraw(self) -> None:
        self.grid_canvas.delete("all")
        self.keys_canvas.delete("all")
        if not self.current_track:
            return

        spec = self.current_track.instrument
        total_height = self.total_rows * self.row_height

        ticks_per_beat = 480
        bar_ticks = ticks_per_beat * 4
        configured_ticks = self.total_bars * bar_ticks

        max_note_tick = max([n.end_tick for n in self.current_track.notes], default=0)
        max_ticks = max(configured_ticks, max_note_tick + bar_ticks)
        total_width = int(max_ticks * self.zoom_x)

        self.grid_canvas.configure(scrollregion=(0, 0, total_width, total_height))
        self.keys_canvas.configure(scrollregion=(0, 0, self.keys_width, total_height))

        # 1. Řádky a vertikální klaviatura
        for pitch in range(127, -1, -1):
            y = (127 - pitch) * self.row_height
            is_black = is_black_key(pitch)
            in_range = (spec.min_pitch <= pitch <= spec.max_pitch) if spec.id_name != "NONE" else True

            if in_range:
                row_bg = "#283038" if is_black else "#323C46"
                key_bg = "#222222" if is_black else "#F0F0F0"
                key_fg = "#FFFFFF" if is_black else "#111111"
            else:
                row_bg = "#141414" if is_black else "#1A1A1A"
                key_bg = "#2A2A2A" if is_black else "#454545"
                key_fg = "#777777"

            self.grid_canvas.create_rectangle(
                0, y, total_width, y + self.row_height,
                fill=row_bg, outline="#222222", tags=("bg_grid",)
            )
            self.keys_canvas.create_rectangle(
                0, y, self.keys_width, y + self.row_height,
                fill=key_bg, outline="#555555"
            )

            if in_range and spec.id_name != "NONE":
                self.keys_canvas.create_rectangle(
                    self.keys_width - 6, y, self.keys_width, y + self.row_height,
                    fill=spec.color, outline=""
                )

            note_str = midi_to_note_name(pitch)
            self.keys_canvas.create_text(
                8, y + self.row_height / 2,
                text=note_str, anchor="w", fill=key_fg,
                font=("Segoe UI", 9, "bold" if pitch % 12 == 0 or in_range else "normal")
            )

        # 2. Svislé taktové a mřížkové čáry
        step_tick = max(60, int(ticks_per_beat * (4 / self.snap_div)))
        grid_step = min(ticks_per_beat, step_tick)

        for t in range(0, max_ticks + 1, grid_step):
            x = t * self.zoom_x
            if t % bar_ticks == 0:
                self.grid_canvas.create_line(x, 0, x, total_height, fill="#555555", width=1, tags=("bg_grid",))
                bar_num = (t // bar_ticks) + 1
                self.grid_canvas.create_text(
                    x + 4, 10, text=f"Takt {bar_num}",
                    anchor="nw", fill="#AAAAAA", font=("Segoe UI", 8, "bold"), tags=("bg_grid",)
                )
            elif t % ticks_per_beat == 0:
                self.grid_canvas.create_line(x, 0, x, total_height, fill="#383838", tags=("bg_grid",))
            else:
                self.grid_canvas.create_line(x, 0, x, total_height, fill="#252525", tags=("bg_grid",))

        # 3. Noty a Playhead
        self.redraw_notes()

    def redraw_playhead(self) -> None:
        self.grid_canvas.delete("playhead")
        x = self.current_tick * self.zoom_x
        total_height = self.total_rows * self.row_height
        self.grid_canvas.create_line(x, 0, x, total_height, fill="#FFCC00", width=2, tags=("playhead",))

    def _on_key_click(self, event) -> None:
        canvas_y = self.keys_canvas.canvasy(event.y)
        pitch = 127 - int(canvas_y // self.row_height)
        if 0 <= pitch <= 127 and self.on_preview_note:
            self.on_preview_note(pitch)

    def _on_grid_left_click(self, event) -> None:
        if not self.current_track:
            return

        canvas_x = self.grid_canvas.canvasx(event.x)
        canvas_y = self.grid_canvas.canvasy(event.y)

        tick = max(0, int(canvas_x / self.zoom_x))
        pitch = 127 - int(canvas_y // self.row_height)
        if not (0 <= pitch <= 127):
            return

        ticks_per_beat = 480
        duration_step = max(60, int(ticks_per_beat * (4 / self.snap_div)))
        snap_step = min(ticks_per_beat, duration_step)
        quantized_tick = (tick // snap_step) * snap_step

        if self.current_tool == "ERASE":
            self._erase_at(quantized_tick, tick, pitch)
            return

        # Režim Kreslit / Akord
        existing = [
            n for n in self.current_track.notes
            if n.pitch == pitch and n.start_tick <= tick < n.end_tick
        ]
        if existing and self.current_chord == "Jedna nota (Tužka)":
            for ex in existing:
                self.current_track.notes.remove(ex)
            self.current_track.validate_notes()
            self.redraw_notes()
        else:
            new_notes = MidiValidator.create_chord_notes(
                root_pitch=pitch,
                start_tick=quantized_tick,
                duration_tick=duration_step,
                chord_name=self.current_chord,
                instrument_id=self.current_track.instrument_id
            )
            spec = self.current_track.instrument
            for nn in new_notes:
                if not any(n.pitch == nn.pitch and n.start_tick == nn.start_tick for n in self.current_track.notes):
                    self.current_track.notes.append(nn)
                    # OKAMŽITĚ vykreslíme obdélníček přímo na plátno!
                    self._draw_single_note_item(nn, spec)

            self.current_track.notes.sort(key=lambda n: (n.start_tick, n.pitch))
            self.current_track.validate_notes()
            self.redraw_notes()

            if self.on_preview_note:
                self.after(10, lambda p=pitch: self.on_preview_note(p))

        self.on_notes_modified()

    def _on_grid_right_click(self, event) -> None:
        if not self.current_track:
            return
        canvas_x = self.grid_canvas.canvasx(event.x)
        canvas_y = self.grid_canvas.canvasy(event.y)
        tick = max(0, int(canvas_x / self.zoom_x))
        pitch = 127 - int(canvas_y // self.row_height)
        self._erase_at(tick, tick, pitch)

    def _erase_at(self, quantized_tick: int, raw_tick: int, pitch: int) -> None:
        if not self.current_track:
            return
        before = len(self.current_track.notes)
        self.current_track.notes = [
            n for n in self.current_track.notes
            if not (n.pitch == pitch and (n.start_tick <= raw_tick <= n.end_tick or n.start_tick == quantized_tick))
        ]
        if len(self.current_track.notes) != before:
            self.current_track.validate_notes()
            self.redraw_notes()
            self.on_notes_modified()