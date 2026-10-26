from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "folio"))
from document_io import LocalDocument, Gio, GLib


class DocumentIOTests(unittest.TestCase):
    def setUp(self):
        artifacts = Path(__file__).resolve().parents[1] / ".test-artifacts"
        artifacts.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=artifacts)
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "notas.md"

    def test_save_preserves_bom_crlf_permissions_and_missing_final_newline(self):
        self.path.write_bytes(b"\xef\xbb\xbf# Titulo\r\n\r\nTexto")
        self.path.chmod(0o640)
        document = LocalDocument.load(self.path)
        self.assertEqual(document.text, "# Titulo\n\nTexto")
        document.save("# Título\n\nOutro texto")
        self.assertEqual(self.path.read_bytes(), b"\xef\xbb\xbf# T\xc3\xadtulo\r\n\r\nOutro texto")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
        self.assertFalse(document.has_changed())

    def test_stale_save_is_rejected_without_changing_disk_or_document(self):
        self.path.write_text("Primeiro conteúdo\n")
        document = LocalDocument.load(self.path)
        replacement = self.path.with_suffix(".new")
        replacement.write_text("Conteúdo externo bem diferente\n")
        replacement.replace(self.path)
        self.assertTrue(document.has_changed())
        with self.assertRaises(GLib.Error) as caught:
            document.save("Edição local\n")
        self.assertTrue(caught.exception.matches(Gio.io_error_quark(), Gio.IOErrorEnum.WRONG_ETAG))
        self.assertEqual(self.path.read_text(), "Conteúdo externo bem diferente\n")
        self.assertEqual(document.text, "Primeiro conteúdo\n")
        document.save("Edição local\n", overwrite=True)
        self.assertEqual(self.path.read_text(), "Edição local\n")

    def test_save_copy_keeps_original(self):
        self.path.write_text("Original\n")
        document = LocalDocument.load(self.path)
        copy = self.path.with_name("cópia.md")
        document.save("Conteúdo da cópia\n", target=copy)
        self.assertEqual(self.path.read_text(), "Original\n")
        self.assertEqual(copy.read_text(), "Conteúdo da cópia\n")
        self.assertEqual(document.path, copy)
        self.assertFalse(document.has_changed())

    def test_failed_save_preserves_document_state(self):
        self.path.write_text("Original\n")
        document = LocalDocument.load(self.path)
        with self.assertRaises(GLib.Error):
            document.save("Novo\n", target=self.path.parent / "ausente" / "novo.md")
        self.assertEqual(document.path, self.path)
        self.assertEqual(document.text, "Original\n")
        self.assertEqual(self.path.read_text(), "Original\n")

    def test_symlink_is_preserved_and_missing_file_is_detected(self):
        self.path.write_text("Original\n")
        link = self.path.with_name("atalho.md")
        link.symlink_to(self.path)
        document = LocalDocument.load(link)
        document.save("Novo\n")
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.read_text(), "Novo\n")
        self.path.unlink()
        self.assertTrue(document.has_changed())

    def test_invalid_utf8_is_not_silently_replaced(self):
        self.path.write_bytes(b"\xff\xfe")
        with self.assertRaises(UnicodeError):
            LocalDocument.load(self.path)


if __name__ == "__main__":
    unittest.main()
