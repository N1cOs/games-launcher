import tkinter as tk
import dataclasses
import subprocess
import threading
import time
import datetime
import logging
import signal
import os

from tkinter import messagebox
from typing import List


class FileDurationStorage:
    TIME_IDX = 0
    DATE_IDX = 1
    DURATION_IDX = 2

    log: logging.Logger
    duration: datetime.timedelta
    file_name: str
    need_flush: bool

    def __init__(self, file_name: str) -> None:
        log = logging.getLogger("FileDurationStorage")

        try:
            total_duration = datetime.timedelta(seconds=0)
            today = datetime.datetime.now().date()
            with open(file_name, "r") as file:
                lines = file.readlines()
                if len(lines) > 0:
                    parts = lines[-1].split(",")

                    date_str = parts[self.DATE_IDX]
                    date = datetime.date.fromisoformat(date_str)

                    duration_str = parts[self.DURATION_IDX]
                    duration = datetime.timedelta(seconds=float(duration_str))

                    if date == today:
                        total_duration = duration
        except FileNotFoundError:
            log.info("did not find db file, will create a new one")
        else:    
            log.info(f"loaded db into memory: date={today}, duration={total_duration}")

        self.log = log
        self.duration = total_duration
        self.file_name = file_name
        self.need_flush = False

    def get_duration(self) -> datetime.timedelta:
        return self.duration

    def add_duration(self, duration: datetime.timedelta) -> datetime.timedelta:
        self.log.debug(f"adding duration on date: duration={duration}, total_duration={self.duration}")
        self.duration += duration
        
        self.need_flush = True
        return self.duration
    
    def flush(self) -> None:
        if not self.need_flush:
            return
        
        with open(self.file_name, "a") as file:
            dt = datetime.datetime.now()
            file.write(f"{dt},{dt.date().isoformat()},{self.duration.seconds}\n")
            self.log.info(f"wrote db in file: duration={self.duration}")
        
        self.need_flush = False

@dataclasses.dataclass
class GameItem:
    name: str
    executable: str

class Launcher:
    DAY_TIME_LIMIT = datetime.timedelta(hours=1)
    
    log: logging.Logger
    store: FileDurationStorage
    games: List[GameItem]
    has_active_game: bool

    def __init__(self, store: FileDurationStorage, games: List[GameItem]) -> None:
        self.store = store
        self.games = games
        
        self.log = logging.getLogger("Launcher")
        self.has_active_game = False
    
    def on_select_game(self, event):
        self.log.debug(f"selected game: event={event}")
        if self.has_active_game:
            return
        
        selection = event.widget.curselection()
        if selection is None:
            return
        
        idx = selection[0]
        if idx >= len(self.games):
            return
        
        if self.store.get_duration() >= self.DAY_TIME_LIMIT:
            self._show_error()
            return
        
        self.has_active_game = True
        th = threading.Thread(target=lambda: self._run_game(self.games[idx].executable))
        th.start()

    def on_exit(self):
        self.log.info("received exit signal")
        self.store.flush()
    
    def _run_game(self, executable: str):
        self.log.info(f"started game process: executable={executable}")
        proc = subprocess.Popen(executable, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        poll_interval = datetime.timedelta(seconds=1)
        while True:
            elapsed = self.store.add_duration(poll_interval)
            if elapsed >= self.DAY_TIME_LIMIT:
                self.log.info("time is out, killing process")
                proc.send_signal(signal.SIGTERM)

            
            exit_code = proc.poll()
            if exit_code is not None:
                break

            time.sleep(poll_interval.seconds)
        
        self.store.flush()
        self.has_active_game = False
        if proc.returncode != 0:
            self._show_error()

    def _show_error(self):
        messagebox.showerror(title="Ошибка", message="Севун, время на сегодня закончилось")
    
def main():
    base_dir = os.path.dirname(os.path.realpath(__file__))
    
    log_file = os.path.join(base_dir, "launcher.logs")
    logging.basicConfig(level=logging.INFO, filename=log_file, filemode="a", format="%(asctime)s %(levelname)s %(message)s")

    try:
        durations_file = os.path.join(base_dir, "durations.csv")
        store = FileDurationStorage(durations_file)
        games = [
            GameItem("Steam", "C:\Program Files (x86)\Steam\steam.exe")
        ]
        launcher = Launcher(store, games)
    except Exception:
         logging.error("fatal init error", exc_info=True)
         return

    root = tk.Tk()
    root.title("Games Launcher")
    root.geometry("500x500")

    listbox = tk.Listbox(root)
    listbox.pack(side="top", fill="both", expand=True)
    for i, game in enumerate(games):
        listbox.insert(i, game.name)
    listbox.bind("<<ListboxSelect>>", launcher.on_select_game)

    def on_exit():
        launcher.on_exit()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_exit)

    try:
        root.mainloop()
    except Exception as e:
        logging.error("fatal run error", exc_info=True)

if __name__ == "__main__":
    main()
