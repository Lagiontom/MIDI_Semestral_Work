# ui/app_window.py
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from typing import List, Dict, Any, Optional

from models.note_event import TrackData
from models.project_io import ProjectIO
from core.midi_parser import MidiFileParser
from core.validator import MidiValidator
from core.track_router import TrackRouter
from core.sequencer import RealtimeSequencer
from core.note_state_manager import NoteStateManager
from core.audio_engine import AudioEngine
from hardware.serial_manager import SerialHardwareManager

from ui.top_bar import TopBar
from ui.left_panel import LeftPanel
from ui.piano_roll import PianoRollCanvas
from ui.bottom_bar import BottomBar
from ui.settings_modal import SettingsModal


class MidiLogWindow(ctk.CTkToplevel):
    """
    Okno s kompletní historií všech odeslaných MIDI zpráv a možností uložení do .txt.
    """

    def __init__(self, parent, serial_mgr: SerialHardwareManager):
        super().__init__(parent)
        self.title("📋 MIDI Monitor — Výpis odeslaných zpráv do převodníku")
        self.geometry("740x480")
        self.serial_mgr = serial_mgr

        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=12, pady=(12, 6))

        self.lbl_last = ctk.CTkLabel(
            top_frame,
            text=f"Poslední MIDI zpráva: {self.serial_mgr.last_midi_message_str}",
            font=("Consolas", 13, "bold"),
            anchor="w"
        )
        self.lbl_last.pack(side="left", padx=10, pady=8, fill="x", expand=True)

        self.textbox = ctk.CTkTextbox(self, font=("Consolas", 12), wrap="none")
        self.textbox.pack(fill="both", expand=True, padx=12, pady=6)

        if self.serial_mgr.midi_log_history:
            self.textbox.insert("end", "\n".join(self.serial_mgr.midi_log_history) + "\n")
            self.textbox.see("end")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(4, 12))

        ctk.CTkButton(
            btn_frame,
            text="💾 Stáhnout log (.txt)",
            fg_color="#2FA572",
            hover_color="#248259",
            width=170,
            command=self._save_txt
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="🗑 Vymazat výpis",
            fg_color="#D9534F",
            hover_color="#B52B27",
            width=140,
            command=self._clear_log
        ).pack(side="left")

        ctk.CTkButton(
            btn_frame,
            text="Zavřít",
            fg_color="gray40",
            width=100,
            command=self.destroy
        ).pack(side="right")

    def append_line(self, short_msg: str, full_line: str) -> None:
        if not self.winfo_exists():
            return
        self.lbl_last.configure(text=f"Poslední MIDI zpráva: {short_msg}")
        self.textbox.insert("end", full_line + "\n")
        self.textbox.see("end")

    def _clear_log(self) -> None:
        self.serial_mgr.clear_log()
        self.textbox.delete("1.0", "end")
        self.lbl_last.configure(text="Poslední MIDI zpráva: -")

    def _save_txt(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Uložit MIDI log do souboru",
            defaultextension=".txt",
            initialfile="midi_komunikace_log.txt",
            filetypes=[("Textový soubor", "*.txt"), ("Všechny soubory", "*.*")]
        )
        if path:
            try:
                self.serial_mgr.save_log_to_txt(path)
                messagebox.showinfo("Uloženo", f"Log komunikace byl uložen do:\n{path}")
            except Exception as e:
                messagebox.showerror("Chyba uložení", f"Nepodařilo se uložit log:\n{e}")


