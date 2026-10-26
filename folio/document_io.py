"""Local UTF-8 documents with format-preserving, atomic saves."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from gi.repository import Gio, GLib

MAX_FILE_SIZE = 20 * 1024 * 1024


@dataclass
class LocalDocument:
    path: Path
    text: str
    etag: str
    bom: bool = False
    newline: str = "\n"
    digest: str = ""

    @classmethod
    def load(cls, filename):
        path = Path(filename).expanduser().resolve()
        if path.stat().st_size > MAX_FILE_SIZE:
            raise ValueError("Este arquivo é muito grande (limite de 20 MB).")
        _success, contents, etag = Gio.File.new_for_path(str(path)).load_contents(None)
        if len(contents) > MAX_FILE_SIZE:
            raise ValueError("Este arquivo é muito grande (limite de 20 MB).")
        source = contents.decode("utf-8-sig")
        first_newline = re.search(r"\r\n|\r|\n", source)
        newline = first_newline[0] if first_newline else "\n"
        return cls(path, source.replace("\r\n", "\n").replace("\r", "\n"), etag,
                   contents.startswith(b"\xef\xbb\xbf"), newline, hashlib.sha256(contents).hexdigest())

    def has_changed(self):
        try:
            if self.path.stat().st_size > MAX_FILE_SIZE:
                return True
            _success, contents, etag = Gio.File.new_for_path(str(self.path)).load_contents(None)
            return etag != self.etag or hashlib.sha256(contents).hexdigest() != self.digest
        except (GLib.Error, OSError):
            return True

    def save(self, text, target=None, overwrite=False):
        path = Path(target).expanduser().resolve() if target else self.path
        if path == self.path and not overwrite and self.has_changed():
            raise GLib.Error.new_literal(Gio.io_error_quark(), "O arquivo foi alterado desde a abertura.", Gio.IOErrorEnum.WRONG_ETAG)
        contents = text.replace("\n", self.newline).encode("utf-8")
        if self.bom:
            contents = b"\xef\xbb\xbf" + contents
        etag = self.etag if path == self.path and not overwrite else None
        _success, new_etag = Gio.File.new_for_path(str(path)).replace_contents(
            contents, etag, False, Gio.FileCreateFlags.NONE, None)
        self.path, self.text, self.etag = path, text, new_etag
        self.digest = hashlib.sha256(contents).hexdigest()
