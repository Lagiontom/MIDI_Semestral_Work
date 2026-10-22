import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import mido
from mido import Message, MetaMessage, MidiFile, MidiTrack

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_to_note_name(note_num):
    if note_num is None or not (0 <= note_num <= 127):
        return "-"
    octave = (note_num // 12) - 1
    name = NOTE_NAMES[note_num % 12]
    return f"{name}{octave} ({note_num})"


class MidiStudioApp:

    def __init__(self, root):
        self.root = root
        self.root.title("USB-MIDI Studio (Přehrávač, Editor, Prohlížeč)")
        self.root.geometry("760x540")

        self.midi_file_path = None
        self.is_playing = False
        self.stop_requested = False
        self.play_thread = None

        # Seznam not v editoru: (note_num, duration_beats, velocity, channel)
        # note_num = -1 značí pomlku
        self.editor_notes = []

        # Záložky (Notebook)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_player = ttk.Frame(self.notebook)
        self.tab_creator = ttk.Frame(self.notebook)
        self.tab_inspector = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_player, text=" 1. Přehrávač (USB-MIDI) ")
        self.notebook.add(self.tab_creator, text=" 2. Vytvořit MIDI ")
        self.notebook.add(self.tab_inspector, text=" 3. Prohlížeč MIDI ")

        self._build_player_tab()
        self._build_creator_tab()
        self._build_inspector_tab()

        self.refresh_ports()

    # =========================================================================
    # KARTA 1: PŘEHRÁVAČ
    # =========================================================================
    def _build_player_tab(self):
        frame_file = ttk.LabelFrame(
            self.tab_player, text="1. MIDI Soubor", padding=10
        )
        frame_file.pack(fill="x", padx=15, pady=(15, 5))

        self.lbl_file = ttk.Label(
            frame_file, text="Žádný soubor nevybrán", width=55
        )
        self.lbl_file.pack(side="left", padx=(0, 10))

        btn_browse = ttk.Button(
            frame_file, text="Vybrat .mid", command=self.load_file_for_all
        )
        btn_browse.pack(side="right")

        frame_port = ttk.LabelFrame(
            self.tab_player, text="2. Výstupní USB-MIDI port", padding=10
        )
        frame_port.pack(fill="x", padx=15, pady=5)

        self.combo_ports = ttk.Combobox(frame_port, state="readonly", width=45)
        self.combo_ports.pack(side="left", padx=(0, 10))

        btn_test = ttk.Button(
            frame_port, text="Test tón (C4)", command=self.send_test_note
        )
        btn_test.pack(side="right", padx=(5, 0))

        btn_refresh = ttk.Button(
            frame_port, text="Obnovit porty", command=self.refresh_ports
        )
        btn_refresh.pack(side="right")

        frame_ctrl = ttk.LabelFrame(
            self.tab_player, text="3. Přehrávání", padding=10
        )
        frame_ctrl.pack(fill="x", padx=15, pady=5)

        self.btn_play = ttk.Button(
            frame_ctrl, text="▶ Přehrát do USB-MIDI", command=self.start_playback
        )
        self.btn_play.pack(side="left", expand=True, fill="x", padx=5)

        self.btn_stop = ttk.Button(
            frame_ctrl,
            text="⏹ Stop (Panic)",
            command=self.stop_playback,
            state="disabled",
        )
        self.btn_stop.pack(side="right", expand=True, fill="x", padx=5)

        frame_status = ttk.Frame(self.tab_player, padding=15)
        frame_status.pack(fill="both", expand=True)

        self.lbl_status = ttk.Label(
            frame_status,
            text="Stav: Připraveno",
            font=("sans-serif", 10, "bold"),
        )
        self.lbl_status.pack(anchor="w")

        self.lbl_last_msg = ttk.Label(
            frame_status, text="Poslední MIDI zpráva: -", foreground="gray"
        )
        self.lbl_last_msg.pack(anchor="w", pady=(8, 0))

    def load_file_for_all(self, filepath=None):
        if not filepath:
            filepath = filedialog.askopenfilename(
                title="Vyberte MIDI soubor",
                filetypes=[
                    ("MIDI soubory", "*.mid *.midi"),
                    ("Všechny soubory", "*.*"),
                ],
            )
        if filepath:
            self.midi_file_path = filepath
            filename = os.path.basename(filepath)
            self.lbl_file.config(text=filename)
            self.lbl_status.config(text=f"Stav: Načten soubor {filename}")
            self._inspect_file(filepath)

    def refresh_ports(self):
        try:
            ports = mido.get_output_names()
            self.combo_ports["values"] = ports
            if ports:
                self.combo_ports.current(0)
            else:
                self.combo_ports.set("")
        except Exception as e:
            messagebox.showerror("Chyba MIDI", f"Nelze načíst MIDI porty:\n{e}")

    def send_test_note(self):
        port_name = self.combo_ports.get()
        if not port_name:
            messagebox.showwarning(
                "Upozornění", "Nejprve vyberte výstupní MIDI port."
            )
            return

        def _test():
            try:
                with mido.open_output(port_name) as outport:
                    msg_on = Message("note_on", note=60, velocity=100, channel=0)
                    msg_off = Message("note_off", note=60, velocity=0, channel=0)
                    outport.send(msg_on)
                    self.root.after(
                        0,
                        lambda: self.lbl_last_msg.config(
                            text=f"Test: {msg_on}"
                        ),
                    )
                    time.sleep(0.3)
                    outport.send(msg_off)
                    self.root.after(
                        0,
                        lambda: self.lbl_last_msg.config(
                            text=f"Test dokončen: {msg_off}"
                        ),
                    )
            except Exception as e:
                self.root.after(
                    0, lambda: messagebox.showerror("Chyba portu", str(e))
                )

        threading.Thread(target=_test, daemon=True).start()

    def start_playback(self):
        if not self.midi_file_path:
            messagebox.showwarning("Upozornění", "Nejprve vyberte MIDI soubor.")
            return
        port_name = self.combo_ports.get()
        if not port_name:
            messagebox.showwarning("Upozornění", "Vyberte výstupní MIDI port.")
            return

        self.is_playing = True
        self.stop_requested = False
        self.btn_play.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.lbl_status.config(text="Stav: Přehrávám...")

        self.play_thread = threading.Thread(
            target=self._playback_worker,
            args=(self.midi_file_path, port_name),
            daemon=True,
        )
        self.play_thread.start()

    def stop_playback(self):
        if self.is_playing:
            self.stop_requested = True
            self.lbl_status.config(text="Stav: Zastavuji...")

    def _playback_worker(self, midi_path, port_name):
        active_notes = set()
        try:
            mid = MidiFile(midi_path)
            with mido.open_output(port_name) as outport:
                for msg in mid:
                    if self.stop_requested:
                        break

                    wait_time = msg.time
                    while wait_time > 0 and not self.stop_requested:
                        step = min(0.02, wait_time)
                        time.sleep(step)
                        wait_time -= step

                    if self.stop_requested:
                        break

                    if not msg.is_meta:
                        outport.send(msg)
                        if msg.type == "note_on" and msg.velocity > 0:
                            active_notes.add((msg.channel, msg.note))
                        elif msg.type == "note_off" or (
                            msg.type == "note_on" and msg.velocity == 0
                        ):
                            active_notes.discard((msg.channel, msg.note))

                        self.root.after(
                            0,
                            lambda m=msg: self.lbl_last_msg.config(
                                text=f"Poslední MIDI zpráva: {m}"
                            ),
                        )

                # Explicitní vypnutí všech aktivních not + All Notes Off (CC 123)
                for ch, note in active_notes:
                    outport.send(
                        Message("note_off", channel=ch, note=note, velocity=0)
                    )
                for ch in range(16):
                    outport.send(
                        Message("control_change", channel=ch, control=123, value=0)
                    )

        except Exception as e:
            self.root.after(
                0, lambda: messagebox.showerror("Chyba při přehrávání", str(e))
            )
        finally:
            self.root.after(0, self._on_playback_finished)

    def _on_playback_finished(self):
        self.is_playing = False
        self.btn_play.config(state="normal")
        self.btn_stop.config(state="disabled")
        if self.stop_requested:
            self.lbl_status.config(text="Stav: Zastaveno uživatelem")
        else:
            self.lbl_status.config(text="Stav: Přehrávání dokončeno")

    # =========================================================================
    # KARTA 2: VYTVOŘIT MIDI
    # =========================================================================
    def _build_creator_tab(self):
        frame_top = ttk.LabelFrame(
            self.tab_creator, text="Přidat notu nebo pomlku", padding=10
        )
        frame_top.pack(fill="x", padx=15, pady=(15, 5))

       # Výběr noty: C1 (24) až A3 (57) -> případně změňte 58 na 97 pro rozsah C1 až C7
        ttk.Label(frame_top, text="Nota:").grid(row=0, column=0, padx=5, pady=5)
        note_options = ["Pomlka (Rest)"] + [
            f"{midi_to_note_name(n)}" for n in range(24, 58)
        ]  # 24 = C1, 57 = A3
        self.combo_note = ttk.Combobox(
            frame_top, values=note_options, state="readonly", width=15
        )
        self.combo_note.set("C2 (36)")  # Výchozí vybraná nota v novém rozsahu
        self.combo_note.grid(row=0, column=1, padx=5, pady=5)

        # Délka v dobách (1.0 = čtvrťová nota)
        ttk.Label(frame_top, text="Délka (doby):").grid(
            row=0, column=2, padx=5, pady=5
        )
        self.combo_dur = ttk.Combobox(
            frame_top,
            values=["0.25 (1/16)", "0.5 (1/8)", "1.0 (1/4)", "2.0 (1/2)", "4.0 (Celá)"],
            state="readonly",
            width=12,
        )
        self.combo_dur.current(2)
        self.combo_dur.grid(row=0, column=3, padx=5, pady=5)

        # Velocity
        ttk.Label(frame_top, text="Velocity (1-127):").grid(
            row=1, column=0, padx=5, pady=5
        )
        self.spin_vel = ttk.Spinbox(frame_top, from_=1, to=127, width=8)
        self.spin_vel.set(100)
        self.spin_vel.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        # MIDI Kanál (1-16)
        ttk.Label(frame_top, text="Kanál (1-16):").grid(
            row=1, column=2, padx=5, pady=5
        )
        self.spin_ch = ttk.Spinbox(frame_top, from_=1, to=16, width=8)
        self.spin_ch.set(1)
        self.spin_ch.grid(row=1, column=3, sticky="w", padx=5, pady=5)

        btn_add = ttk.Button(
            frame_top, text="＋ Přidat do sekvence", command=self.add_note_to_seq
        )
        btn_add.grid(row=0, column=4, rowspan=2, padx=15, pady=5, sticky="ns")

        # Tabulka sekvence
        frame_list = ttk.LabelFrame(
            self.tab_creator, text="Sekvence not", padding=10
        )
        frame_list.pack(fill="both", expand=True, padx=15, pady=5)

        cols = ("idx", "note", "dur", "vel", "ch")
        self.tree_creator = ttk.Treeview(
            frame_list, columns=cols, show="headings", height=8
        )
        self.tree_creator.heading("idx", text="#")
        self.tree_creator.heading("note", text="Nota / Událost")
        self.tree_creator.heading("dur", text="Délka (doby)")
        self.tree_creator.heading("vel", text="Velocity")
        self.tree_creator.heading("ch", text="Kanál")

        self.tree_creator.column("idx", width=40, anchor="center")
        self.tree_creator.column("note", width=180, anchor="center")
        self.tree_creator.column("dur", width=120, anchor="center")
        self.tree_creator.column("vel", width=100, anchor="center")
        self.tree_creator.column("ch", width=80, anchor="center")
        self.tree_creator.pack(side="left", fill="both", expand=True)

        scroll_c = ttk.Scrollbar(
            frame_list, orient="vertical", command=self.tree_creator.yview
        )
        self.tree_creator.configure(yscrollcommand=scroll_c.set)
        scroll_c.pack(side="right", fill="y")

        # Spodní lišta pro uložení a nastavení tempa
        frame_bot = ttk.Frame(self.tab_creator, padding=10)
        frame_bot.pack(fill="x", padx=10)

        ttk.Label(frame_bot, text="Tempo (BPM):").pack(side="left", padx=(5, 5))
        self.spin_bpm = ttk.Spinbox(frame_bot, from_=30, to=300, width=6)
        self.spin_bpm.set(120)
        self.spin_bpm.pack(side="left", padx=(0, 15))

        btn_del = ttk.Button(
            frame_bot, text="Smazat vybranou", command=self.delete_selected_note
        )
        btn_del.pack(side="left", padx=5)

        btn_clear = ttk.Button(
            frame_bot, text="Vymazat vše", command=self.clear_sequence
        )
        btn_clear.pack(side="left", padx=5)

        btn_save = ttk.Button(
            frame_bot, text="💾 Uložit .mid soubor", command=self.save_created_midi
        )
        btn_save.pack(side="right", padx=5)

    def add_note_to_seq(self):
        note_str = self.combo_note.get()
        if "Pomlka" in note_str:
            note_num = -1
        else:
            note_num = int(note_str.split("(")[1].replace(")", ""))

        dur_beats = float(self.combo_dur.get().split(" ")[0])
        vel = int(self.spin_vel.get())
        ch = int(self.spin_ch.get())

        self.editor_notes.append((note_num, dur_beats, vel, ch))
        self._refresh_creator_tree()

    def delete_selected_note(self):
        selected = self.tree_creator.selection()
        if not selected:
            return
        idx = self.tree_creator.index(selected[0])
        del self.editor_notes[idx]
        self._refresh_creator_tree()

    def clear_sequence(self):
        self.editor_notes.clear()
        self._refresh_creator_tree()

    def _refresh_creator_tree(self):
        for item in self.tree_creator.get_children():
            self.tree_creator.delete(item)
        for i, (note_num, dur, vel, ch) in enumerate(self.editor_notes, start=1):
            n_label = (
                "Pomlka (Rest)"
                if note_num == -1
                else midi_to_note_name(note_num)
            )
            v_label = "-" if note_num == -1 else vel
            c_label = "-" if note_num == -1 else ch
            self.tree_creator.insert(
                "", "end", values=(i, n_label, dur, v_label, c_label)
            )

    def save_created_midi(self):
        if not self.editor_notes:
            messagebox.showwarning("Prázdná sekvence", "Nejprve přidejte alespoň jednu notu.")
            return

        filepath = filedialog.asksaveasfilename(
            title="Uložit MIDI soubor",
            defaultextension=".mid",
            filetypes=[("MIDI soubor", "*.mid")],
        )
        if not filepath:
            return

        bpm = int(self.spin_bpm.get())
        mid = MidiFile(ticks_per_beat=480)
        track = MidiTrack()
        mid.tracks.append(track)

        track.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))

        pending_rest_ticks = 0
        for note_num, dur_beats, vel, ch in self.editor_notes:
            ticks = int(dur_beats * 480)
            if note_num == -1:
                pending_rest_ticks += ticks
            else:
                midi_ch = max(0, min(15, ch - 1))
                track.append(
                    Message(
                        "note_on",
                        note=note_num,
                        velocity=vel,
                        channel=midi_ch,
                        time=pending_rest_ticks,
                    )
                )
                track.append(
                    Message(
                        "note_off",
                        note=note_num,
                        velocity=0,
                        channel=midi_ch,
                        time=ticks,
                    )
                )
                pending_rest_ticks = 0

        mid.save(filepath)
        messagebox.showinfo(
            "Uloženo",
            f"Soubor byl uložen a automaticky načten do Přehrávače i Prohlížeče:\n{filepath}",
        )
        self.load_file_for_all(filepath)

    # =========================================================================
    # KARTA 3: PROHLÍŽEČ MIDI
    # =========================================================================
    def _build_inspector_tab(self):
        frame_top = ttk.Frame(self.tab_inspector, padding=10)
        frame_top.pack(fill="x", padx=5, pady=(5, 0))

        self.lbl_inspect_info = ttk.Label(
            frame_top,
            text="Načtěte soubor pro zobrazení obsahu...",
            font=("sans-serif", 9, "bold"),
        )
        self.lbl_inspect_info.pack(side="left")

        btn_open_insp = ttk.Button(
            frame_top,
            text="Otevřít jiný .mid soubor",
            command=lambda: self.load_file_for_all(None),
        )
        btn_open_insp.pack(side="right")

        frame_table = ttk.Frame(self.tab_inspector, padding=10)
        frame_table.pack(fill="both", expand=True)

        cols = ("track", "abs_time", "delta", "type", "ch", "note", "vel")
        self.tree_inspector = ttk.Treeview(
            frame_table, columns=cols, show="headings"
        )
        self.tree_inspector.heading("track", text="Stopa")
        self.tree_inspector.heading("abs_time", text="Čas (Ticks)")
        self.tree_inspector.heading("delta", text="Delta (Ticks)")
        self.tree_inspector.heading("type", text="Typ zprávy")
        self.tree_inspector.heading("ch", text="Kanál")
        self.tree_inspector.heading("note", text="Nota / Data")
        self.tree_inspector.heading("vel", text="Velocity / Hodnota")

        self.tree_inspector.column("track", width=55, anchor="center")
        self.tree_inspector.column("abs_time", width=90, anchor="e")
        self.tree_inspector.column("delta", width=85, anchor="e")
        self.tree_inspector.column("type", width=120, anchor="center")
        self.tree_inspector.column("ch", width=60, anchor="center")
        self.tree_inspector.column("note", width=140, anchor="center")
        self.tree_inspector.column("vel", width=120, anchor="center")

        self.tree_inspector.pack(side="left", fill="both", expand=True)

        scroll_i = ttk.Scrollbar(
            frame_table, orient="vertical", command=self.tree_inspector.yview
        )
        self.tree_inspector.configure(yscrollcommand=scroll_i.set)
        scroll_i.pack(side="right", fill="y")

    def _inspect_file(self, filepath):
        for item in self.tree_inspector.get_children():
            self.tree_inspector.delete(item)

        try:
            mid = MidiFile(filepath)
            total_notes = 0

            for track_idx, track in enumerate(mid.tracks):
                abs_ticks = 0
                for msg in track:
                    abs_ticks += msg.time
                    if msg.is_meta:
                        if msg.type == "set_tempo":
                            bpm = round(mido.tempo2bpm(msg.tempo), 1)
                            self.tree_inspector.insert(
                                "",
                                "end",
                                values=(
                                    track_idx,
                                    abs_ticks,
                                    msg.time,
                                    "META: Tempo",
                                    "-",
                                    f"{bpm} BPM",
                                    "-",
                                ),
                            )
                        elif msg.type == "track_name":
                            self.tree_inspector.insert(
                                "",
                                "end",
                                values=(
                                    track_idx,
                                    abs_ticks,
                                    msg.time,
                                    "META: Název",
                                    "-",
                                    msg.name,
                                    "-",
                                ),
                            )
                    else:
                        ch = getattr(msg, "channel", None)
                        ch_str = str(ch + 1) if ch is not None else "-"

                        if msg.type in ("note_on", "note_off"):
                            if msg.type == "note_on" and msg.velocity > 0:
                                total_notes += 1
                            note_str = midi_to_note_name(msg.note)
                            vel_str = str(msg.velocity)
                        elif msg.type == "control_change":
                            note_str = f"CC #{msg.control}"
                            vel_str = str(msg.value)
                        elif msg.type == "program_change":
                            note_str = f"Program #{msg.program}"
                            vel_str = "-"
                        else:
                            note_str = "-"
                            vel_str = "-"

                        self.tree_inspector.insert(
                            "",
                            "end",
                            values=(
                                track_idx,
                                abs_ticks,
                                msg.time,
                                msg.type,
                                ch_str,
                                note_str,
                                vel_str,
                            ),
                        )

            duration_sec = round(mid.length, 2)
            filename = os.path.basename(filepath)
            self.lbl_inspect_info.config(
                text=f"Soubor: {filename} | Délka: {duration_sec} s | Stopy: {len(mid.tracks)} | TPB: {mid.ticks_per_beat} | Počet not: {total_notes}"
            )
        except Exception as e:
            messagebox.showerror(
                "Chyba čtení MIDI", f"Nepodařilo se analyzovat soubor:\n{e}"
            )


if __name__ == "__main__":
    root = tk.Tk()
    app = MidiStudioApp(root)
    root.mainloop()