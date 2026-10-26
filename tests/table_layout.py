"""Check real WebKit table geometry at wide and narrow window sizes."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--document", type=Path)
parser.add_argument("--baseline", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
artifacts = root / ".test-artifacts"
artifacts.mkdir(exist_ok=True)
temporary = tempfile.TemporaryDirectory(prefix="folio-tables-", dir=artifacts)
os.environ["XDG_CONFIG_HOME"] = temporary.name
sys.path.insert(0, str(root / "folio"))
from app import Reader, Gio, GLib, WebKit2

sample = Path(temporary.name) / "tabelas.md"
sample.write_text("""# Tabelas de documentação

Um parágrafo que continua com largura confortável de leitura, mesmo quando uma tabela precisa de mais espaço para mostrar seus dados.

| Aspecto | Estado | Onde |
|---|---|---|
| Documento principal | Leitura com `document-reader`, em `ReaderMode.continuous`, com saída `RenderedDocumentResult`. | `reader/documents.py` |
| Atualização automática | O monitor acompanha alterações no diretório e recarrega a leitura ao salvar o documento no editor. | `DocumentMonitor.py:28-32, 196-202` |
| Guias de referência | Quatro documentos com exemplos de formatação são apresentados para orientar a leitura. Tabelas, listas e blocos de código mantêm o conteúdo legível. | `docs/reading_guide.md` |

| # | Prio | Item | Componente | Seção |
|---|---|---|---|---|
| 1 | Alta | Preservar a posição da leitura ao atualizar o conteúdo no editor | leitor + monitor | 4.1 |
| 2 | Planejada | Oferecer atalhos para navegar pelos documentos locais | interface + leitor | 3.2 |
""")
app = Reader()
app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
app.settings.update(theme="dark", focus=False, zoom=1)
loop = GLib.MainLoop()
errors = []
sizes = iter([(1920, 1080), (1280, 900), (900, 800), (680, 800)])
current_width = 0


def finish(error=None):
    if error:
        errors.append(str(error))
    app.window.destroy()
    loop.quit()
    return False


def later(callback, delay=450):
    def invoke():
        try:
            callback()
        except Exception as error:
            finish(error)
        return False
    GLib.timeout_add(delay, invoke)


def initial():
    if not app.ready:
        later(initial, 100)
        return
    app.open_file(args.document or sample)
    later(resize)


def resize():
    global current_width
    size = next(sizes, None)
    if size is None:
        print("PASS: table layout at 1920, 1280, 900 and 680 px.")
        finish()
        return
    current_width = size[0]
    app.window.resize(*size)
    later(measure)


def measure():
    script = """(() => {
      const scroll = document.getElementById('reading-scroll');
      const table = document.querySelector('.table-wrap');
      scroll.scrollTo({top: scroll.scrollTop + table.getBoundingClientRect().top - scroll.getBoundingClientRect().top - 30, behavior:'instant'});
      const widths = [...document.querySelectorAll('.table-wrap')].map(wrap => ({
        viewport: wrap.clientWidth, content: wrap.scrollWidth,
        columns: [...wrap.querySelectorAll('thead th')].map(cell => Math.round(cell.getBoundingClientRect().width))
      }));
      const cells = [...document.querySelectorAll('td, th')];
      const broken = [];
      for (const cell of cells) {
        const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
          for (const match of node.textContent.matchAll(/[A-Za-zÀ-ÿ_]{4,}/g)) {
            const range = document.createRange();
            range.setStart(node, match.index); range.setEnd(node, match.index + match[0].length);
            const lines = new Set([...range.getClientRects()].filter(rect => rect.width > .5).map(rect => Math.round(rect.top)));
            if (lines.size > 1) broken.push(match[0]);
          }
        }
      }
      return JSON.stringify({width:innerWidth, reading:scroll.clientWidth, pageOverflow:scroll.scrollWidth-scroll.clientWidth,
        prose:document.querySelector('#document > p')?.getBoundingClientRect().width, tables:widths, brokenWords:broken.length, broken});
    })()"""
    def measured(web, result):
        try:
            data = json.loads(web.evaluate_javascript_finish(result).to_string())
            print(json.dumps(data, ensure_ascii=False))
            if not args.baseline:
                assert data["brokenWords"] == 0, f"Words broken across lines: {data}"
                assert data["pageOverflow"] <= 1, f"Page overflow: {data}"
                assert data["prose"] <= 800, f"Prose too wide: {data}"
                if current_width == 1920:
                    assert data["tables"][0]["viewport"] > 1100, f"Unused window space: {data}"
                    assert data["tables"][0]["columns"][0] >= 180, f"First column squeezed: {data}"
                    assert data["tables"][0]["columns"][-1] >= 180, f"Last column squeezed: {data}"
            snapshot()
        except Exception as error:
            finish(error)
    app.web.evaluate_javascript(script, -1, None, None, None, measured)


def snapshot():
    def captured(web, result):
        try:
            surface = web.get_snapshot_finish(result)
            label = "before" if args.baseline else "after"
            surface.write_to_png(str(artifacts / f"table-{label}-{current_width}.png"))
            later(resize, 100)
        except Exception as error:
            finish(error)
    app.web.get_snapshot(WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE, None, captured)


app.register(None)
app.activate()
later(initial, 100)
GLib.timeout_add_seconds(20, lambda: finish("Table layout test timed out"))
loop.run()
temporary.cleanup()
if errors:
    raise SystemExit("FAIL: " + "; ".join(errors))
