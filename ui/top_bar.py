# ui/top_bar.py
import customtkinter as ctk
from typing import Callable
from models.instrument_defs import CHORD_TEMPLATES

# Mapování čitelných názvů délek not na dělitele taktu (1 takt = 4 doby)
NOTE_LENGTH_OPTIONS = {
    "1/1 (4 doby - Celá)": 1,
    "1/2 (2 doby - Půlová)": 2,
    "1/4 (1 doba - Čtvrťová)": 4,
    "1/8 (Osminová)": 8,
    "1/16 (Šestnáctinová)": 16,
}

class TopBar(ctk.CTkFrame):
    """
    Kompaktní horní panel nástrojů (Toolbar).
    Obsahuje volbu nástroje (Tužka/Guma), Akordové razítko, volbu délky noty (1/1 až 1/16),
    vycentrování rozsahu, Auto-Correct a stav HW.
    """

    def __init__(
        self,
        parent,
        on_auto_correct: Callable[[], None],
        on_center_range: Callable[[], None],
        on_tool_changed: Callable[[str, str, int], None],
        on_open_settings: Callable[[], None]
    ):
        super().__init__(parent, height=48, corner_radius=0)
        self.on_auto_correct = on_auto_correct
        self.on_center_range = on_center_range
        self.on_tool_changed = on_tool_changed
        self.on_open_settings = on_open_settings

        self.current_tool = "DRAW"
        self.current_chord = "Jedna nota (Tužka)"
        self.snap_div = 8  # Výchozí 1/8

        self._build_ui()

    def _build_ui(self) -> None:
        # 1. Vlevo: Editační nástroje
        tools_frame = ctk.CTkFrame(self, fg_color="transparent")
        tools_frame.pack(side="left", padx=8, pady=6)

        ctk.CTkLabel(tools_frame, text="Nástroj:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=(2, 4))

        self.btn_draw = ctk.CTkButton(
            tools_frame,
            text="✎ Kreslit / Akord",
            width=115,
            height=28,
            fg_color="#3B8ED0",
            command=lambda: self._select_tool("DRAW")
        )
        self.btn_draw.pack(side="left", padx=2)

        self.btn_erase = ctk.CTkButton(
            tools_frame,
            text="✖ Guma (Smazat)",
            width=110,
            height=28,
            fg_color="gray30",
            command=lambda: self._select_tool("ERASE")
        )
        self.btn_erase.pack(side="left", padx=2)

        ctk.CTkLabel(tools_frame, text="Akord:", font=("Segoe UI", 12)).pack(side="left", padx=(8, 4))
        self.chord_menu = ctk.CTkOptionMenu(
            tools_frame,
            values=list(CHORD_TEMPLATES.keys()),
            width=170,
            height=28,
            command=self._on_chord_change
        )
        self.chord_menu.set(self.current_chord)
        self.chord_menu.pack(side="left", padx=2)

        ctk.CTkLabel(tools_frame, text="Nota / Mřížka:", font=("Segoe UI", 12)).pack(side="left", padx=(8, 4))
        self.snap_menu = ctk.CTkOptionMenu(
            tools_frame,
            values=list(NOTE_LENGTH_OPTIONS.keys()),
            width=175,
            height=28,
            command=self._on_snap_change
        )
        self.snap_menu.set("1/8 (Osminová)")
        self.snap_menu.pack(side="left", padx=2)

        # 2. Uprostřed: Ochrana rozsahu a vycentrování
        mid_frame = ctk.CTkFrame(self, fg_color="transparent")
        mid_frame.pack(side="left", padx=8, pady=6)

        self.btn_center = ctk.CTkButton(
            mid_frame,
            text="🎯 Vycentrovat na rozsah",
            width=145,
            height=28,
            fg_color="gray35",
            command=self.on_center_range
        )
        self.btn_center.pack(side="left", padx=3)

        self.btn_autocorrect = ctk.CTkButton(
            mid_frame,
            text="Auto-Correct (Transpozice)",
            fg_color="#D9534F",
            hover_color="#B52B27",
            width=160,
            height=28,
            command=self.on_auto_correct
        )
        self.btn_autocorrect.pack(side="left", padx=3)

        self.lbl_range_warning = ctk.CTkLabel(
            mid_frame,
            text="✓ Rozsah OK",
            text_color="#2FA572",
            font=("Segoe UI", 12, "bold")
        )
        self.lbl_range_warning.pack(side="left", padx=6)

        # 3. Vpravo: Kompaktní stav HW + Nastavení
        right_frame = ctk.CTkFrame(self, fg_color="transparent")
        right_frame.pack(side="right", padx=8, pady=6)

        self.btn_settings = ctk.CTkButton(
            right_frame,
            text="⚙ Nastavení / Port",
            width=120,
            height=28,
            fg_color="gray30",
            command=self.on_open_settings
        )
        self.btn_settings.pack(side="right", padx=4)

        self.lbl_hw_status = ctk.CTkLabel(
            right_frame,
            text="● Offline (Bez HW)",
            text_color="#E0A82E",
            font=("Segoe UI", 11, "bold")
        )
        self.lbl_hw_status.pack(side="right", padx=8)

    def _select_tool(self, tool: str) -> None:
        self.current_tool = tool
        if tool == "DRAW":
            self.btn_draw.configure(fg_color="#3B8ED0")
            self.btn_erase.configure(fg_color="gray30")
        else:
            self.btn_draw.configure(fg_color="gray30")
            self.btn_erase.configure(fg_color="#D9534F")
        self._notify_tool()

    def _on_chord_change(self, chord_name: str) -> None:
        self.current_chord = chord_name
        self._select_tool("DRAW")

    def _on_snap_change(self, val: str) -> None:
        self.snap_div = NOTE_LENGTH_OPTIONS.get(val, 8)
        self._notify_tool()

    def _notify_tool(self) -> None:
        self.on_tool_changed(self.current_tool, self.current_chord, self.snap_div)

    def update_track_header(self, track_name: str, inst_name: str, invalid_count: int) -> None:
        if invalid_count > 0:
            self.lbl_range_warning.configure(
                text=f"⚠ {invalid_count} mimo rozsah!",
                text_color="#FF5555"
            )
        else:
            self.lbl_range_warning.configure(
                text="✓ Rozsah OK",
                text_color="#2FA572"
            )

    def update_hw_status(self, connected: bool, status_text: str) -> None:
        if connected:
            short_txt = status_text if len(status_text) <= 24 else status_text[:24] + "..."
            self.lbl_hw_status.configure(text=f"● {short_txt}", text_color="#2FA572")
        else:
            self.lbl_hw_status.configure(text="● Offline (Bez HW)", text_color="#E0A82E")