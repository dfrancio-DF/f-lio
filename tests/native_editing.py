"""Exercise native editing, actual confirmation dialogs and file conflicts."""

import json
import os
from pathlib import Path
import sys
import tempfile
import time

os.environ["GDK_BACKEND"] = "x11"
root = Path(__file__).resolve().parents[1]
artifacts = root / ".test-artifacts"
artifacts.mkdir(exist_ok=True)
temporary = tempfile.TemporaryDirectory(prefix="folio-editing-", dir=artifacts)
os.environ["XDG_CONFIG_HOME"] = temporary.name
sys.path.insert(0, str(root / "folio"))
from app import Reader, Gdk, Gio, GLib, Gtk

folder = Path(temporary.name)
path = folder / "edição.md"
other = folder / "outro.md"
original = "# Documento de edição\n\nUm texto para editar com calma.\n"
path.write_bytes(b"\xef\xbb\xbf" + original.replace("\n", "\r\n").encode())
other.write_text("# Outro documento\n")
app = Reader()
app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)


def pump(seconds=.15):
    loop = GLib.MainLoop()
    GLib.timeout_add(max(1, int(seconds * 1000)), lambda: (loop.quit(), False)[1])
    loop.run()


def wait_for(predicate, timeout=6):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "Timed out waiting for native UI"
        pump(.05)


def javascript(script):
    values, errors = [], []
    def done(web, result):
        try:
            values.append(json.loads(web.evaluate_javascript_finish(result).to_json(0)))
        except Exception as error:
            errors.append(error)
    app.web.evaluate_javascript(script, -1, None, None, None, done)
    wait_for(lambda: values or errors)
    if errors:
        raise errors[0]
    return values[0]


def answer(*responses):
    pending = list(responses)
    seen = set()
    deadline = time.monotonic() + 5
    def respond():
        if not pending or time.monotonic() >= deadline:
            return False
        for dialog in Gtk.Window.list_toplevels():
            if isinstance(dialog, Gtk.MessageDialog) and dialog.get_visible() and dialog not in seen:
                seen.add(dialog)
                dialog.response(pending.pop(0))
                break
        return bool(pending)
    GLib.timeout_add(50, respond)


def append(text):
    buffer = app.editor.buffer
    buffer.begin_user_action()
    buffer.insert(buffer.get_end_iter(), text)
    buffer.end_user_action()


def key(name, shift=False):
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.keyval = Gdk.keyval_from_name(name)
    event.state = Gdk.ModifierType.CONTROL_MASK | (Gdk.ModifierType.SHIFT_MASK if shift else 0)
    return app.on_key(app.window, event)


