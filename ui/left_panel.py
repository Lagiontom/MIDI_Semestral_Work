# ui/left_panel.py
import os
import customtkinter as ctk
from tkinter import messagebox
from typing import List, Callable
from models.instrument_defs import INSTRUMENTS
from models.note_event import TrackData

class LeftPanel(ctk.CTkFrame):
    """
    Levý postranní panel:
    - Knihovna souborů (.mid / .mproj)
    - Správce stop: výběr nástroje, výběr MIDI kanálu (1-16), tlačítka Mute, Solo a Smazat (🗑) s potvrzením.
    """

    def __init__(
        self,
        parent,
        default_dir: str,
        on_file_selected: Callable[[str], None],
        on_track_selected: Callable[[int], None],
        on_track_changed: Callable[[], None],
        on_add_track: Callable[[], None],
        on_delete_track: Callable[[int], None]
    ):
        super().__init__(parent, width=300, corner_radius=0)
        self.pack_propagate(False)

        self.default_dir = default_dir
        self.on_file_selected = on_file_selected
        self.on_track_selected = on_track_selected
        self.on_track_changed = on_track_changed
        self.on_add_track = on_add_track
        self.on_delete_track = on_delete_track

        self._inst_display_to_id = {spec.display_name: k for k, spec in INSTRUMENTS.items()}
        self._build_ui()
        self.refresh_file_list(self.default_dir)

    def _build_ui(self) -> None:
        header_files = ctk.CTkFrame(self, fg_color="transparent")
        header_files.pack(fill="x", padx=10, pady=(8, 2))

        ctk.CTkLabel(header_files, text="📁 Knihovna (.mid / .mproj)", font=("Segoe UI", 13, "bold")).pack(side="left")
        ctk.CTkButton(
            header_files,
            text="↻",
            width=28,
            height=24,
            command=lambda: self.refresh_file_list(self.default_dir)
        ).pack(side="right")

        self.file_scroll = ctk.CTkScrollableFrame(self, height=130)
        self.file_scroll.pack(fill="x", padx=8, pady=4)

        sep = ctk.CTkFrame(self, height=2, fg_color="gray30")
        sep.pack(fill="x", padx=8, pady=4)

        header_tracks = ctk.CTkFrame(self, fg_color="transparent")
        header_tracks.pack(fill="x", padx=10, pady=(2, 4))

        ctk.CTkLabel(header_tracks, text="🎹 Stopy a kanály", font=("Segoe UI", 13, "bold")).pack(side="left")
        ctk.CTkButton(
            header_tracks,
            text="+ Nová stopa",
            width=90,
            height=24,
            fg_color="#2FA572",
            command=self.on_add_track
        ).pack(side="right")

        self.tracks_scroll = ctk.CTkScrollableFrame(self)
        self.tracks_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def refresh_file_list(self, folder_path: str) -> None:
        self.default_dir = folder_path
        for widget in self.file_scroll.winfo_children():
            widget.destroy()

        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)

        files = [
            f for f in sorted(os.listdir(folder_path))
            if f.lower().endswith((".mid", ".midi", ".mproj"))
        ]

        if not files:
            ctk.CTkLabel(
                self.file_scroll,
                text="Složka je prázdná.\nUložte sem .mid nebo .mproj",
                text_color="gray60",
                font=("Segoe UI", 11)
            ).pack(pady=10)
            return

        for fname in files:
            full_path = os.path.join(folder_path, fname)
            icon = "🎵" if fname.lower().endswith((".mid", ".midi")) else "🛠"
            btn = ctk.CTkButton(
                self.file_scroll,
                text=f"{icon}  {fname}",
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray80", "gray25"),
                height=24,
                command=lambda p=full_path: self.on_file_selected(p)
            )
            btn.pack(fill="x", pady=1)

    def render_tracks(self, tracks: List[TrackData], active_index: int) -> None:
        for widget in self.tracks_scroll.winfo_children():
            widget.destroy()

        inst_names = [spec.display_name for spec in INSTRUMENTS.values()]
        channel_options = [f"Kanál {ch}" for ch in range(1, 17)]

        for idx, track in enumerate(tracks):
            is_selected = (idx == active_index)
            spec = track.instrument

            card = ctk.CTkFrame(
                self.tracks_scroll,
                corner_radius=8,
                border_width=2 if is_selected else 1,
                border_color=spec.color if is_selected else "gray35"
            )
            card.pack(fill="x", pady=4, padx=2)

            # 1. Řádek: Výběr stopy + Tlačítko Smazat (🗑)
            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=6, pady=(6, 2))

            lbl_name = ctk.CTkButton(
                top_row,
                text=f"{track.name} ({len(track.notes)} not)",
                anchor="w",
                fg_color=spec.color if is_selected else "transparent",
                text_color="white" if is_selected else ("gray10", "gray95"),
                hover_color=spec.color,
                height=26,
                font=("Segoe UI", 12, "bold"),
                command=lambda i=idx: self.on_track_selected(i)
            )
            lbl_name.pack(side="left", fill="x", expand=True, padx=(0, 4))

            btn_del = ctk.CTkButton(
                top_row,
                text="🗑",
                width=28,
                height=24,
                fg_color="#8B2626",
                hover_color="#D9534F",
                command=lambda i=idx, t=track: self._confirm_delete(i, t.name)
            )
            btn_del.pack(side="right")

            # 2. Řádek: Mute (Ztlumit), Solo (Hrát jen tuto) a Výběr MIDI Kanálu 1-16
            mid_row = ctk.CTkFrame(card, fg_color="transparent")
            mid_row.pack(fill="x", padx=6, pady=2)

            btn_mute = ctk.CTkButton(
                mid_row,
                text="Mute (Ztlumit)" if track.muted else "Mute",
                width=65,
                height=22,
                font=("Segoe UI", 10, "bold"),
                fg_color="#D9534F" if track.muted else "gray35",
                command=lambda t=track: self._toggle_mute(t)
            )
            btn_mute.pack(side="left", padx=(0, 3))

            btn_solo = ctk.CTkButton(
                mid_row,
                text="Solo (Jen tato)" if track.solo else "Solo",
                width=65,
                height=22,
                font=("Segoe UI", 10, "bold"),
                fg_color="#E0A82E" if track.solo else "gray35",
                command=lambda t=track: self._toggle_solo(t)
            )
            btn_solo.pack(side="left", padx=2)

            ch_combo = ctk.CTkOptionMenu(
                mid_row,
                values=channel_options,
                width=95,
                height=22,
                font=("Segoe UI", 11),
                fg_color="gray25",
                command=lambda val, t=track: self._change_channel(t, val)
            )
            ch_combo.set(f"Kanál {track.midi_channel + 1}")
            ch_combo.pack(side="right")

            # 3. Řádek: Roletové menu pro výběr cílového nástroje
            bottom_row = ctk.CTkFrame(card, fg_color="transparent")
            bottom_row.pack(fill="x", padx=6, pady=(2, 6))

            inst_combo = ctk.CTkOptionMenu(
                bottom_row,
                values=inst_names,
                height=26,
                fg_color="gray25",
                button_color=spec.color,
                command=lambda val, t=track, i=idx: self._change_instrument(t, val, i)
            )
            inst_combo.set(spec.display_name)
            inst_combo.pack(fill="x")

    def _confirm_delete(self, idx: int, track_name: str) -> None:
        answer = messagebox.askyesno(
            "Smazat stopu",
            f"Opravdu chcete trvale smazat stopu '{track_name}'?"
        )
        if answer:
            self.on_delete_track(idx)

    def _toggle_mute(self, track: TrackData) -> None:
        track.muted = not track.muted
        self.on_track_changed()

    def _toggle_solo(self, track: TrackData) -> None:
        track.solo = not track.solo
        self.on_track_changed()

    def _change_channel(self, track: TrackData, val: str) -> None:
        try:
            ch_num = int(val.replace("Kanál", "").strip()) - 1
            track.custom_channel = max(0, min(15, ch_num))
            self.on_track_changed()
        except ValueError:
            pass

    def _change_instrument(self, track: TrackData, display_name: str, idx: int) -> None:
        inst_id = self._inst_display_to_id.get(display_name, "MELODICA")
        track.instrument_id = inst_id
        # Při změně nástroje nastavíme i jeho výchozí kanál
        track.custom_channel = INSTRUMENTS[inst_id].default_channel
        track.validate_notes()
        self.on_track_selected(idx)
        self.on_track_changed()