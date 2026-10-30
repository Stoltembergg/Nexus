#!/usr/bin/env python3
"""GTK manual controller for the isolated controlled reopen probe."""
import argparse
import importlib.util
from pathlib import Path
import threading

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk


def load_probe(path, configured_prefix):
    spec = importlib.util.spec_from_file_location('controlled_probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ControlledProbe(configured_prefix)


class ControlledApp:
    def __init__(self, probe):
        self.probe = probe
        self.busy = False
        self.started = False
        self.closed = False
        self.window = Gtk.Window(title='Prova manual de reabertura')
        self.window.set_border_width(24)
        self.window.set_default_size(560, 440)
        self.window.connect('delete-event', self.on_delete)
        self.window.connect('destroy', self.on_destroy)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.window.add(box)
        title = Gtk.Label()
        title.set_markup('<span size="xx-large" weight="bold">Prova manual</span>')
        title.set_xalign(0)
        box.pack_start(title, False, False, 0)
        warning = Gtk.Label(label=(
            'A prova cria e retém um prefixo descartável; ele não será apagado.\n'
            'Nada inicia, consulta ou altera qualquer sessão Riot.\n'
            'Requer DISPLAY e abrir este app fora de NoNewPrivs (NoNewPrivs=0).'))
        warning.set_xalign(0)
        warning.set_line_wrap(True)
        box.pack_start(warning, False, False, 0)
        self.status = Gtk.Label(label='Aguardando pré-requisitos e início explícito.')
        self.status.set_xalign(0)
        self.status.set_line_wrap(True)
        box.pack_start(self.status, True, True, 0)
        self.start_button = Gtk.Button(label='Iniciar prova')
        self.reopen_button = Gtk.Button(label='Reabrir')
        self.stop_button = Gtk.Button(label='Encerrar cooperativamente')
        for button in (self.start_button, self.reopen_button, self.stop_button):
            box.pack_start(button, False, False, 0)
        self.start_button.connect('clicked', lambda *_: self.run_action('start'))
        self.reopen_button.connect('clicked', lambda *_: self.run_action('reopen'))
        self.stop_button.connect('clicked', lambda *_: self.run_action('stop'))
        self.reopen_button.set_sensitive(False)
        self.stop_button.set_sensitive(False)
        self.exit_button = Gtk.Button(label='Sair mesmo assim…')
        self.exit_button.connect('clicked', self.confirm_exit)
        box.pack_start(self.exit_button, False, False, 0)
        self.refresh_prerequisites()
        self.window.show_all()

    def refresh_prerequisites(self):
        no_new_privs = None
        try:
            for line in Path('/proc/self/status').read_text().splitlines():
                if line.startswith('NoNewPrivs:'):
                    no_new_privs = line.split(':', 1)[1].strip() == '0'
        except OSError:
            pass
        ok = bool(__import__('os').environ.get('DISPLAY')) and no_new_privs
        self.start_button.set_sensitive(ok and not self.started and not self.busy)
        if not ok:
            self.status.set_text('Indisponível: abra com DISPLAY definido e NoNewPrivs=0.')

    def run_action(self, action):
        if self.busy or self.closed:
            return
        self.busy = True
        self.refresh_prerequisites()
        for button in (self.start_button, self.reopen_button, self.stop_button):
            button.set_sensitive(False)
        self.status.set_text({'start': 'Iniciando e aguardando observação…',
                              'reopen': 'Verificando fechamento X e reabertura…',
                              'stop': 'Solicitando encerramento cooperativo…'}[action])

        def worker():
            try:
                result = getattr(self.probe, action)()
                message = f'{action.capitalize()} concluído; resultado observado:\n{result}'
                success = True
            except Exception as exc:
                message = f'Falha visível ({action}): {type(exc).__name__}: {exc}'
                success = False
            GLib.idle_add(self.finish_action, action, message, success)

        threading.Thread(target=worker, name='controlled-probe-' + action, daemon=True).start()

    def finish_action(self, action, message, success):
        self.busy = False
        self.status.set_text(message)
        if action == 'start' and success:
            self.started = True
            self.status.set_text(message + '\nAgora clique no X desta janela de prova; depois use Reabrir aqui.')
        if action == 'stop' and success:
            self.closed = True
        self.stop_button.set_sensitive(self.probe_is_alive() and not self.busy)
        if not self.closed:
            self.reopen_button.set_sensitive(self.started and not self.busy)
            self.stop_button.set_sensitive((self.started or self.probe_is_alive()) and not self.busy)
            if not self.started:
                self.refresh_prerequisites()
        return GLib.SOURCE_REMOVE

    def probe_is_alive(self):
        process = getattr(self.probe, 'process', None)
        return process is not None and process.poll() is None

    def confirm_exit(self, *_):
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True,
            message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.NONE,
            text='Sair sem encerrar a prova?')
        dialog.format_secondary_text(
            'O processo e o prefixo podem permanecer retidos. Nenhum processo será morto. '
            'Se possível, use Encerrar cooperativamente antes de sair.')
        dialog.add_button('Voltar', Gtk.ResponseType.CANCEL)
        dialog.add_button('Sair', Gtk.ResponseType.YES)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            self.window.destroy()

    def on_destroy(self, *_):
        Gtk.main_quit()

    def on_delete(self, *_):
        if self.closed:
            return False
        if self.busy:
            self.status.set_text('Ação em andamento; aguarde antes de sair.')
            return True
        if self.probe_is_alive():
            self.status.set_text('A prova ainda pode estar ativa. Use “Encerrar cooperativamente” ou “Sair mesmo assim…”.')
            return True
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('configured_prefix', help='prefixo configurado usado apenas para verificar isolamento')
    args = parser.parse_args()
    probe_path = Path(__file__).with_name('controlled.py')
    app = ControlledApp(load_probe(probe_path, args.configured_prefix))
    Gtk.main()


if __name__ == '__main__':
    main()
