#!/usr/bin/env python3
"""Graphical launcher for the Riot Client session running under Darling.

The window offers the same operations as scripts/riot-launcher.sh and shows
the state of the session. Every path is derived from this file, so the
launcher works from any checkout.
"""
import os
from pathlib import Path
import subprocess
import sys
import threading

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib, Gtk  # noqa: E402
except (ImportError, ValueError) as error:  # pragma: no cover - depends on the host
    ROOT = Path(__file__).resolve().parents[1]
    LAUNCHER = ROOT / "scripts/riot-launcher.sh"
    print(
        "The graphical launcher needs PyGObject (python3-gi) and GTK 3.\n"
        f"Details: {error}\n"
        "Install the GTK 3 bindings of your distribution, or use the terminal "
        f"launcher: {LAUNCHER} {{start|stop|restart|status}}",
        file=sys.stderr,
    )
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/riot-launcher.sh"

STATUS_TEXT = {
    "stopped": "Parado",
    "starting": "Iniciando...",
    "running": "Rodando",
    "stopping": "Parando...",
    "error": "Erro",
}

STATUS_COLOR = {
    "running": "#2e7d32",
    "stopped": "#c62828",
    "starting": "#ef6c00",
    "stopping": "#ef6c00",
    "error": "#c62828",
}


class LauncherWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="Riot Client (Darling)")
        self.set_default_size(400, 320)
        self.set_border_width(18)
        self._status = "stopped"
        self._busy = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.add(box)

        title = Gtk.Label()
        title.set_markup("<span weight='bold' size='large'>Riot Client</span>")
        title.set_justify(Gtk.Justification.CENTER)
        box.pack_start(title, False, False, 0)

        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.status_label = Gtk.Label()
        self.status_label.set_halign(Gtk.Align.CENTER)
        status_box.pack_start(Gtk.Label(label="Status:"), False, False, 0)
        status_box.pack_start(self.status_label, True, True, 0)
        box.pack_start(status_box, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid.set_margin_top(6)

        self.btn_start = Gtk.Button(label="Iniciar")
        self.btn_stop = Gtk.Button(label="Parar")
        self.btn_restart = Gtk.Button(label="Reiniciar")
        self.btn_refresh = Gtk.Button(label="Atualizar status")

        for button in (self.btn_start, self.btn_stop, self.btn_restart, self.btn_refresh):
            button.set_hexpand(True)

        self.btn_start.connect("clicked", self.on_start)
        self.btn_stop.connect("clicked", self.on_stop)
        self.btn_restart.connect("clicked", self.on_restart)
        self.btn_refresh.connect("clicked", self.on_refresh)

        grid.attach(self.btn_start, 0, 0, 1, 1)
        grid.attach(self.btn_stop, 1, 0, 1, 1)
        grid.attach(self.btn_restart, 0, 1, 2, 1)
        grid.attach(self.btn_refresh, 0, 2, 2, 1)
        box.pack_start(grid, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.log_buffer = self.log_view.get_buffer()
        scroller.add(self.log_view)
        box.pack_start(scroller, True, True, 0)

        self.show_all()
        self._apply_status()
        self.refresh_status()

    # -- helpers ---------------------------------------------------------
    def log(self, text):
        GLib.idle_add(self._append_log, text)

    def _append_log(self, text):
        end = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end, text + "\n")
        self.log_view.scroll_to_iter(self.log_buffer.get_end_iter(), 0.0, True, 0.0, 1.0)
        return False

    def _set_status(self, status):
        self._status = status
        GLib.idle_add(self._apply_status)
        return False

    def _apply_status(self):
        text = STATUS_TEXT.get(self._status, self._status)
        color = STATUS_COLOR.get(self._status, "#000000")
        self.status_label.set_markup(
            f"<span weight='bold' size='medium' foreground='{color}'>{text}</span>")
        busy = self._busy
        running = self._status == "running"
        self.btn_start.set_sensitive(not busy and not running)
        self.btn_stop.set_sensitive(not busy and running)
        self.btn_restart.set_sensitive(not busy)
        self.btn_refresh.set_sensitive(not busy)
        return False

    def _set_busy(self, busy):
        self._busy = busy
        GLib.idle_add(self._apply_status)
        return False

    def _run(self, arguments):
        try:
            return subprocess.run(
                [str(LAUNCHER), *arguments],
                capture_output=True, text=True, cwd=str(ROOT), timeout=180,
            )
        except subprocess.TimeoutExpired:
            self.log("Tempo esgotado ao executar o comando.")
            return None
        except OSError as error:
            self.log(f"Não foi possível executar o launcher: {error}")
            return None

    def _worker(self, arguments, status_during, label):
        def work():
            self.log(f">>> {label}")
            GLib.idle_add(self._set_busy, True)
            GLib.idle_add(self._set_status, status_during)
            result = self._run(arguments)
            if result is None:
                GLib.idle_add(self._set_status, "error")
                GLib.idle_add(self._set_busy, False)
                return
            for line in (result.stdout or "").splitlines():
                self.log(line)
            for line in (result.stderr or "").splitlines():
                self.log(line)
            if result.returncode == 0:
                GLib.idle_add(self._set_status, "running" if arguments[0] != "stop" else "stopped")
            else:
                GLib.idle_add(self._set_status, "error")
            GLib.idle_add(self._set_busy, False)
        threading.Thread(target=work, daemon=True).start()

    # -- actions ---------------------------------------------------------
    def on_start(self, _button):
        self._worker(["start"], "starting", "Iniciando o Riot Client...")

    def on_stop(self, _button):
        self._worker(["stop"], "stopping", "Encerrando a sessão...")

    def on_restart(self, _button):
        self._worker(["restart"], "stopping", "Reiniciando o Riot Client...")

    def on_refresh(self, _button):
        self.refresh_status()

    def refresh_status(self):
        def work():
            result = self._run(["status"])
            if result is None:
                GLib.idle_add(self._set_status, "error")
                return
            GLib.idle_add(self._set_status,
                          "running" if "Darling server: RUNNING" in result.stdout else "stopped")
        threading.Thread(target=work, daemon=True).start()


def main():
    if not LAUNCHER.is_file():
        print(f"launcher not found: {LAUNCHER}", file=sys.stderr)
        return 1
    window = LauncherWindow()
    window.connect("destroy", Gtk.main_quit)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
