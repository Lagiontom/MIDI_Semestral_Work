# ui/settings_modal.py
import customtkinter as ctk
from tkinter import filedialog, messagebox
from typing import Dict, Any, Callable
from hardware.serial_manager import SerialHardwareManager


class SettingsModal(ctk.CTkToplevel):
    """
    Modální okno nastavení:
    - Přepínání Dark / Light režimu
    - Výběr výchozí složky pro integrovaný prohlížeč MIDI souborů
    - Výběr USB-MIDI portu nebo COM portu + tlačítko Test tón (C4)
    """

    def __init__(
        self,
        parent,
        config: Dict[str, Any],
        serial_mgr: SerialHardwareManager,
        on_save_callback: Callable[[Dict[str, Any]], None]
    ):
        super().__init__(parent)
        self.title("Nastavení aplikace a USB-MIDI / Hardwaru")
        self.geometry("560x470")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.config_data = config.copy()
        self.serial_mgr = serial_mgr
        self.on_save_callback = on_save_callback

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 20, "pady": 6}

        # --- Sekce 1: Vzhled (Dark / Light) ---
        lbl_theme = ctk.CTkLabel(self, text="Vzhled rozhraní (Appearance Mode):", font=("Segoe UI", 13, "bold"))
        lbl_theme.pack(anchor="w", padx=20, pady=(15, 2))

        self.theme_var = ctk.StringVar(value=self.config_data.get("appearance_mode", "Dark"))
        self.seg_theme = ctk.CTkSegmentedButton(
            self,
            values=["Dark", "Light"],
            variable=self.theme_var,
            command=self._on_theme_change
        )
        self.seg_theme.pack(fill="x", **pad)

        # --- Sekce 2: Výchozí složka pro MIDI a projekty ---
        lbl_dir = ctk.CTkLabel(self, text="Výchozí složka pro MIDI a projekty:", font=("Segoe UI", 13, "bold"))
        lbl_dir.pack(anchor="w", padx=20, pady=(10, 2))

        dir_frame = ctk.CTkFrame(self, fg_color="transparent")
        dir_frame.pack(fill="x", **pad)

        self.dir_var = ctk.StringVar(value=self.config_data.get("default_midi_dir", ""))
        self.entry_dir = ctk.CTkEntry(dir_frame, textvariable=self.dir_var)
        self.entry_dir.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_browse = ctk.CTkButton(dir_frame, text="Procházet...", width=100, command=self._browse_dir)
        btn_browse.pack(side="right")

        # --- Sekce 3: Hardwarová komunikace (USB-MIDI / COM port) ---
        lbl_hw = ctk.CTkLabel(self, text="Výstupní USB-MIDI port nebo Sériový COM port:", font=("Segoe UI", 13, "bold"))
        lbl_hw.pack(anchor="w", padx=20, pady=(10, 2))

        hw_frame = ctk.CTkFrame(self)
        hw_frame.pack(fill="x", padx=20, pady=6)

        # Výběr portu
        row1 = ctk.CTkFrame(hw_frame, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(row1, text="Port:", width=70, anchor="w").pack(side="left")

        ports = self.serial_mgr.list_available_ports()
        if not ports:
            ports = ["Žádné porty nenalezeny"]

        saved_port = self.config_data.get("com_port", "")
        initial_port = saved_port if saved_port in ports else ports[0]

        self.port_var = ctk.StringVar(value=initial_port)
        self.combo_port = ctk.CTkOptionMenu(row1, variable=self.port_var, values=ports, width=280)
        self.combo_port.pack(side="left", padx=6)

        btn_refresh = ctk.CTkButton(row1, text="🔄 Obnovit", width=90, command=self._refresh_ports)
        btn_refresh.pack(side="right")

        # Výběr Baudrate + Připojit + Test tón C4
        row2 = ctk.CTkFrame(hw_frame, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(row2, text="Baudrate:", width=70, anchor="w").pack(side="left")

        self.baud_var = ctk.StringVar(value=str(self.config_data.get("baudrate", 115200)))
        self.combo_baud = ctk.CTkOptionMenu(
            row2,
            variable=self.baud_var,
            values=["31250", "38400", "57600", "115200", "230400"],
            width=110
        )
        self.combo_baud.pack(side="left", padx=6)

        self.btn_test = ctk.CTkButton(
            row2,
            text="🔊 Test tón (C4)",
            fg_color="#1F6AA5",
            width=125,
            command=self._test_note_c4
        )
        self.btn_test.pack(side="right", padx=(6, 0))

        self.btn_connect = ctk.CTkButton(
            row2,
            text="Odpojit" if self.serial_mgr.is_connected else "Připojit HW",
            fg_color="#D9534F" if self.serial_mgr.is_connected else "#2FA572",
            width=110,
            command=self._toggle_connection
        )
        self.btn_connect.pack(side="right")

        # --- Spodní tlačítka Uložit / Zavřít ---
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.pack(fill="x", side="bottom", padx=20, pady=15)

        ctk.CTkButton(bottom_frame, text="Uložit a zavřít", command=self._save_and_close).pack(side="right", padx=5)
        ctk.CTkButton(bottom_frame, text="Zrušit", fg_color="gray40", command=self.destroy).pack(side="right", padx=5)

    def _on_theme_change(self, mode: str) -> None:
        self.config_data["appearance_mode"] = mode

    def _browse_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.dir_var.get())
        if selected:
            self.dir_var.set(selected)

    def _refresh_ports(self) -> None:
        ports = self.serial_mgr.list_available_ports()
        if not ports:
            ports = ["Žádné porty nenalezeny"]
        self.combo_port.configure(values=ports)
        self.port_var.set(ports[0])

    def _toggle_connection(self) -> None:
        if self.serial_mgr.is_connected:
            self.serial_mgr.disconnect()
            self.btn_connect.configure(text="Připojit HW", fg_color="#2FA572")
        else:
            port = self.port_var.get()
            baud = int(self.baud_var.get())
            ok = self.serial_mgr.connect(port, baud)
            if ok:
                self.btn_connect.configure(text="Odpojit", fg_color="#D9534F")
            else:
                messagebox.showerror("Chyba portu", f"Nepodařilo se otevřít port:\n{port}")

    def _test_note_c4(self) -> None:
        if not self.serial_mgr.is_connected:
            port = self.port_var.get()
            baud = int(self.baud_var.get())
            if self.serial_mgr.connect(port, baud):
                self.btn_connect.configure(text="Odpojit", fg_color="#D9534F")

        if not self.serial_mgr.send_test_note(pitch=60, channel=0, duration=0.4):
            messagebox.showwarning("Test tón", "Nejprve vyberte a připojte platný USB-MIDI nebo COM port!")

    def _save_and_close(self) -> None:
        self.config_data["appearance_mode"] = self.theme_var.get()
        self.config_data["default_midi_dir"] = self.dir_var.get()
        self.config_data["com_port"] = self.serial_mgr.extract_port_name(self.port_var.get())
        self.config_data["baudrate"] = int(self.baud_var.get())
        self.on_save_callback(self.config_data)
        self.destroy()