"""Exercise actual GTK/WebKit rendering, IPC, find, file watching and links."""

import json
import os
from pathlib import Path
import sys
import tempfile

os.environ["GDK_BACKEND"] = "x11"
artifacts = Path(__file__).resolve().parents[1] / ".test-artifacts"
artifacts.mkdir(exist_ok=True)
temporary = tempfile.TemporaryDirectory(prefix="folio-smoke-", dir=artifacts)
os.environ["XDG_CONFIG_HOME"] = temporary.name
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "folio"))
from app import Reader, Gio, GLib, WebKit2

folder = Path(temporary.name)
document = folder / "leitura com espaço.md"
next_document = folder / "próximo.md"
next_document.write_text("# Segundo documento\n\n## Destino\n\nLink local aberto.")
(folder / "imagem.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="30" height="20"><rect width="30" height="20" fill="green"/></svg>')
document.write_text("# Teste nativo\n\n## Primeira seção\n\nUma palavra **encontrável**.\n\n[Próximo](pr%C3%B3ximo.md#destino)\n\n![Local](imagem.svg)\n\n" + "Parágrafo para rolar.\n\n" * 100)
app = Reader()
app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
loop = GLib.MainLoop()
errors = []


def finish(error=None):
    if error:
        errors.append(str(error))
    app.window.destroy()
    loop.quit()
    return False


def evaluate(script, callback):
    def done(web, result):
        try:
            value = web.evaluate_javascript_finish(result)
            callback(json.loads(value.to_json(0)))
        except Exception as error:
            finish(error)
    app.web.evaluate_javascript(f"JSON.stringify((() => {{ {script} }})())", -1, None, None, None, done)


def later(callback, milliseconds=700):
    GLib.timeout_add(milliseconds, lambda: (callback(), False)[1])


def initial():
    if not app.ready:
        later(initial, 100)
        return
    evaluate("return {title: document.querySelector('h1')?.textContent, toc: document.querySelectorAll('#toc a').length};", check_initial)


def check_initial(encoded):
    value = json.loads(encoded)
    assert "calma" in value["title"], value
    assert value["toc"] >= 4, value
    def snapshot_done(web, result):
        try:
            surface = web.get_snapshot_finish(result)
            surface.write_to_png(str(artifacts / "folio-welcome.png"))
            app.open([Gio.File.new_for_path(str(document))], "")
            later(check_open)
        except Exception as error:
            finish(error)
    app.web.get_snapshot(WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE, None, snapshot_done)


def check_open():
    evaluate("return {title: document.querySelector('h1')?.textContent, filename: document.getElementById('filename').textContent, recent: document.querySelectorAll('.recent-item').length, image: document.querySelector('#document img').naturalWidth};", after_open)


def after_open(encoded):
    value = json.loads(encoded)
    assert value["title"] == "Teste nativo", value
    assert value["recent"] == 1, value
    assert value["filename"] == document.name, value
    assert value["image"] == 30, value
    evaluate("document.querySelector('[data-action=theme]').click(); document.querySelector('[data-action=zoom-in]').click(); document.querySelector('[data-action=focus]').click(); document.querySelector('[data-action=find]').click(); const input = document.getElementById('find-input'); input.value = 'palavra encontrável'; input.dispatchEvent(new Event('input')); return true;", lambda _: later(check_controls))


def check_controls():
    assert app.settings["theme"] == "dark", app.settings
    assert app.settings["zoom"] == 1.1, app.settings
    assert app.settings["focus"] is True, app.settings
    evaluate("return {theme: document.documentElement.dataset.theme, focus: document.body.classList.contains('focus'), found: document.getElementById('find-count').textContent};", after_controls)


def after_controls(encoded):
    value = json.loads(encoded)
    assert value["theme"] == "dark" and value["focus"], value
    assert value["found"] == "1 / 1", value
    evaluate("window.folio.receive('command', 'escape'); document.getElementById('reading-scroll').scrollTop = 500; return true;", lambda _: replace_document())


def replace_document():
    replacement = folder / "replacement.md"
    replacement.write_text(document.read_text().replace("Teste nativo", "Atualizado automaticamente"))
    replacement.replace(document)
    later(check_reload, 1100)


def check_reload():
    evaluate("return {title: document.querySelector('h1').textContent, scroll: document.getElementById('reading-scroll').scrollTop};", after_reload)


def after_reload(encoded):
    value = json.loads(encoded)
    assert value["title"] == "Atualizado automaticamente", value
    assert value["scroll"] >= 490, value
    evaluate("document.querySelector('#document a').click(); return true;", lambda _: later(check_link))


def check_link():
    evaluate("return {title: document.querySelector('h1').textContent, sections: document.querySelectorAll('#toc a').length};", after_link)


def after_link(encoded):
    value = json.loads(encoded)
    assert value["title"] == "Segundo documento", value
    assert app.path == next_document, app.path
    assert value["sections"] == 1, value
    evaluate("window.folio.receive('command', 'escape'); document.querySelector('[data-action=welcome]').click(); return true;", lambda _: later(check_welcome))


def check_welcome():
    assert app.path is None
    assert len(app.settings["recent"]) == 2
    print("PASS: GTK/WebKit startup, Markdown, index, recent files, theme, zoom, focus, document-scoped search, atomic-save reload with scroll preservation, relative link, welcome navigation.")
    print(f"Screenshot: {artifacts / 'folio-welcome.png'}")
    finish()


app.register(None)
app.activate()
later(initial, 100)
GLib.timeout_add_seconds(25, lambda: finish("Native smoke test timed out"))
loop.run()
temporary.cleanup()
if errors:
    raise SystemExit("FAIL: " + "; ".join(errors))