try:
    app.register(None)
    app.activate()
    wait_for(lambda: app.ready)
    assert not app.editing and app.stack.get_visible_child_name() == "reading"
    assert javascript("document.getElementById('edit-button').disabled") is True
    assert app.open_file(path)
    wait_for(lambda: javascript("document.getElementById('edit-button').disabled") is False)
    assert javascript("document.getElementById('document').isContentEditable") is False
    javascript("document.getElementById('edit-button').click(); true")
    wait_for(lambda: app.editing)
    pump(.15)
    assert app.window.get_focus() == app.editor.view, "Editing must keep keyboard focus in the source view"
    assert app.stack.get_visible_child_name() == "editor"
    assert app.editor.text() == original
    assert app.editor.buffer.get_language().get_id() == "markdown"
    assert not app.editor.modified

    append("\n## Uma nova ideia\n\nEdição nativa de Markdown.\n")
    assert app.editor.modified and app.window.get_title().startswith("• ")
    key("z")
    assert app.editor.text() == original and not app.editor.modified
    key("z", shift=True)
    assert app.editor.modified
    edited = app.editor.text()
    key("s")
    assert not app.editor.modified
    assert path.read_bytes() == b"\xef\xbb\xbf" + edited.replace("\n", "\r\n").encode()
    assert app.editing
    pump(.5)
    assert app.editor.text() == edited, "Own save must not reset the editor"
    assert app.editor.buffer.can_undo(), "Save must preserve undo history"

    # Capture only the test application's virtual X11 window.
    size = app.window.get_allocation()
    image = Gdk.pixbuf_get_from_window(app.window.get_window(), 0, 0, size.width, size.height)
    image.savev(str(artifacts / "folio-editor.png"), "png", [], [])
    app.toggle_theme()
    pump(.2)
    assert app.editor.buffer.get_style_scheme().get_id() == "oblivion"
    image = Gdk.pixbuf_get_from_window(app.window.get_window(), 0, 0, size.width, size.height)
    image.savev(str(artifacts / "folio-editor-dark.png"), "png", [], [])
    app.editor.back_button.clicked()
    assert not app.editing
    assert "Uma nova ideia" in javascript("document.getElementById('document').textContent")
    assert app.start_editing()

    append("\nRascunho não salvo.\n")
    draft = app.editor.text()
    for operation in (app.return_to_reading, lambda: app.open_file(other), app.show_welcome,
                      lambda: app.reload_from_disk(manual=True)):
        answer(Gtk.ResponseType.CANCEL)
        assert operation() is False
        assert app.editing and app.editor.text() == draft
    answer(Gtk.ResponseType.CANCEL)
    assert app.on_close() is True, "Cancel must prevent closing"
    assert app.editor.text() == draft

    answer(Gtk.ResponseType.REJECT)
    assert app.return_to_reading()
    assert not app.editing
    assert app.document.text == edited
    assert app.start_editing()

    # External changes reload clean buffers, but never overwrite dirty ones.
    external = "# Atualização externa\n\nUm conteúdo atualizado no editor externo.\n"
    path.write_bytes(b"\xef\xbb\xbf" + external.replace("\n", "\r\n").encode())
    wait_for(lambda: app.editor.text() == external)
    assert not app.editor.modified
    append("\nMinha edição local.\n")
    local = app.editor.text()
    external2 = "# Outra atualização externa\n"
    path.write_bytes(b"\xef\xbb\xbf" + external2.replace("\n", "\r\n").encode())
    wait_for(lambda: app.editor.info.get_visible())
    assert app.editor.text() == local
    answer(Gtk.ResponseType.CANCEL)
    assert not app.save_document()
    assert app.editor.modified and app.document.text == external
    assert external2 in path.read_text(encoding="utf-8-sig")

    # Canceling a save conflict inside the close prompt must also cancel closing.
    answer(Gtk.ResponseType.ACCEPT, Gtk.ResponseType.CANCEL)
    assert app.on_close() is True
    assert app.editor.text() == local

    copy = folder / "cópia.md"
    app.choose_save_path = lambda: str(copy)
    answer(2)  # Save a copy, preserving both versions.
    assert app.save_document()
    assert app.path == copy and not app.editor.modified
    assert external2 in path.read_text(encoding="utf-8-sig")
    assert copy.read_bytes() == b"\xef\xbb\xbf" + local.replace("\n", "\r\n").encode()

    append("\nPermanece após erro.\n")
    before_error = app.editor.text()
    assert not app.save_document(save_as=True, target=folder / "ausente" / "arquivo.md")
    assert app.editor.modified and app.editor.text() == before_error and app.path == copy

    # Explicit overwrite is the only path that replaces an external version.
    copy.write_text("Versão externa da cópia, não perder silenciosamente.\n")
    answer(3)
    assert app.save_document()
    assert copy.read_bytes() == b"\xef\xbb\xbf" + before_error.replace("\n", "\r\n").encode()

    append("\nDescartar só por escolha explícita.\n")
    copy.write_text("# Documento externo recarregado\n\nMinha edição externa.\n")
    answer(1)
    assert app.save_document()
    assert app.editor.text() == copy.read_text() and not app.editor.modified

    key("f")
    assert app.editor.find_bar.get_visible()
    app.editor.find_entry.set_text("Minha edição")
    pump(.4)
    assert app.editor.search.get_occurrences_count() == 1
    app.editor.close_find()

    # Saving on close, Save As cancellation, and default read-only navigation.
    append("\nSalvo antes de fechar.\n")
    app.choose_save_path = lambda: None
    assert not app.save_document(save_as=True)
    assert app.editor.modified
    answer(Gtk.ResponseType.ACCEPT)
    assert app.on_close() is False and not app.editor.modified
    assert app.open_file(other) and not app.editing
    assert app.stack.get_visible_child_name() == "reading"
    assert app.start_editing()
    assert not app.editor.modified and not app.editor.buffer.can_undo()
    print("PASS: read-only default, Edit IPC, GtkSourceView, undo/redo, save, BOM/CRLF, dirty dialogs, external changes, conflict cancel/copy/overwrite, save failure, editor search and Save As cancellation.")
    print(f"Screenshot: {artifacts / 'folio-editor.png'}")
finally:
    if app.window:
        app.window.destroy()
    temporary.cleanup()