class AppWindow(ctk.CTk):
    """Hlavní okno aplikace Mechatronic MIDI Studio."""

    def __init__(self):
        super().__init__()
        self.title("Mechatronic MIDI Studio — STM32F407 Sequencer Hub")
        self.geometry("1420x840")
        self.minsize(1080, 680)

        self.config_data = ProjectIO.load_config()
        ctk.set_appearance_mode(self.config_data.get("appearance_mode", "Dark"))

        self.log_window: Optional[MidiLogWindow] = None

        # POZOR: Nejprve inicializujeme SerialHardwareManager (mido), ABY MĚL PŘEVODNÍK VOLNÝ!
        self.state_manager = NoteStateManager()
        self.serial_mgr = SerialHardwareManager(
            on_status_change=self._on_hw_status_change,
            on_midi_log=self._on_midi_log_received
        )
        self.audio_engine = AudioEngine()
        self.router = TrackRouter(self.state_manager, self.serial_mgr, self.audio_engine)

        self.sequencer = RealtimeSequencer(
            router=self.router,
            on_tick_callback=self._on_sequencer_tick_threadsafe,
            on_playback_finished=self._on_playback_finished_threadsafe
        )

        self.current_project_path: str = ""
        self.bpm: float = 120.0
        self.ticks_per_beat: int = 480
        self.tracks: List[TrackData] = [
            TrackData(name="Harmonika", instrument_id="MELODICA")
        ]
        self.active_track_index: int = 0
        self._preview_timers: Dict[int, threading.Timer] = {}

        self._build_custom_menubar()
        self._build_ui()
        self._refresh_quick_port_combo()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_custom_menubar(self) -> None:
        self.menubar_frame = ctk.CTkFrame(
            self, height=34, corner_radius=0,
            fg_color=("#E5E5E5", "#1E1E1E")
        )
        self.menubar_frame.pack(side="top", fill="x")

        btn_style = {
            "width": 68,
            "height": 26,
            "corner_radius": 4,
            "fg_color": "transparent",
            "hover_color": ("#CCCCCC", "#333333"),
            "text_color": ("#111111", "#EAEAEA"),
            "font": ("Segoe UI", 12)
        }

        self.btn_menu_file = ctk.CTkButton(self.menubar_frame, text="Soubor", command=self._show_file_menu, **btn_style)
        self.btn_menu_file.pack(side="left", padx=(6, 2), pady=3)

        self.btn_menu_edit = ctk.CTkButton(self.menubar_frame, text="Úpravy", command=self._show_edit_menu, **btn_style)
        self.btn_menu_edit.pack(side="left", padx=2, pady=3)

        self.btn_menu_view = ctk.CTkButton(self.menubar_frame, text="Zobrazení", command=self._show_view_menu, **btn_style)
        self.btn_menu_view.pack(side="left", padx=2, pady=3)

        ctk.CTkLabel(self.menubar_frame, text="|  Výstupní port:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=(8, 4))

        self.quick_port_var = ctk.StringVar(value="")
        self.quick_port_combo = ctk.CTkOptionMenu(
            self.menubar_frame,
            variable=self.quick_port_var,
            values=["Žádný port"],
            width=210,
            height=25,
            command=self._on_quick_port_selected
        )
        self.quick_port_combo.pack(side="left", padx=4, pady=3)

        ctk.CTkButton(
            self.menubar_frame,
            text="🔄 Obnovit",
            width=78,
            height=25,
            command=self._refresh_quick_port_combo
        ).pack(side="left", padx=2, pady=3)

        ctk.CTkButton(
            self.menubar_frame,
            text="🔊 Test tón (C4)",
            width=110,
            height=25,
            fg_color="#1F6AA5",
            command=self._send_hw_test_note
        ).pack(side="left", padx=4, pady=3)

        ctk.CTkButton(
            self.menubar_frame,
            text="📋 MIDI Log (.txt)",
            width=125,
            height=25,
            fg_color="#2FA572",
            hover_color="#248259",
            command=self.open_midi_log_window
        ).pack(side="left", padx=4, pady=3)

        self.lbl_last_midi = ctk.CTkLabel(
            self.menubar_frame,
            text="Poslední MIDI zpráva: -",
            font=("Consolas", 12),
            text_color=("#111111", "#88FF88"),
            anchor="w"
        )
        self.lbl_last_midi.pack(side="left", padx=(12, 8), fill="x", expand=True)

    def _refresh_quick_port_combo(self) -> None:
        """Uvolní případnou blokaci winmm.dll, načte porty přes mido a připojí vybraný port."""
        if self.audio_engine and self.audio_engine.initialized:
            self.audio_engine.close()

        ports = self.serial_mgr.list_available_ports()
        if not ports:
            ports = ["Žádné porty nenalezeny"]

        self.quick_port_combo.configure(values=ports)
        saved = self.config_data.get("com_port", "")
        chosen = saved if saved in ports else ports[0]
        self.quick_port_var.set(chosen)

        if "Žádné" not in chosen:
            self.serial_mgr.connect(chosen, self.config_data.get("baudrate", 115200))

    def _on_quick_port_selected(self, selected_port: str) -> None:
        if self.audio_engine and self.audio_engine.initialized:
            self.audio_engine.close()
        self.serial_mgr.connect(selected_port, self.config_data.get("baudrate", 115200))
        self.config_data["com_port"] = selected_port
        ProjectIO.save_config(self.config_data)

    def _send_hw_test_note(self) -> None:
        selected_port = self.quick_port_var.get()
        if not self.serial_mgr.is_connected and selected_port and "Žádné" not in selected_port:
            self.serial_mgr.connect(selected_port, self.config_data.get("baudrate", 115200))

        ch = (self.active_track.midi_channel if self.active_track else 0)
        ok = self.serial_mgr.send_test_note(pitch=60, channel=ch, duration=0.4)
        if not ok:
            messagebox.showwarning(
                "Port není připojen",
                f"Nepodařilo se odeslat testovací tón na port '{selected_port}'.\nZkontrolujte výběr portu v horní liště."
            )

    def _on_midi_log_received(self, short_msg: str, full_line: str) -> None:
        def _update():
            self.lbl_last_midi.configure(text=f"Poslední MIDI zpráva: {short_msg}")
            if self.log_window is not None and self.log_window.winfo_exists():
                self.log_window.append_line(short_msg, full_line)

        self.after(0, _update)

    def open_midi_log_window(self) -> None:
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.lift()
            self.log_window.focus()
            return
        self.log_window = MidiLogWindow(self, self.serial_mgr)

    def _create_popup_menu(self) -> tk.Menu:
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg = "#252526" if is_dark else "#F5F5F5"
        fg = "#EAEAEA" if is_dark else "#111111"
        active_bg = "#3B8ED0"
        return tk.Menu(
            self, tearoff=0, bg=bg, fg=fg,
            activebackground=active_bg, activeforeground="white",
            font=("Segoe UI", 10), bd=1, relief="solid"
        )

    def _show_file_menu(self) -> None:
        menu = self._create_popup_menu()
        menu.add_command(label="Nový projekt", command=self.new_project)
        menu.add_command(label="Otevřít (.mid / .mproj)...", command=self.open_file_dialog)
        menu.add_command(label="Uložit projekt (.mproj)", command=self.save_project)
        menu.add_command(label="Exportovat standardní .mid...", command=self.export_midi)
        menu.add_separator()
        menu.add_command(label="Otevřít MIDI Monitor / Log (.txt)...", command=self.open_midi_log_window)
        menu.add_command(label="Nastavení (Porty & Vzhled)...", command=self.open_settings_modal)
        menu.add_separator()
        menu.add_command(label="Ukončit", command=self._on_close)
        x = self.btn_menu_file.winfo_rootx()
        y = self.btn_menu_file.winfo_rooty() + self.btn_menu_file.winfo_height()
        menu.tk_popup(x, y)

    def _show_edit_menu(self) -> None:
        menu = self._create_popup_menu()
        menu.add_command(label="Auto-Correct (Transpozice do rozsahu)", command=self.run_auto_correct)
        menu.add_command(label="Přidat novou stopu", command=self.add_new_track)
        menu.add_command(label="Vymazat všechny noty v aktivní stopě", command=self.clear_active_track_notes)
        x = self.btn_menu_edit.winfo_rootx()
        y = self.btn_menu_edit.winfo_rooty() + self.btn_menu_edit.winfo_height()
        menu.tk_popup(x, y)

    def _show_view_menu(self) -> None:
        menu = self._create_popup_menu()
        menu.add_command(
            label="Vycentrovat tabulku na rozsah nástroje",
            command=lambda: self.piano_roll.scroll_to_instrument_range()
        )
        menu.add_command(label="Otevřít MIDI Monitor / Log", command=self.open_midi_log_window)
        menu.add_separator()
        menu.add_command(label="Tmavý režim (Dark)", command=lambda: self._switch_theme("Dark"))
        menu.add_command(label="Světlý režim (Light)", command=lambda: self._switch_theme("Light"))
        x = self.btn_menu_view.winfo_rootx()
        y = self.btn_menu_view.winfo_rooty() + self.btn_menu_view.winfo_height()
        menu.tk_popup(x, y)

    def _switch_theme(self, mode: str) -> None:
        self.config_data["appearance_mode"] = mode
        ProjectIO.save_config(self.config_data)
        self.after(20, lambda: ctk.set_appearance_mode(mode))

    def _build_ui(self) -> None:
        self.top_bar = TopBar(
            self,
            on_auto_correct=self.run_auto_correct,
            on_center_range=lambda: self.piano_roll.scroll_to_instrument_range(),
            on_tool_changed=self._on_tool_changed,
            on_open_settings=self.open_settings_modal
        )
        self.top_bar.pack(side="top", fill="x")

        center_frame = ctk.CTkFrame(self, fg_color="transparent")
        center_frame.pack(side="top", fill="both", expand=True)

        self.left_panel = LeftPanel(
            center_frame,
            default_dir=self.config_data.get("default_midi_dir", "./"),
            on_file_selected=self.load_file,
            on_track_selected=self.select_track,
            on_track_changed=self.refresh_ui,
            on_add_track=self.add_new_track,
            on_delete_track=self.delete_track
        )
        self.left_panel.pack(side="left", fill="y", padx=(4, 2), pady=4)

        self.piano_roll = PianoRollCanvas(
            center_frame,
            on_notes_modified=self._on_notes_modified_in_grid,
            on_preview_note=self._preview_single_note
        )
        self.piano_roll.pack(side="right", fill="both", expand=True, padx=(2, 4), pady=4)

        self.bottom_bar = BottomBar(
            self,
            on_play=self.start_playback,
            on_pause=self.pause_playback,
            on_stop=self.stop_playback,
            on_record_toggle=self.toggle_recording,
            on_bpm_changed=self.set_bpm,
            on_key_down=self._test_key_down,
            on_key_up=self._test_key_up,
            on_bars_changed=self.set_total_bars
        )
        self.bottom_bar.pack(side="bottom", fill="x")

        self.select_track(0)

    def _on_hw_status_change(self, connected: bool, text: str) -> None:
        self.after(0, lambda: self.top_bar.update_hw_status(connected, text))

    @property
    def active_track(self) -> Optional[TrackData]:
        if 0 <= self.active_track_index < len(self.tracks):
            return self.tracks[self.active_track_index]
        return None

    def refresh_ui(self, auto_scroll: bool = False) -> None:
        active_t = self.active_track
        invalid_cnt = active_t.validate_notes() if active_t else 0
        inst_name = active_t.instrument.display_name if active_t else "---"
        track_name = active_t.name if active_t else "---"

        self.top_bar.update_track_header(track_name, inst_name, invalid_cnt)
        self.left_panel.render_tracks(self.tracks, self.active_track_index)
        self.piano_roll.set_track(active_t, auto_scroll=auto_scroll)

    def _on_notes_modified_in_grid(self) -> None:
        active_t = self.active_track
        invalid_cnt = active_t.validate_notes() if active_t else 0
        inst_name = active_t.instrument.display_name if active_t else "---"
        track_name = active_t.name if active_t else "---"
        self.top_bar.update_track_header(track_name, inst_name, invalid_cnt)

    def select_track(self, index: int) -> None:
        if 0 <= index < len(self.tracks):
            self.active_track_index = index
            self.refresh_ui(auto_scroll=True)

    def add_new_track(self) -> None:
        new_idx = len(self.tracks) + 1
        default_inst = "METALLOPHONE" if new_idx == 2 else ("PAN_FLUTE" if new_idx == 3 else "MELODICA")
        t = TrackData(name=f"Stopa {new_idx}", instrument_id=default_inst)
        self.tracks.append(t)
        self.select_track(len(self.tracks) - 1)

    def delete_track(self, index: int) -> None:
        if len(self.tracks) <= 1:
            messagebox.showwarning("Nelze smazat", "Projekt musí obsahovat alespoň jednu stopu.")
            return
        if 0 <= index < len(self.tracks):
            self.tracks.pop(index)
            self.active_track_index = max(0, min(self.active_track_index, len(self.tracks) - 1))
            self.select_track(self.active_track_index)

    def clear_active_track_notes(self) -> None:
        t = self.active_track
        if t and messagebox.askyesno("Vymazat noty", f"Opravdu vymazat všechny noty ve stopě '{t.name}'?"):
            t.notes.clear()
            self.refresh_ui(auto_scroll=False)

    def new_project(self) -> None:
        self.stop_playback()
        self.current_project_path = ""
        self.tracks = [TrackData(name="Harmonika", instrument_id="MELODICA")]
        self.bpm = 120.0
        self.bottom_bar.set_bpm_display(self.bpm)
        self.select_track(0)

    def open_file_dialog(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=self.config_data.get("default_midi_dir", "./"),
            filetypes=[("MIDI & Projekty", "*.mid *.midi *.mproj"), ("Všechny soubory", "*.*")]
        )
        if path:
            self.load_file(path)

    def load_file(self, filepath: str) -> None:
        self.stop_playback()
        try:
            if filepath.lower().endswith(".mproj"):
                self.tracks, self.bpm, self.ticks_per_beat = ProjectIO.load_project(filepath)
                self.current_project_path = filepath
            else:
                self.tracks, self.bpm, self.ticks_per_beat = MidiFileParser.load_midi_file(filepath)
                self.current_project_path = ""

            self.bottom_bar.set_bpm_display(self.bpm)
            self.active_track_index = 0
            self.select_track(0)
        except Exception as e:
            messagebox.showerror("Chyba načítání", f"Nepodařilo se načíst soubor:\n{e}")

    def save_project(self) -> None:
        if not self.current_project_path:
            path = filedialog.asksaveasfilename(
                initialdir=self.config_data.get("default_midi_dir", "./"),
                defaultextension=".mproj",
                filetypes=[("MidiStudio projekt", "*.mproj")]
            )
            if not path:
                return
            self.current_project_path = path

        ProjectIO.save_project(self.current_project_path, self.tracks, self.bpm, self.ticks_per_beat)
        self.left_panel.refresh_file_list(self.config_data.get("default_midi_dir", "./"))
        messagebox.showinfo("Uloženo", "Projekt byl úspěšně uložen do .mproj")

    def export_midi(self) -> None:
        path = filedialog.asksaveasfilename(
            initialdir=self.config_data.get("default_midi_dir", "./"),
            defaultextension=".mid",
            filetypes=[("Standardní MIDI", "*.mid")]
        )
        if path:
            MidiFileParser.export_midi_file(path, self.tracks, self.bpm, self.ticks_per_beat)
            self.left_panel.refresh_file_list(self.config_data.get("default_midi_dir", "./"))
            messagebox.showinfo("Export", "MIDI soubor byl exportován (velocity fixována na 127).")

    def run_auto_correct(self) -> None:
        t = self.active_track
        if not t:
            return
        fixed, invalid = MidiValidator.auto_correct_track(t)
        self.refresh_ui(auto_scroll=True)
        messagebox.showinfo("Auto-Correct", f"Transponováno not do rozsahu: {fixed}\nZbývá mimo rozsah: {invalid}")

    def _on_tool_changed(self, tool: str, chord_name: str, snap_div: int) -> None:
        self.piano_roll.set_tool_params(tool, chord_name, snap_div)

    def set_bpm(self, val: float) -> None:
        self.bpm = val
        self.sequencer.bpm = val

    def set_total_bars(self, bars: int) -> None:
        self.sequencer.set_total_bars(bars)
        self.piano_roll.set_total_bars(bars)

    def start_playback(self) -> None:
        self.sequencer.bpm = self.bpm
        self.sequencer.ticks_per_beat = self.ticks_per_beat
        self.sequencer.start(self.tracks, record_mode=self.bottom_bar.is_recording)

    def pause_playback(self) -> None:
        self.sequencer.pause()

    def stop_playback(self) -> None:
        for timer in list(self._preview_timers.values()):
            timer.cancel()
        self._preview_timers.clear()

        self.sequencer.stop()
        self.bottom_bar.set_recording_state(False)
        self.piano_roll.set_playhead(0)
        self.bottom_bar.update_time_display("00:00:000")

    def toggle_recording(self, rec_active: bool) -> None:
        if rec_active:
            self.sequencer.bpm = self.bpm
            self.sequencer.ticks_per_beat = self.ticks_per_beat
            self.sequencer.start(self.tracks, record_mode=True)
        else:
            self.stop_playback()
            self.refresh_ui(auto_scroll=False)

    def _on_sequencer_tick_threadsafe(self, tick: int) -> None:
        self.after(0, self._update_playhead_on_main_thread, tick)

    def _update_playhead_on_main_thread(self, tick: int) -> None:
        self.piano_roll.set_playhead(tick)
        time_str = self.sequencer.ticks_to_time_str(tick)
        self.bottom_bar.update_time_display(time_str)

    def _on_playback_finished_threadsafe(self) -> None:
        self.after(0, self.stop_playback)

    def _preview_single_note(self, pitch: int) -> None:
        t = self.active_track
        if not t:
            return

        inst_id = t.instrument_id
        ch = t.midi_channel

        old_timer = self._preview_timers.pop(pitch, None)
        if old_timer:
            old_timer.cancel()

        self.router.trigger_note_on(inst_id, pitch, channel=ch)

        def _stop_preview():
            self._preview_timers.pop(pitch, None)
            self.router.trigger_note_off(inst_id, pitch, channel=ch)

        timer = threading.Timer(0.20, _stop_preview)
        timer.daemon = True
        self._preview_timers[pitch] = timer
        timer.start()

    def _test_key_down(self, pitch: int) -> None:
        t = self.active_track
        if t:
            self.router.trigger_note_on(
                t.instrument_id,
                pitch,
                channel=t.midi_channel,
                is_recording=self.sequencer.is_recording,
                current_tick=self.sequencer.current_tick
            )

    def _test_key_up(self, pitch: int) -> None:
        t = self.active_track
        if t:
            created = self.router.trigger_note_off(
                t.instrument_id,
                pitch,
                channel=t.midi_channel,
                is_recording=self.sequencer.is_recording,
                current_tick=self.sequencer.current_tick,
                active_track=t
            )
            if created is not None:
                self.piano_roll.redraw_notes()
                self._on_notes_modified_in_grid()

    def open_settings_modal(self) -> None:
        SettingsModal(self, self.config_data, self.serial_mgr, self._save_config)

    def _save_config(self, new_cfg: Dict[str, Any]) -> None:
        self.config_data = new_cfg
        ProjectIO.save_config(new_cfg)
        self.left_panel.refresh_file_list(new_cfg.get("default_midi_dir", "./"))
        self._refresh_quick_port_combo()

    def _on_close(self) -> None:
        for timer in list(self._preview_timers.values()):
            timer.cancel()
        self.sequencer.stop()
        self.serial_mgr.disconnect()
        self.audio_engine.close()
        self.destroy()