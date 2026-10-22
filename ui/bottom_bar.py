# ui/bottom_bar.py
import customtkinter as ctk
import tkinter as tk
from typing import Callable, Dict, Optional
from models.instrument_defs import midi_to_note_name, is_black_key

class BottomBar(ctk.CTkFrame):
    """
    Spodní panel s transportním ovládáním (Play, Pause, Stop, REC, BPM, Takty)
    a realistickou 2oktávovou klavírní klaviaturou (bílé a černé klávesy).
    """

    def __init__(
        self,
        parent,
        on_play: Callable[[], None],
        on_pause: Callable[[], None],
        on_stop: Callable[[], None],
        on_record_toggle: Callable[[bool], None],
        on_bpm_changed: Callable[[float], None],
        on_key_down: Callable[[int], None],
        on_key_up: Callable[[int], None],
        on_bars_changed: Optional[Callable[[int], None]] = None
    ):
        super().__init__(parent, height=96, corner_radius=0)
        self.pack_propagate(False)

        self.on_play = on_play
        self.on_pause = on_pause
        self.on_stop = on_stop
        self.on_record_toggle = on_record_toggle
        self.on_bpm_changed = on_bpm_changed
        self.on_key_down = on_key_down
        self.on_key_up = on_key_up
        self.on_bars_changed = on_bars_changed

        self.base_octave = 4  # Zobrazuje 2 oktávy: např. C4 až B5
        self.is_recording = False
        self._pressed_pitch: int = -1
        self._key_items: Dict[int, int] = {}

        self._build_ui()

    def _build_ui(self) -> None:
        # --- Levá část: Ovládání přehrávání a nahrávání ---
        transport_frame = ctk.CTkFrame(self, fg_color="transparent")
        transport_frame.pack(side="left", padx=10, pady=10)

        self.btn_play = ctk.CTkButton(
            transport_frame, text="▶ Přehrát", width=84, height=34,
            fg_color="#2FA572", font=("Segoe UI", 12, "bold"), command=self.on_play
        )
        self.btn_play.pack(side="left", padx=2)

        self.btn_pause = ctk.CTkButton(
            transport_frame, text="⏸ Pauza", width=74, height=34,
            fg_color="gray35", font=("Segoe UI", 12, "bold"), command=self.on_pause
        )
        self.btn_pause.pack(side="left", padx=2)

        self.btn_stop = ctk.CTkButton(
            transport_frame, text="⏹ Stop", width=68, height=34,
            fg_color="#D9534F", font=("Segoe UI", 12, "bold"), command=self.on_stop
        )
        self.btn_stop.pack(side="left", padx=2)

        self.btn_rec = ctk.CTkButton(
            transport_frame, text="● REC", width=80, height=34,
            fg_color="gray30", font=("Segoe UI", 12, "bold"), command=self._toggle_rec
        )
        self.btn_rec.pack(side="left", padx=4)

        # Časovač
        self.lbl_time = ctk.CTkLabel(
            transport_frame, text="00:00:000",
            font=("Consolas", 14, "bold"), width=82
        )
        self.lbl_time.pack(side="left", padx=6)

        # BPM
        ctk.CTkLabel(transport_frame, text="BPM:", font=("Segoe UI", 11)).pack(side="left", padx=(4, 2))
        self.entry_bpm = ctk.CTkEntry(transport_frame, width=48, height=28)
        self.entry_bpm.insert(0, "120")
        self.entry_bpm.pack(side="left", padx=2)
        self.entry_bpm.bind("<Return>", self._submit_bpm)
        self.entry_bpm.bind("<FocusOut>", self._submit_bpm)

        # Délka stopy v taktech (Takty)
        ctk.CTkLabel(transport_frame, text="Takty:", font=("Segoe UI", 11)).pack(side="left", padx=(8, 2))
        self.entry_bars = ctk.CTkEntry(transport_frame, width=42, height=28)
        self.entry_bars.insert(0, "8")
        self.entry_bars.pack(side="left", padx=2)
        self.entry_bars.bind("<Return>", self._submit_bars)
        self.entry_bars.bind("<FocusOut>", self._submit_bars)

        # --- Pravá část: Realistická klavírní klaviatura (2 oktávy) ---
        piano_container = ctk.CTkFrame(self, fg_color="transparent")
        piano_container.pack(side="right", padx=10, pady=6)

        oct_frame = ctk.CTkFrame(piano_container, fg_color="transparent")
        oct_frame.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(oct_frame, text="Oktáva klavíru:", font=("Segoe UI", 11)).pack(pady=(0, 2))
        btn_row = ctk.CTkFrame(oct_frame, fg_color="transparent")
        btn_row.pack()
        ctk.CTkButton(btn_row, text="◄", width=26, height=26, command=lambda: self._shift_octave(-1)).pack(side="left", padx=2)
        self.lbl_octave = ctk.CTkLabel(btn_row, text="C4–B5", font=("Segoe UI", 11, "bold"), width=46)
        self.lbl_octave.pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="►", width=26, height=26, command=lambda: self._shift_octave(1)).pack(side="left", padx=2)

        self.white_w = 32
        self.white_h = 76
        self.black_w = 20
        self.black_h = 46
        canvas_w = 14 * self.white_w + 2

        self.piano_canvas = tk.Canvas(
            piano_container,
            width=canvas_w,
            height=self.white_h,
            bg="#181818",
            highlightthickness=1,
            highlightbackground="#444444"
        )
        self.piano_canvas.pack(side="right")

        self.piano_canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.piano_canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        self._draw_piano_keys()

    def _draw_piano_keys(self) -> None:
        self.piano_canvas.delete("all")
        self._key_items.clear()

        start_pitch = (self.base_octave + 1) * 12
        pitches = [start_pitch + i for i in range(24) if 0 <= start_pitch + i <= 127]

        white_index = 0
        pitch_to_white_x: Dict[int, int] = {}

        for p in pitches:
            if not is_black_key(p):
                x1 = white_index * self.white_w
                x2 = x1 + self.white_w
                rect = self.piano_canvas.create_rectangle(
                    x1, 0, x2, self.white_h,
                    fill="#F5F5F5", outline="#333333", width=1,
                    tags=(f"pitch_{p}", "white")
                )
                self.piano_canvas.create_text(
                    (x1 + x2) / 2, self.white_h - 12,
                    text=midi_to_note_name(p),
                    fill="#222222", font=("Segoe UI", 8, "bold"),
                    state="disabled"
                )
                self._key_items[p] = rect
                pitch_to_white_x[p] = x1
                white_index += 1

        for p in pitches:
            if is_black_key(p):
                prev_white_x = pitch_to_white_x.get(p - 1, 0)
                x1 = prev_white_x + self.white_w - (self.black_w // 2)
                x2 = x1 + self.black_w
                rect = self.piano_canvas.create_rectangle(
                    x1, 0, x2, self.black_h,
                    fill="#202020", outline="#000000", width=1,
                    tags=(f"pitch_{p}", "black")
                )
                self._key_items[p] = rect

    def _get_pitch_at_xy(self, x: int, y: int) -> int:
        items = self.piano_canvas.find_overlapping(x, y, x, y)
        for item in reversed(items):
            tags = self.piano_canvas.gettags(item)
            for t in tags:
                if t.startswith("pitch_"):
                    return int(t.split("_")[1])
        return -1

    def _on_mouse_down(self, event) -> None:
        pitch = self._get_pitch_at_xy(event.x, event.y)
        if pitch != -1:
            self._pressed_pitch = pitch
            self.highlight_key(pitch, True)
            self.on_key_down(pitch)

    def _on_mouse_up(self, event) -> None:
        if self._pressed_pitch != -1:
            pitch = self._pressed_pitch
            self._pressed_pitch = -1
            self.highlight_key(pitch, False)
            self.on_key_up(pitch)

    def highlight_key(self, pitch: int, pressed: bool) -> None:
        rect = self._key_items.get(pitch)
        if not rect:
            return
        if pressed:
            self.piano_canvas.itemconfig(rect, fill="#3B8ED0")
        else:
            default_col = "#202020" if is_black_key(pitch) else "#F5F5F5"
            self.piano_canvas.itemconfig(rect, fill=default_col)

    def _toggle_rec(self) -> None:
        self.set_recording_state(not self.is_recording)
        self.on_record_toggle(self.is_recording)

    def set_recording_state(self, rec_active: bool) -> None:
        self.is_recording = rec_active
        if self.is_recording:
            self.btn_rec.configure(fg_color="#D9534F", text="● REC (Běží)")
        else:
            self.btn_rec.configure(fg_color="gray30", text="● REC")

    def _submit_bpm(self, event=None) -> None:
        try:
            val = float(self.entry_bpm.get())
            if 20 <= val <= 300:
                self.on_bpm_changed(val)
        except ValueError:
            pass

    def _submit_bars(self, event=None) -> None:
        try:
            bars = int(self.entry_bars.get())
            if 1 <= bars <= 200 and self.on_bars_changed:
                self.on_bars_changed(bars)
        except ValueError:
            pass

    def set_bpm_display(self, bpm: float) -> None:
        self.entry_bpm.delete(0, "end")
        self.entry_bpm.insert(0, str(int(bpm)))

    def _shift_octave(self, delta: int) -> None:
        self.base_octave = max(1, min(6, self.base_octave + delta))
        self.lbl_octave.configure(text=f"C{self.base_octave}–B{self.base_octave+1}")
        self._draw_piano_keys()

    def update_time_display(self, time_str: str) -> None:
        self.lbl_time.configure(text=time_str)