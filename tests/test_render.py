import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "folio"))
from render import render_document


class MarkdownTests(unittest.TestCase):
    def test_navigation_and_duplicate_headings(self):
        result = render_document("# Olá, mundo\n\n## Uma seção\n\n## Uma seção\n\n## `código` e **texto**", "/tmp/documento.md")
        self.assertEqual(result["title"], "Olá, mundo")
        self.assertEqual([h["id"] for h in result["headings"]], ["ola-mundo", "uma-secao", "uma-secao-1", "codigo-e-texto"])
        self.assertIn('id="uma-secao-1"', result["html"])

    def test_gfm_tables_checklists_and_highlighting(self):
        result = render_document("| A | B |\n|---|---|\n| 1 | 2 |\n\n- [x] Feito\n- [ ] Pendente\n\n~~antigo~~\n\n```python\ndef hello():\n    return 1\n```\n")
        self.assertIn("<table>", result["html"])
        self.assertIn('checked="checked"', result["html"])
        self.assertEqual(result["html"].count('type="checkbox"'), 2)
        self.assertIn("<s>antigo</s>", result["html"])
        self.assertIn('class="k"', result["html"])

    def test_untrusted_html_cannot_execute_or_restyle_the_app(self):
        source = '''# Documento
<script>window.webkit.messageHandlers.folio.postMessage('bad')</script>
<style>body {display:none}</style>
<img src="x.png" onerror="alert(1)">
<a href="java&#x09;script:alert(1)" onclick="alert(2)">perigo</a>
<iframe src="https://example.org"></iframe>
<div style="position:fixed" data-action="open">Texto seguro</div>
<details><summary>Mais</summary>Conteúdo</details>
'''
        rendered = render_document(source, "/tmp/test.md")["html"]
        for forbidden in ("<script", "<style", "<iframe", "onerror", "onclick", "javascript:", "data-action", "style=", "postMessage"):
            self.assertNotIn(forbidden, rendered)
        self.assertIn("Texto seguro", rendered)
        self.assertIn("<details>", rendered)

    def test_relative_images_links_and_unicode_paths(self):
        rendered = render_document('[Próximo](outro%20arquivo.md#secao)\n\n![Imagem](imagens/foto.png)\n\n<a href="#resumo">Resumo</a>', "/tmp/pasta com espaços/olá.md")["html"]
        self.assertIn('href="file:///tmp/pasta%20com%20espa%C3%A7os/outro%20arquivo.md#secao"', rendered)
        self.assertIn('src="file:///tmp/pasta%20com%20espa%C3%A7os/imagens/foto.png"', rendered)
        self.assertIn('href="#resumo"', rendered)

    def test_fenced_code_remains_literal(self):
        rendered = render_document('```unknown-language\n<script>alert(1)</script>\n```')["html"]
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn("<script>", rendered)

    def test_incomplete_html_link_can_be_saved_and_rendered(self):
        rendered = render_document('<a href="http://[">Rascunho</a>')["html"]
        self.assertIn("Rascunho", rendered)
        self.assertNotIn("href=", rendered)


if __name__ == "__main__":
    unittest.main()
