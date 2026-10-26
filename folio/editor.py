"""Native Markdown source editor, loaded only when editing is requested."""

import gi

gi.require_version("GtkSource", "4")
from gi.repository import Gtk, GtkSource, Pango


class MarkdownEditor(Gtk.Box):
    def __init__(self, *, save, save_as, back, changed, reload, theme):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.get_style_context().add_class("folio-editor")
        self.changed_callback = changed
        self.path = None
        self.loading = False
        toolbar = Gtk.Box(spacing=8)
        toolbar.get_style_context().add_class("editor-toolbar")
        self.pack_start(toolbar, False, False, 0)

        def button(icon, label, tooltip, callback):
            control = Gtk.Button()
            box = Gtk.Box(spacing=7)
            box.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON), False, False, 0)
            if label:
                box.pack_start(Gtk.Label(label=label), False, False, 0)
            control.add(box)
            control.set_tooltip_text(tooltip)
            control.connect("clicked", lambda _: callback())
            toolbar.pack_start(control, False, False, 0)
            return control

        self.back_button = button("go-previous-symbolic", "Leitura", "Voltar à leitura (Ctrl E)", back)
        self.filename = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE)
        self.filename.set_hexpand(True)
        self.filename.set_margin_start(12)
        toolbar.pack_start(self.filename, True, True, 0)
        self.undo_button = button("edit-undo-symbolic", None, "Desfazer (Ctrl Z)", self.undo)
        self.redo_button = button("edit-redo-symbolic", None, "Refazer (Ctrl Shift Z)", self.redo)
        button("edit-find-symbolic", None, "Buscar no Markdown (Ctrl F)", self.show_find)
        button("weather-clear-night-symbolic", None, "Alternar tema", theme)
        button("document-save-as-symbolic", None, "Salvar como (Ctrl Shift S)", save_as)
        self.save_button = button("document-save-symbolic", "Salvar", "Salvar (Ctrl S)", save)
        self.save_button.get_style_context().add_class("suggested-action")

        self.info = Gtk.InfoBar(show_close_button=True, message_type=Gtk.MessageType.WARNING)
        self.info.set_no_show_all(True)
        self.info_label = Gtk.Label(xalign=0, wrap=True)
        self.info_label.set_hexpand(True)
        self.info.get_content_area().add(self.info_label)
        self.reload_button = self.info.add_button("Recarregar do disco", Gtk.ResponseType.APPLY)
        self.info.connect("response", lambda _, response: reload() if response == Gtk.ResponseType.APPLY else self.info.hide())
        self.pack_start(self.info, False, False, 0)

        self.find_bar = Gtk.Box(spacing=8)
        self.find_bar.get_style_context().add_class("editor-find")
        self.find_bar.set_no_show_all(True)
        self.find_entry = Gtk.SearchEntry(placeholder_text="Buscar no Markdown…")
        self.find_entry.set_hexpand(True)
        self.find_bar.pack_start(self.find_entry, True, True, 0)
        self.find_count = Gtk.Label()
        self.find_bar.pack_start(self.find_count, False, False, 0)
        for label, callback in (("↑", lambda: self.find_match(False)), ("↓", self.find_match), ("×", self.close_find)):
            control = Gtk.Button(label=label)
            control.connect("clicked", lambda _, callback=callback: callback())
            self.find_bar.pack_start(control, False, False, 0)
        self.pack_start(self.find_bar, False, False, 0)

        self.buffer = GtkSource.Buffer()
        self.buffer.set_language(GtkSource.LanguageManager.get_default().get_language("markdown"))
        self.buffer.set_highlight_syntax(True)
        self.buffer.set_max_undo_levels(500)
        self.view = GtkSource.View.new_with_buffer(self.buffer)
        self.view.set_monospace(True)
        self.view.set_show_line_numbers(True)
        self.view.set_highlight_current_line(True)
        self.view.set_auto_indent(True)
        self.view.set_insert_spaces_instead_of_tabs(True)
        self.view.set_tab_width(4)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_left_margin(22)
        self.view.set_right_margin(22)
        self.view.set_top_margin(24)
        self.view.set_bottom_margin(24)
        self.view.set_smart_home_end(GtkSource.SmartHomeEndType.BEFORE)
        scroller = Gtk.ScrolledWindow()
        scroller.add(self.view)
        self.pack_start(scroller, True, True, 0)

        footer = Gtk.Box(spacing=16)
        footer.get_style_context().add_class("editor-footer")
        self.format_label = Gtk.Label(xalign=0)
        self.format_label.set_hexpand(True)
        self.status = Gtk.Label(label="Sem alterações")
        self.cursor = Gtk.Label(label="Ln 1, Col 1")
        for child, expand in ((self.format_label, True), (self.status, False), (self.cursor, False)):
            footer.pack_start(child, expand, expand, 0)
        self.pack_start(footer, False, False, 0)

        self.search_settings = GtkSource.SearchSettings(wrap_around=True, case_sensitive=False)
        self.search = GtkSource.SearchContext.new(self.buffer, self.search_settings)
        self.search.connect("notify::occurrences-count", self.on_search_count)
        self.find_entry.connect("search-changed", self.on_search_changed)
        self.find_entry.connect("activate", lambda _: self.find_match())
        self.find_entry.connect("key-press-event", self.on_find_key)
        self.find_entry.connect("stop-search", lambda _: self.close_find())
        self.buffer.connect("modified-changed", self.on_modified)
        self.buffer.connect("mark-set", self.on_cursor)
        for prop in ("can-undo", "can-redo"):
            self.buffer.connect(f"notify::{prop}", lambda *_: self.update_actions())
        self.show_all()
        self.info.hide()
        self.find_bar.hide()
        self.update_actions()

    @property
    def modified(self):
        return self.buffer.get_modified()

    def text(self):
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), True)

    def load(self, document):
        self.loading = True
        self.path = document.path
        self.buffer.begin_not_undoable_action()
        self.buffer.set_text(document.text)
        self.buffer.end_not_undoable_action()
        self.buffer.set_modified(False)
        self.buffer.place_cursor(self.buffer.get_start_iter())
        self.loading = False
        endings = {"\n": "LF", "\r\n": "CRLF", "\r": "CR"}[document.newline]
        self.format_label.set_text(f"Markdown · UTF-8{' com BOM' if document.bom else ''} · {endings}")
        self.info.hide()
        self.close_find()
        self.on_modified()

    def saved(self, document):
        self.path = document.path
        self.buffer.set_modified(False)
        self.info.hide()
        self.on_modified()

    def on_modified(self, *_):
        if self.loading:
            return
        self.filename.set_text(("• " if self.modified else "") + (self.path.name if self.path else "Markdown"))
        self.status.set_text("Alterações não salvas" if self.modified else "Tudo salvo")
        self.save_button.set_sensitive(self.modified)
        self.changed_callback()

    def on_cursor(self, *_):
        position = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        self.cursor.set_text(f"Ln {position.get_line() + 1}, Col {position.get_line_offset() + 1}")

    def update_actions(self):
        self.undo_button.set_sensitive(self.buffer.can_undo())
        self.redo_button.set_sensitive(self.buffer.can_redo())

    def undo(self):
        if self.buffer.can_undo():
            self.buffer.undo()

    def redo(self):
        if self.buffer.can_redo():
            self.buffer.redo()

    def appearance(self, dark, zoom):
        manager = GtkSource.StyleSchemeManager.get_default()
        scheme = manager.get_scheme("oblivion" if dark else "tango")
        self.buffer.set_style_scheme(scheme)
        self.view.override_font(Pango.FontDescription(f"Monospace {11 * zoom:.1f}"))

    def show_message(self, message, *, warning=False, reload=False):
        self.info.set_message_type(Gtk.MessageType.WARNING if warning else Gtk.MessageType.INFO)
        self.info_label.set_text(message)
        self.info.get_content_area().show_all()
        self.info.get_action_area().show_all()
        self.reload_button.set_visible(reload)
        self.info_label.show()
        self.info.show()

    def show_find(self):
        self.find_bar.set_no_show_all(False)
        self.find_bar.show_all()
        self.find_bar.set_no_show_all(True)
        self.find_entry.grab_focus()

    def close_find(self):
        self.find_bar.hide()
        self.find_entry.set_text("")
        self.search_settings.set_search_text(None)
        self.view.grab_focus()

    def on_search_changed(self, *_):
        self.search_settings.set_search_text(self.find_entry.get_text() or None)
        self.find_match(from_start=True)

    def on_search_count(self, *_):
        count = self.search.get_occurrences_count()
        self.find_count.set_text(f"{count} resultado(s)" if count >= 0 and self.find_entry.get_text() else "")

    def on_find_key(self, _entry, event):
        from gi.repository import Gdk
        if event.keyval in {Gdk.KEY_Return, Gdk.KEY_KP_Enter} and event.state & Gdk.ModifierType.SHIFT_MASK:
            self.find_match(False)
            return True
        return False

    def find_match(self, forward=True, from_start=False):
        if not self.find_entry.get_text():
            return
        selection = self.buffer.get_selection_bounds()
        if from_start:
            start = self.buffer.get_start_iter()
        elif selection:
            start = selection[1 if forward else 0]
        else:
            start = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        found, begin, end, _wrapped = self.search.forward(start) if forward else self.search.backward(start)
        if found:
            self.buffer.select_range(begin, end)
            self.view.scroll_to_iter(begin, .15, False, 0, 0)
