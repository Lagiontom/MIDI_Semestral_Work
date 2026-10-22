# models/project_io.py
import json
import os
from typing import List, Tuple, Dict, Any
from models.note_event import TrackData

CONFIG_FILE = "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "appearance_mode": "Dark",       # "Dark" nebo "Light"
    "default_midi_dir": os.path.abspath("./midi_library"),
    "com_port": "COM3",
    "baudrate": 115200               # CP2102 USB-UART bridge na desce STM32F407
}

class ProjectIO:
    """Správa vlastního formátu projektů (.mproj) a trvalého nastavení aplikace."""

    @staticmethod
    def save_project(filepath: str, tracks: List[TrackData], bpm: float, ticks_per_beat: int = 480) -> None:
        if not filepath.lower().endswith(".mproj"):
            filepath += ".mproj"

        data = {
            "version": "1.0",
            "bpm": bpm,
            "ticks_per_beat": ticks_per_beat,
            "tracks": [t.to_dict() for t in tracks]
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def load_project(filepath: str) -> Tuple[List[TrackData], float, int]:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        bpm = float(data.get("bpm", 120.0))
        ticks_per_beat = int(data.get("ticks_per_beat", 480))
        tracks = [TrackData.from_dict(t) for t in data.get("tracks", [])]
        if not tracks:
            tracks = [TrackData(name="CH01 Harmonika", instrument_id="MELODICA")]
        return tracks, bpm, ticks_per_beat

    @staticmethod
    def load_config() -> Dict[str, Any]:
        cfg = DEFAULT_CONFIG.copy()
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    cfg.update(loaded)
            except Exception:
                pass
        # Zajistíme existenci výchozí složky pro MIDI knihovnu
        os.makedirs(cfg["default_midi_dir"], exist_ok=True)
        return cfg

    @staticmethod
    def save_config(cfg: Dict[str, Any]) -> None:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass