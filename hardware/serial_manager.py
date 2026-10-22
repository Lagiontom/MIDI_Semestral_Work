# hardware/serial_manager.py
import threading
import time
from datetime import datetime
from typing import List, Optional, Callable
import mido
import serial
import serial.tools.list_ports


class SerialHardwareManager:
    """
    Komunikace s převodníkem:
    1. Přímá podpora USB-MIDI přes mido.open_output() – identicky jako ve funkčním MidiStudioApp.
    2. Podpora sériových COM portů přes pyserial.
    3. Kompletní logování všech odeslaných MIDI zpráv s možností exportu do .txt.
    """

    def __init__(
        self,
        on_status_change: Optional[Callable[[bool, str], None]] = None,
        on_midi_log: Optional[Callable[[str, str], None]] = None
    ):
        self._serial: Optional[serial.Serial] = None
        self._mido_port = None
        self.mode: Optional[str] = None  # "MIDO" nebo "SERIAL"
        self.port_name: str = ""
        self.baudrate: int = 115200
        self._lock = threading.Lock()
        self._running = False
        self._rx_thread: Optional[threading.Thread] = None

        self.on_status_change = on_status_change
        self.on_midi_log = on_midi_log
        self.last_rx_line: str = ""

        # Historie všech odeslaných MIDI zpráv
        self.midi_log_history: List[str] = []
        self.last_midi_message_str: str = "Žádná zpráva zatím neodeslána"

    @staticmethod
    def list_available_ports() -> List[str]:
        """Vrátí nejprve všechny USB-MIDI porty z mido.get_output_names() a poté COM porty."""
        ports: List[str] = []
        try:
            for name in mido.get_output_names():
                ports.append(name)
        except Exception as e:
            print(f"[mido.get_output_names error]: {e}")

        try:
            for p in serial.tools.list_ports.comports():
                ports.append(f"{p.device} ({p.description})")
        except Exception:
            pass

        return ports

    @staticmethod
    def extract_port_name(port_display: str) -> str:
        if not port_display:
            return ""
        # Pokud je to přímo mido port, nesmíme ho oříznout podle mezery!
        try:
            midi_names = mido.get_output_names()
            clean = port_display.replace("[USB-MIDI]", "").strip()
            if clean in midi_names:
                return clean
        except Exception:
            pass

        if port_display.upper().startswith("COM"):
            return port_display.split(" ")[0].strip()
        return port_display.strip()

    @property
    def is_connected(self) -> bool:
        if self.mode == "MIDO":
            return self._mido_port is not None
        if self.mode == "SERIAL":
            return self._serial is not None and self._serial.is_open
        return False

    def connect(self, port: str, baudrate: int = 115200) -> bool:
        """Otevře USB-MIDI port přes mido.open_output(port) nebo sériový COM port."""
        self.disconnect()
        if not port or "Žádn" in port:
            return False

        clean_candidate = port.replace("[USB-MIDI]", "").strip()

        # 1. Zkusíme otevřít jako mido USB-MIDI port (přesně jako ve tvém druhém programu)
        midi_names: List[str] = []
        try:
            midi_names = mido.get_output_names()
        except Exception:
            pass

        # Pokud název odpovídá libovolnému mido portu (nebo se shoduje začátek názvu)
        matched_midi = None
        if clean_candidate in midi_names:
            matched_midi = clean_candidate
        else:
            for m_name in midi_names:
                if clean_candidate and (clean_candidate in m_name or m_name in clean_candidate):
                    matched_midi = m_name
                    break

        if matched_midi is not None:
            try:
                with self._lock:
                    self._mido_port = mido.open_output(matched_midi)
                    self.mode = "MIDO"
                    self.port_name = matched_midi
                self._log_event(f"Připojen USB-MIDI port: {matched_midi}", is_system=True)
                if self.on_status_change:
                    self.on_status_change(True, f"USB-MIDI: {matched_midi}")
                return True
            except Exception as e:
                self._mido_port = None
                self.mode = None
                self._log_event(f"Chyba otevření USB-MIDI '{matched_midi}': {e}", is_system=True)
                if self.on_status_change:
                    self.on_status_change(False, f"Chyba USB-MIDI: {e}")
                return False

        # 2. Jinak otevřeme jako sériový COM port přes pyserial
        com_name = port.split(" ")[0].strip()
        try:
            with self._lock:
                self._serial = serial.Serial(
                    port=com_name,
                    baudrate=int(baudrate),
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.05,
                    write_timeout=0.1
                )
                self.mode = "SERIAL"
                self.port_name = com_name
                self.baudrate = int(baudrate)
                self._running = True

            self._rx_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._rx_thread.start()

            self._log_event(f"Připojen sériový port: {com_name} @ {baudrate} Bd", is_system=True)
            if self.on_status_change:
                self.on_status_change(True, f"COM: {com_name} @ {baudrate} Bd")
            return True

        except Exception as e:
            self._serial = None
            self.mode = None
            self._log_event(f"Chyba otevření COM portu '{com_name}': {e}", is_system=True)
            if self.on_status_change:
                self.on_status_change(False, f"Odpojeno ({com_name} nedostupný)")
            return False

    def disconnect(self) -> None:
        self._running = False
        with self._lock:
            if self._mido_port is not None:
                try:
                    self._mido_port.close()
                except Exception:
                    pass
                self._mido_port = None

            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                except Exception:
                    pass
            self._serial = None
            self.mode = None
            self.port_name = ""

        if self.on_status_change:
            self.on_status_change(False, "Odpojeno")

    def _log_event(self, short_msg: str, is_system: bool = False) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        port_tag = f"[{self.mode}:{self.port_name}]" if self.is_connected else "[NEPŘIPOJENO]"
        full_line = f"[{timestamp}] {port_tag} {short_msg}"
        self.midi_log_history.append(full_line)
        if not is_system:
            self.last_midi_message_str = short_msg
        if self.on_midi_log:
            try:
                self.on_midi_log(short_msg, full_line)
            except Exception:
                pass

    def clear_log(self) -> None:
        self.midi_log_history.clear()
        self.last_midi_message_str = "Log vymazán"

    def save_log_to_txt(self, filepath: str) -> None:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("=== MECHATRONIC MIDI STUDIO - LOG KOMUNIKACE ===\n")
            f.write(f"Aktuální port: {self.port_name or 'Žádný'} (Režim: {self.mode or 'Offline'})\n")
            f.write("=" * 55 + "\n\n")
            for line in self.midi_log_history:
                f.write(line + "\n")

    def send_raw_midi(self, midi_bytes: Optional[bytes]) -> bool:
        """
        Odešle MIDI zprávu do převodníku a zapíše ji do logu přesně ve formátu mido:
        např. 'note_on channel=0 note=25 velocity=127 time=0'
        """
        if not midi_bytes:
            return False

        # Rozparsujeme 3bajtové zprávy na objekty mido.Message
        messages: List[mido.Message] = []
        for i in range(0, len(midi_bytes) - 2, 3):
            status = midi_bytes[i] & 0xF0
            ch = midi_bytes[i] & 0x0F
            d1 = midi_bytes[i + 1] & 0x7F
            d2 = midi_bytes[i + 2] & 0x7F

            if status == 0x90 and d2 > 0:
                messages.append(mido.Message("note_on", channel=ch, note=d1, velocity=d2, time=0))
            elif status == 0x80 or (status == 0x90 and d2 == 0):
                messages.append(mido.Message("note_off", channel=ch, note=d1, velocity=0, time=0))
            elif status == 0xB0:
                messages.append(mido.Message("control_change", channel=ch, control=d1, value=d2, time=0))

        # Zalogujeme každou zprávu (i když třeba port ještě není připojen, abys viděl, co program generuje!)
        for msg in messages:
            self._log_event(str(msg), is_system=False)

        if not self.is_connected:
            return False

        with self._lock:
            try:
                if self.mode == "MIDO" and self._mido_port is not None:
                    for msg in messages:
                        self._mido_port.send(msg)
                    return True
                elif self.mode == "SERIAL" and self._serial and self._serial.is_open:
                    self._serial.write(midi_bytes)
                    self._serial.flush()
                    return True
            except Exception as e:
                self._log_event(f"CHYBA ODESÍLÁNÍ: {e}", is_system=True)
                return False
        return False

    def send_batch(self, messages: List[bytes]) -> None:
        if not messages:
            return
        for m in messages:
            self.send_raw_midi(m)

    def send_test_note(self, pitch: int = 60, channel: int = 0, duration: float = 0.4) -> bool:
        """
        Odešle testovací tón přesně jako metoda send_test_note v tvém funkčním MidiStudioApp:
        mido.Message('note_on', note=60, velocity=127, channel=0) -> sleep -> note_off
        """
        ch = max(0, min(15, int(channel)))
        note = max(0, min(127, int(pitch)))

        def _worker():
            self.send_raw_midi(bytes([0x90 | ch, note, 127]))
            time.sleep(duration)
            self.send_raw_midi(bytes([0x80 | ch, note, 0]))

        threading.Thread(target=_worker, daemon=True).start()
        return self.is_connected

    def _read_loop(self) -> None:
        while self._running:
            try:
                if self._serial and self._serial.is_open and self._serial.in_waiting > 0:
                    raw = self._serial.readline()
                    if raw:
                        line = raw.decode("utf-8", errors="ignore").strip()
                        self.last_rx_line = line
                        self._log_event(f"RX z MCU: {line}", is_system=True)
                else:
                    time.sleep(0.02)
            except Exception:
                break


SerialMidiManager = SerialHardwareManager