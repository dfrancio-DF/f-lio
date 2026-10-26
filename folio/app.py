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
        css.load_from_data(b"headerbar { min-height: 28px; padding: 0 8px; box-shadow: none; border-bottom: 1px solid alpha(@theme_fg_color, .08); } headerbar .title { font-size: 12px; font-weight: 500; }")
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
        self.window.add(self.web)
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

    def open_file(self, filename, reload=False):
        path = Path(filename).expanduser().resolve()
        try:
            if path.stat().st_size > 20 * 1024 * 1024:
                raise ValueError("Este arquivo é muito grande (limite de 20 MB).")
            source = path.read_text(encoding="utf-8-sig")
            document = render_document(source, path)
        except (OSError, UnicodeError, ValueError) as error:
            self.send("toast", f"Não foi possível abrir {path.name}: {error}")
            return
        document["reload"] = reload
        self.path = path
        self.window.set_title(f"{path.name} — Fólio")
        self.header.set_title(f"{path.name} — Fólio")
        self.settings["recent"] = [str(path)] + [p for p in self.settings["recent"] if p != str(path)][:11]
        self.save_settings()
        self.send("settings", self.settings)
        self.send("document", document)
        if self.monitor:
            self.monitor.cancel()
        # Monitor the directory too: editors commonly replace the inode on save.
        self.monitor = Gio.File.new_for_path(str(path.parent)).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.monitor.connect("changed", self.on_file_changed)

    def on_file_changed(self, _monitor, file, other, _event):
        paths = {f.get_path() for f in (file, other) if f}
        if str(self.path) in paths:
            if self.reload_timer:
                GLib.source_remove(self.reload_timer)
            self.reload_timer = GLib.timeout_add(250, self.reload_document)

    def reload_document(self):
        self.reload_timer = 0
        if self.path:
            self.open_file(self.path, reload=True)
        return False

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
                if self.monitor:
                    self.monitor.cancel()
                    self.monitor = None
                self.path = None
                self.window.set_title("Fólio")
                self.header.set_title("Fólio")
                self.send("document", render_document((ROOT / "welcome.md").read_text()))
            elif action == "recent" and value in self.settings["recent"]:
                self.open_file(value)
            elif action == "reload":
                self.reload_document()
            elif action == "theme" and value in {"light", "dark", "system"}:
                self.settings["theme"] = value
                self.apply_native_theme()
                self.save_settings()
            elif action == "focus":
                self.settings["focus"] = bool(value)
                self.save_settings()
            elif action == "zoom":
                self.settings["zoom"] = max(0.8, min(1.5, float(value)))
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
                    self.open_file(path)
                    if parsed.fragment:
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
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        key = Gdk.keyval_name(event.keyval).lower()
        if ctrl and key == "o":
            self.choose_file()
        elif ctrl and key == "r":
            self.reload_document()
        elif ctrl and key == "f" and shift:
            self.send("command", "focus")
        elif ctrl and key == "f":
            self.send("command", "find")
        elif ctrl and key in {"plus", "equal", "kp_add", "minus", "kp_subtract", "0", "kp_0"}:
            self.send("command", "zoom-reset" if key in {"0", "kp_0"} else "zoom-out" if key in {"minus", "kp_subtract"} else "zoom-in")
        elif key == "escape":
            self.send("command", "escape")
        else:
            return False
        return True


if __name__ == "__main__":
    import sys
    raise SystemExit(Reader().run(sys.argv))
