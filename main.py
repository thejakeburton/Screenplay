"""Screenplay — a minimal offline novel and screenplay editor for macOS."""
import json
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QStringListModel
from PySide6.QtGui import QFont, QTextBlockFormat, QTextCursor, QPageSize, QPageLayout, QKeySequence, QAction, QShortcut
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QComboBox, QFileDialog, QMessageBox, QInputDialog, QCompleter
)

ELEMENTS = ("Scene Heading", "Action", "Character", "Dialogue", "Parenthetical", "Transition")
# QTextBlockFormat left margins relative to the screenplay's 1.5-inch page margin.
INDENT = (0, 0, 160, 90, 120, 220)
RIGHT = (0, 0, 0, 115, 100, 0)


class WritingEditor(QTextEdit):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.mode = "Action"
        self.characters = set()
        self.setAcceptRichText(True)
        self.setFont(QFont("Courier New", 12))
        self.setStyleSheet("QTextEdit { background: #fffefa; color: #202329; border: 1px solid #c9cbd0; selection-background-color: #386fa5; }")
        self.document().setDocumentMargin(26)
        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.activated.connect(self.complete_character)
        self.textChanged.connect(self.suggest_character)
        self.cursorPositionChanged.connect(self.sync_element)

    def screenplay(self):
        return self.owner.kind == "Screenplay"

    def set_element(self, element):
        if not self.screenplay() or element not in ELEMENTS:
            return
        self.mode = element
        cursor = self.textCursor()
        fmt = QTextBlockFormat()
        i = ELEMENTS.index(element)
        fmt.setLeftMargin(INDENT[i])
        fmt.setRightMargin(RIGHT[i])
        fmt.setTopMargin(10 if element in ("Scene Heading", "Character", "Transition") else 2)
        fmt.setBottomMargin(3)
        fmt.setLineHeight(100.0, 1)
        cursor.mergeBlockFormat(fmt)
        cursor.block().setUserState(i)
        self.setTextCursor(cursor)
        self.owner.element.blockSignals(True)
        self.owner.element.setCurrentText(element)
        self.owner.element.blockSignals(False)

    def sync_element(self):
        if not self.screenplay():
            return
        state = self.textCursor().block().userState()
        element = ELEMENTS[state] if 0 <= state < len(ELEMENTS) else "Action"
        self.mode = element
        self.owner.element.blockSignals(True)
        self.owner.element.setCurrentText(element)
        self.owner.element.blockSignals(False)

    def complete_character(self, name):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(name)
        self.setTextCursor(cursor)
        self.set_element("Character")
        self.completer.popup().hide()

    def suggest_character(self):
        if not self.screenplay() or self.mode != "Character":
            self.completer.popup().hide()
            return
        cursor = self.textCursor()
        if cursor.hasSelection():
            return
        prefix = cursor.block().text().strip().upper()
        matches = sorted(c for c in self.characters if c.startswith(prefix) and c != prefix) if prefix else []
        if not matches:
            self.completer.popup().hide()
            return
        self.completer.setModel(QStringListModel(matches, self.completer))
        self.completer.setCompletionPrefix(prefix)
        rect = self.cursorRect()
        rect.setWidth(230)
        self.completer.complete(rect)

    def keyPressEvent(self, event):
        if not self.screenplay():
            return super().keyPressEvent(event)
        key = event.key()
        if self.completer.popup().isVisible():
            if key in (Qt.Key_Tab, Qt.Key_Return, Qt.Key_Enter):
                value = self.completer.currentCompletion()
                if value:
                    self.complete_character(value)
                return
            if key == Qt.Key_Escape:
                self.completer.popup().hide()
                return
        if key == Qt.Key_Tab and event.modifiers() == Qt.NoModifier:
            self.set_element(ELEMENTS[(ELEMENTS.index(self.mode) + 1) % len(ELEMENTS)])
            return
        if key in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() == Qt.NoModifier:
            previous = self.textCursor().block().text().strip()
            current = self.mode
            if current == "Character" and previous:
                self.characters.add(previous.upper())
            super().keyPressEvent(event)
            if current == "Character":
                following = "Dialogue"
            elif current == "Scene Heading":
                following = "Action"
            elif current in ("Dialogue", "Parenthetical"):
                following = "Dialogue" if previous else "Action"
            elif current == "Transition":
                following = "Scene Heading"
            else:
                following = "Action"
            self.set_element(following)
            return
        super().keyPressEvent(event)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.kind = "Screenplay"
        self.file_path = None
        self.dirty = False
        self.setWindowTitle("Screenplay — Untitled")
        self.resize(1050, 800)

        central = QWidget()
        central.setStyleSheet("QWidget { background: #252b33; color: #e9edf1; } QLabel { color: #d6dce3; } QComboBox { background: #39424d; color: white; padding: 5px; }")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(26, 20, 26, 20)
        top = QHBoxLayout()
        top.addWidget(QLabel("WRITING MODE"))
        self.kind_select = QComboBox()
        self.kind_select.addItems(("Screenplay", "Novel"))
        self.kind_select.currentTextChanged.connect(self.change_mode)
        top.addWidget(self.kind_select)
        top.addSpacing(24)
        self.element_label = QLabel("ELEMENT")
        top.addWidget(self.element_label)
        self.element = QComboBox()
        self.element.addItems(ELEMENTS)
        self.element.setCurrentText("Action")
        self.element.currentTextChanged.connect(self.set_element)
        top.addWidget(self.element)
        top.addStretch()
        layout.addLayout(top)
        self.editor = WritingEditor(self)
        layout.addWidget(self.editor, 1)
        self.setCentralWidget(central)
        self.editor.textChanged.connect(self.mark_dirty)
        self.editor.cursorPositionChanged.connect(self.update_status)
        self.make_menus()
        self.statusBar().showMessage("Screenplay · Tab changes element · Return advances · ⌘S saves")
        self.editor.set_element("Action")
        self.dirty = False

    def make_menus(self):
        file_menu = self.menuBar().addMenu("File")
        for title, fn, shortcut in (
            ("New…", self.new_document, "Ctrl+N"),
            ("Open…", self.open_document, "Ctrl+O"),
            ("Save", self.save_document, "Ctrl+S"),
            ("Save As…", self.save_as, "Ctrl+Shift+S"),
            ("Export PDF…", self.export_pdf, "Ctrl+E"),
        ):
            action = file_menu.addAction(title, fn)
            action.setShortcut(QKeySequence(shortcut))
        edit_menu = self.menuBar().addMenu("Edit")
        for title, fn, shortcut in (
            ("Undo", self.editor.undo, "Ctrl+Z"),
            ("Redo", self.editor.redo, "Ctrl+Shift+Z"),
            ("Find…", self.find_text, "Ctrl+F"),
        ):
            action = edit_menu.addAction(title, fn)
            action.setShortcut(QKeySequence(shortcut))
        format_menu = self.menuBar().addMenu("Format")
        for index, element in enumerate(ELEMENTS, 1):
            action = format_menu.addAction(element, lambda checked=False, e=element: self.set_element(e))
            action.setShortcut(QKeySequence("Ctrl+" + str(index)))
        format_menu.addSeparator()
        for title, method, shortcut in (
            ("Bold", "setFontWeight", "Ctrl+B"),
            ("Italic", "setFontItalic", "Ctrl+I"),
            ("Underline", "setFontUnderline", "Ctrl+U"),
        ):
            if title == "Bold":
                fn = lambda: self.editor.setFontWeight(400 if self.editor.fontWeight() > 400 else 700)
            elif title == "Italic":
                fn = lambda: self.editor.setFontItalic(not self.editor.fontItalic())
            else:
                fn = lambda: self.editor.setFontUnderline(not self.editor.fontUnderline())
            action = format_menu.addAction(title, fn)
            action.setShortcut(QKeySequence(shortcut))

    def set_element(self, element):
        self.editor.set_element(element)

    def change_mode(self, mode):
        self.kind = mode
        script = mode == "Screenplay"
        self.element.setVisible(script)
        self.element_label.setVisible(script)
        self.editor.completer.popup().hide()
        self.editor.setFont(QFont("Courier New", 12) if script else QFont("Georgia", 12))
        if script:
            self.editor.set_element("Action")
        self.mark_dirty()
        self.update_status()

    def mark_dirty(self):
        self.dirty = True
        name = Path(self.file_path).stem if self.file_path else "Untitled"
        self.setWindowTitle("Screenplay — " + name + (" *" if self.dirty else ""))

    def update_status(self):
        words = len(self.editor.toPlainText().split())
        self.statusBar().showMessage(f"{self.kind} · {words:,} words · ⌘S Save · ⌘E Export PDF")

    def confirm_discard(self):
        if not self.dirty:
            return True
        result = QMessageBox.question(self, "Unsaved changes", "Discard unsaved changes?",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return result == QMessageBox.Yes

    def new_document(self):
        if not self.confirm_discard():
            return
        choices = ["Screenplay", "Novel"]
        kind, ok = QInputDialog.getItem(self, "New document", "Document type:", choices, 0, False)
        if not ok:
            return
        self.file_path = None
        self.kind_select.setCurrentText(kind)
        self.editor.clear()
        self.editor.characters.clear()
        if kind == "Screenplay":
            self.editor.set_element("Action")
        self.dirty = False
        self.mark_dirty()
        self.dirty = False
        self.setWindowTitle("Screenplay — Untitled")

    def open_document(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open document", "", "Screenplay documents (*.screenplay)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if data.get("kind") not in ("Screenplay", "Novel") or not isinstance(data.get("html"), str):
                raise ValueError("Not a valid Screenplay document")
            self.kind_select.setCurrentText(data["kind"])
            self.editor.setHtml(data["html"])
            self.editor.characters = set(data.get("characters", []))
            self.file_path = path
            self.dirty = False
            self.setWindowTitle("Screenplay — " + Path(path).stem)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Open failed", str(exc))

    def save_document(self):
        if not self.file_path:
            return self.save_as()
        try:
            data = {"version": 1, "kind": self.kind, "html": self.editor.toHtml(),
                    "characters": sorted(self.editor.characters)}
            Path(self.file_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.dirty = False
            self.setWindowTitle("Screenplay — " + Path(self.file_path).stem)
            return True
        except OSError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return False

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save document", self.file_path or "Untitled.screenplay",
                                              "Screenplay documents (*.screenplay)")
        if not path:
            return False
        self.file_path = path if path.endswith(".screenplay") else path + ".screenplay"
        return self.save_document()

    def find_text(self):
        term, ok = QInputDialog.getText(self, "Find", "Find text:")
        if ok and term:
            if not self.editor.find(term):
                self.editor.moveCursor(QTextCursor.Start)
                if not self.editor.find(term):
                    QMessageBox.information(self, "Find", "No match found.")

    def export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", (Path(self.file_path).stem if self.file_path else "Untitled") + ".pdf",
                                              "PDF (*.pdf)")
        if not path:
            return
        try:
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(path)
            printer.setPageSize(QPageSize(QPageSize.Letter))
            # QTextDocument printing respects block indentation and styling.
            doc = self.editor.document().clone()
            if self.kind == "Screenplay":
                printer.setPageMargins(38, 25, 25, 25, QPageLayout.Millimeter)
            else:
                printer.setPageMargins(25, 25, 25, 25, QPageLayout.Millimeter)
            doc.print_(printer)
            QMessageBox.information(self, "PDF exported", "Saved PDF to:\n" + path)
        except Exception as exc:
            QMessageBox.warning(self, "PDF export failed", str(exc))

    def closeEvent(self, event):
        event.accept() if self.confirm_discard() else event.ignore()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Screenplay")
    window = Window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
