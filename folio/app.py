#!/usr/bin/python3
"""Fólio — a small native Linux Markdown reader using the system WebKit."""

import json
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit2

from render import render_document
from document_io import LocalDocument

ROOT = Path(__file__).resolve().parent.parent
APP_ID = "io.github.folio.Reader"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "folio" / "settings.json"


class Reader(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.window = None
        self.ready = False
        self.path = None
        self.monitor = None
        self.reload_timer = 0
        self.pending = None
        self.document = None
        self.editor = None
        self.editing = False
        self.prompting = False
        self.settings = {"theme": "light", "zoom": 1, "focus": False, "recent": []}
        try:
            saved = json.loads(CONFIG.read_text())
            for key in self.settings:
                if key in saved:
                    self.settings[key] = saved[key]
        except (OSError, ValueError, TypeError):
            pass
        if self.settings["theme"] not in {"light", "dark", "system"}:
            self.settings["theme"] = "light"
        if not isinstance(self.settings["zoom"], (int, float)):
            self.settings["zoom"] = 1
        self.settings["zoom"] = min(1.5, max(0.8, self.settings["zoom"]))
        self.settings["recent"] = [p for p in self.settings["recent"] if isinstance(p, str)][:12] if isinstance(self.settings["recent"], list) else []

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Fólio")
        self.window.set_default_size(1280, 900)
        self.window.set_icon_from_file(str(ROOT / "assets" / "folio.svg"))
        header = Gtk.HeaderBar(title="Fólio", show_close_button=True)
        header.set_decoration_layout("menu:minimize,maximize,close")
        self.window.set_titlebar(header)
        self.header = header
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            headerbar { min-height: 28px; padding: 0 8px; box-shadow: none; border-bottom: 1px solid alpha(@theme_fg_color, .08); }
            headerbar .title { font-size: 12px; font-weight: 500; }
            .editor-toolbar { padding: 12px 18px; border-bottom: 1px solid alpha(@theme_fg_color, .1); }
            .editor-toolbar button { border-radius: 6px; }
            .editor-find { padding: 8px 20px; border-bottom: 1px solid alpha(@theme_fg_color, .1); }
            .editor-footer { padding: 9px 22px; font-size: 11px; color: alpha(@theme_fg_color, .65); border-top: 1px solid alpha(@theme_fg_color, .1); }
        """)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        manager = WebKit2.UserContentManager()
        manager.register_script_message_handler("folio")
        manager.connect("script-message-received::folio", self.on_message)
        self.web = WebKit2.WebView.new_with_user_content_manager(manager)
        web_settings = self.web.get_settings()
        web_settings.set_enable_developer_extras(False)
        web_settings.set_enable_html5_database(False)
        web_settings.set_enable_html5_local_storage(False)
        web_settings.set_allow_file_access_from_file_urls(True)
        web_settings.set_allow_universal_access_from_file_urls(False)
        web_settings.set_enable_write_console_messages_to_stdout(False)
        self.web.connect("decide-policy", self.on_policy)
        self.web.connect("context-menu", lambda *_: True)
        self.web.connect("load-changed", self.on_loaded)
        self.web.drag_dest_set(Gtk.DestDefaults.ALL, [Gtk.TargetEntry.new("text/uri-list", 0, 0)], Gdk.DragAction.COPY)
        self.web.connect("drag-data-received", self.on_drop)
        self.window.connect("key-press-event", self.on_key)
        self.window.connect("delete-event", self.on_close)
        self.stack = Gtk.Stack()
        self.stack.add_named(self.web, "reading")
        self.window.add(self.stack)
        self.apply_native_theme()
        self.web.load_uri((ROOT / "ui" / "index.html").as_uri())
        self.window.show_all()

    def do_open(self, files, _count, _hint):
        self.do_activate()
        if files:
            path = files[0].get_path()
            if path:
                if self.ready:
                    self.open_file(path)
                else:
                    self.pending = path

    def on_loaded(self, _web, event):
        if event == WebKit2.LoadEvent.FINISHED:
            self.ready = True
            self.send("settings", self.settings)
            self.send("document", render_document((ROOT / "welcome.md").read_text()))
            if self.pending:
                path, self.pending = self.pending, None
                self.open_file(path)

    def send(self, event, payload):
        if self.ready:
            script = f"window.folio.receive({json.dumps(event)}, {json.dumps(payload, ensure_ascii=True)});"
            self.web.evaluate_javascript(script, -1, None, None, None, None, None)

    def save_settings(self):
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            temporary = CONFIG.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2))
            temporary.replace(CONFIG)
        except OSError as error:
            self.send("toast", f"Não foi possível salvar as preferências: {error.strerror}")

    def apply_native_theme(self):
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", self.settings["theme"] == "dark")
        self.update_editor_appearance()

    def update_editor_appearance(self):
        if self.editor:
            settings = Gtk.Settings.get_default()
            dark = settings.get_property("gtk-application-prefer-dark-theme") or "dark" in settings.get_property("gtk-theme-name").lower()
            self.editor.appearance(dark, self.settings["zoom"])

    def toggle_theme(self):
        self.settings["theme"] = "light" if self.settings["theme"] == "dark" else "dark"
        self.apply_native_theme()
        self.save_settings()
        self.send("settings", self.settings)

    def notify(self, message, *, warning=False):
        if self.editing:
            self.editor.show_message(message, warning=warning)
        else:
            self.send("toast", message)

    def update_title(self):
        title = f"{self.path.name} — Fólio" if self.path else "Fólio"
        if self.editing and self.editor.modified:
            title = "• " + title
        self.window.set_title(title)
        self.header.set_title(title)

    def remember_path(self):
        path = str(self.path)
        self.settings["recent"] = [path] + [p for p in self.settings["recent"] if p != path][:11]
        self.save_settings()
        self.send("settings", self.settings)

    def render_current(self, reload=False):
        document = render_document(self.document.text, self.path)
        document["reload"] = reload
        self.send("document", document)

    def stop_reload_timer(self):
        if self.reload_timer:
            GLib.source_remove(self.reload_timer)
            self.reload_timer = 0

    def watch_current_file(self):
        self.stop_reload_timer()
        if self.monitor:
            self.monitor.cancel()
        # Monitor the directory too: editors commonly replace the inode on save.
        self.monitor = Gio.File.new_for_path(str(self.path.parent)).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.monitor.connect("changed", self.on_file_changed)

    def open_file(self, filename, reload=False):
        if reload:
            return self.reload_from_disk()
        if not self.confirm_unsaved("abrir outro documento"):
            return False
        try:
            document = LocalDocument.load(filename)
        except (OSError, UnicodeError, ValueError, GLib.Error) as error:
            self.notify(f"Não foi possível abrir {Path(filename).name}: {error}", warning=True)
            return False
        self.document, self.path = document, document.path
        self.editing = False
        self.stack.set_visible_child_name("reading")
        self.update_title()
        self.remember_path()
        self.render_current()
        self.watch_current_file()
        return True

    def on_file_changed(self, _monitor, file, other, _event):
        paths = {f.get_path() for f in (file, other) if f}
        if str(self.path) in paths:
            if self.reload_timer:
                GLib.source_remove(self.reload_timer)
            self.reload_timer = GLib.timeout_add(250, self.reload_document)

    def reload_document(self):
        self.reload_timer = 0
        if self.document and self.document.has_changed():
            self.reload_from_disk()
        return False

    def reload_from_disk(self, manual=False, discard=False):
        if not self.document:
            return False
        if self.editing and self.editor.modified and not discard:
            if not manual:
                self.editor.show_message("O arquivo mudou fora do Fólio. Suas edições foram preservadas; ao salvar, você poderá escolher como continuar.", warning=True, reload=True)
                return False
            response = self.ask("Recarregar o arquivo do disco?", "Suas alterações não salvas serão descartadas.",
                                [("Cancelar", Gtk.ResponseType.CANCEL), ("Descartar e recarregar", Gtk.ResponseType.REJECT)])
            if response != Gtk.ResponseType.REJECT:
                return False
        try:
            document = LocalDocument.load(self.path)
        except (OSError, UnicodeError, ValueError, GLib.Error) as error:
            self.notify(f"Não foi possível recarregar: {error}", warning=True)
            return False
        self.document = document
        if self.editing:
            self.editor.load(document)
        self.update_title()
        self.render_current(reload=True)
        return True

    def start_editing(self):
        if self.editing:
            return self.return_to_reading()
        if not self.document:
            self.notify("Abra um arquivo Markdown para começar a editar.")
            return False
        if self.document.has_changed() and not self.reload_from_disk():
            return False
        if self.editor is None:
            try:
                from editor import MarkdownEditor
            except (ImportError, ValueError):
                self.notify("Para editar, instale o GtkSourceView: sudo apt install gir1.2-gtksource-4")
                return False
            self.editor = MarkdownEditor(save=self.save_document, save_as=lambda: self.save_document(save_as=True),
                                         back=self.return_to_reading, changed=self.update_title,
                                         reload=lambda: self.reload_from_disk(manual=True), theme=self.toggle_theme)
            self.stack.add_named(self.editor, "editor")
        self.editor.load(self.document)
        self.update_editor_appearance()
        self.editing = True
        self.stack.set_visible_child_name("editor")
        self.editor.view.grab_focus()
        self.update_title()
        return True

    def return_to_reading(self):
        if not self.editing or not self.confirm_unsaved("voltar à leitura"):
            return False
        # Reread on discard as well, so external changes are not hidden.
        if not self.reload_from_disk(discard=True):
            return False
        self.editing = False
        self.stack.set_visible_child_name("reading")
        self.update_title()
        return True

    def show_welcome(self):
        if not self.confirm_unsaved("abrir as boas-vindas"):
            return False
        self.stop_reload_timer()
        if self.monitor:
            self.monitor.cancel()
            self.monitor = None
        self.path = self.document = None
        self.editing = False
        self.stack.set_visible_child_name("reading")
        self.update_title()
        self.send("document", render_document((ROOT / "welcome.md").read_text()))
        return True

    def ask(self, title, detail, buttons):
        if self.prompting:
            return Gtk.ResponseType.CANCEL
        self.prompting = True
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.NONE, text=title)
        dialog.format_secondary_text(detail)
        for label, response in buttons:
            dialog.add_button(label, response)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        try:
            return dialog.run()
        finally:
            dialog.destroy()
            self.prompting = False

    def confirm_unsaved(self, action):
        if not self.editing or not self.editor.modified:
            return True
        response = self.ask("Salvar as alterações antes de " + action + "?", self.path.name,
                            [("Cancelar", Gtk.ResponseType.CANCEL), ("Descartar", Gtk.ResponseType.REJECT), ("Salvar", Gtk.ResponseType.ACCEPT)])
        if response == Gtk.ResponseType.ACCEPT:
            return self.save_document()
        return response == Gtk.ResponseType.REJECT

    def choose_save_path(self):
        dialog = Gtk.FileChooserNative.new("Salvar Markdown como", self.window, Gtk.FileChooserAction.SAVE, "Salvar", "Cancelar")
        dialog.set_do_overwrite_confirmation(True)
        dialog.set_current_folder(str(self.path.parent))
        dialog.set_current_name(self.path.name)
        try:
            return dialog.get_filename() if dialog.run() == Gtk.ResponseType.ACCEPT else None
        finally:
            dialog.destroy()

    def resolve_save_conflict(self):
        response = self.ask("O arquivo mudou fora do Fólio", "Recarregar descarta suas edições. Salvar uma cópia mantém os dois conteúdos; substituir grava suas edições sobre o arquivo do disco.",
                            [("Cancelar", Gtk.ResponseType.CANCEL), ("Recarregar do disco", 1), ("Salvar cópia…", 2), ("Substituir arquivo", 3)])
        if response == 1:
            return self.reload_from_disk(discard=True)
        if response == 2:
            return self.save_document(save_as=True)
        if response == 3:
            return self.save_document(overwrite=True)
        return False

    def save_document(self, save_as=False, target=None, overwrite=False):
        if not self.editing:
            return False
        if save_as and target is None:
            target = self.choose_save_path()
            if target is None:
                return False
        same_file = target is None or Path(target).expanduser().resolve() == self.path
        if same_file and not overwrite and self.document.has_changed():
            return self.resolve_save_conflict()
        if same_file and not self.editor.modified and not overwrite:
            return True
        try:
            self.document.save(self.editor.text(), target=target, overwrite=overwrite)
        except GLib.Error as error:
            if error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.WRONG_ETAG):
                return self.resolve_save_conflict()
            self.notify(f"Não foi possível salvar: {error.message}", warning=True)
            return False
        except (OSError, ValueError, UnicodeError) as error:
            self.notify(f"Não foi possível salvar: {error}", warning=True)
            return False
        self.path = self.document.path
        self.editor.saved(self.document)
        self.update_title()
        self.remember_path()
        self.render_current(reload=True)
        self.watch_current_file()
        return True

    def on_close(self, *_):
        return not self.confirm_unsaved("fechar")

    def choose_file(self):
        dialog = Gtk.FileChooserNative.new("Abrir Markdown", self.window, Gtk.FileChooserAction.OPEN, "Abrir", "Cancelar")
        markdown = Gtk.FileFilter()
        markdown.set_name("Markdown e texto (*.md, *.markdown, *.txt)")
        for pattern in ("*.[mM][dD]", "*.markdown", "*.mdown", "*.mkd", "*.txt"):
            markdown.add_pattern(pattern)
        dialog.add_filter(markdown)
        all_files = Gtk.FileFilter()
        all_files.set_name("Todos os arquivos")
        all_files.add_pattern("*")
        dialog.add_filter(all_files)
        if self.path:
            dialog.set_current_folder(str(self.path.parent))
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            self.open_file(dialog.get_filename())
        dialog.destroy()

    def on_message(self, _manager, result):
        try:
            message = json.loads(result.get_js_value().to_string())
            action, value = message.get("action"), message.get("value")
            if action == "open":
                self.choose_file()
            elif action == "welcome":
                self.show_welcome()
            elif action == "edit":
                self.start_editing()
            elif action == "recent" and value in self.settings["recent"]:
                self.open_file(value)
            elif action == "reload":
                self.reload_from_disk(manual=True)
            elif action == "theme" and value in {"light", "dark", "system"}:
                self.settings["theme"] = value
                self.apply_native_theme()
                self.save_settings()
            elif action == "focus":
                self.settings["focus"] = bool(value)
                self.save_settings()
            elif action == "zoom":
                self.settings["zoom"] = max(0.8, min(1.5, float(value)))
                self.update_editor_appearance()
                self.save_settings()
            elif action == "copy":
                Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(str(value), -1)
            elif action == "reveal" and self.path:
                Gio.AppInfo.launch_default_for_uri(self.path.parent.as_uri(), None)
            elif action == "clear-recent":
                self.settings["recent"] = []
                self.save_settings()
                self.send("settings", self.settings)
        except (ValueError, TypeError, GLib.Error) as error:
            self.send("toast", str(error))

    def on_policy(self, _web, decision, kind):
        if kind not in {WebKit2.PolicyDecisionType.NAVIGATION_ACTION, WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION}:
            return False
        navigation = decision.get_navigation_action()
        uri = navigation.get_request().get_uri()
        shell_uri = (ROOT / "ui" / "index.html").as_uri()
        if uri.split("#")[0] == shell_uri:
            return False
        decision.ignore()
        parsed = urlsplit(uri)
        # Only a deliberate link activation may leave the reader.
        if navigation.get_navigation_type() == WebKit2.NavigationType.LINK_CLICKED:
            if parsed.scheme == "file":
                path = Path(unquote(parsed.path))
                if path.suffix.lower() in {".md", ".markdown", ".mdown", ".mkd", ".txt"}:
                    opened = self.open_file(path)
                    if opened and parsed.fragment:
                        self.send("anchor", unquote(parsed.fragment))
                else:
                    self.send("toast", "Este link não é um arquivo Markdown. Use o gerenciador de arquivos para abri-lo.")
            elif parsed.scheme in {"http", "https", "mailto"}:
                Gio.AppInfo.launch_default_for_uri(uri, None)
        return True

    def on_drop(self, _widget, context, _x, _y, selection, _info, timestamp):
        uris = selection.get_uris() or []
        if uris:
            path = Gio.File.new_for_uri(uris[0]).get_path()
            if path:
                self.open_file(path)
        Gtk.drag_finish(context, bool(uris), False, timestamp)

    def on_key(self, _window, event):
        if self.prompting:
            return False
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        key = Gdk.keyval_name(event.keyval).lower()
        if ctrl and key == "o":
            self.choose_file()
        elif ctrl and key == "e":
            self.start_editing()
        elif ctrl and key == "s":
            self.save_document(save_as=shift)
        elif ctrl and key == "r":
            self.reload_from_disk(manual=True)
        elif self.editing and ctrl and key in {"z", "y"}:
            self.editor.redo() if shift or key == "y" else self.editor.undo()
        elif ctrl and key == "f" and shift:
            self.send("command", "focus")
        elif ctrl and key == "f":
            self.editor.show_find() if self.editing else self.send("command", "find")
        elif ctrl and key in {"plus", "equal", "kp_add", "minus", "kp_subtract", "0", "kp_0"}:
            if self.editing:
                self.settings["zoom"] = 1 if key in {"0", "kp_0"} else round(max(.8, min(1.5, self.settings["zoom"] + (-.1 if key in {"minus", "kp_subtract"} else .1))), 1)
                self.update_editor_appearance()
                self.save_settings()
                self.send("settings", self.settings)
            else:
                self.send("command", "zoom-reset" if key in {"0", "kp_0"} else "zoom-out" if key in {"minus", "kp_subtract"} else "zoom-in")
        elif key == "escape":
            if self.editing:
                if not self.editor.find_bar.get_visible():
                    return False
                self.editor.close_find()
            else:
                self.send("command", "escape")
        else:
            return False
        return True


if __name__ == "__main__":
    import sys
    raise SystemExit(Reader().run(sys.argv))
