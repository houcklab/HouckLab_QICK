"""
==================
ConfigCodeEditor.py
==================

This class contains the window for the config extractor code editor.

Running this config extractor runs the script via .exec(). Before execution, certain built-ins are applied. Notably, it
prevents the importing of certain dangerous modules such as socProxy, and blocks actual code execution such as .acquire.

Currently, this is a ban-list type of approach. Safer to move to a allow-list type of approach.

ENHANCEMENTS:
- File watching for external changes (autosave sync)
- Unsaved changes indicator
- Advanced code editing with QsciScintilla (syntax highlighting, auto-indent, commenting)
- Dark mode toggle
"""

import os
import traceback
import sys
import ast
import importlib.util
from types import SimpleNamespace
import matplotlib.pyplot as plt

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QToolBar, QAction,
    QLineEdit, QHBoxLayout, QPushButton, QApplication,
    QFrame, QSpacerItem, QSizePolicy, QShortcut, QLabel,
    QMessageBox, QPlainTextEdit
)
from PyQt5.QtGui import QKeySequence, QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QPainter, QTextFormat
from PyQt5.QtCore import Qt, pyqtSignal, qCritical, qInfo, QTimer, QRegExp, QRect, qWarning, QFileSystemWatcher

# Import QScintilla for advanced code editing
try:
    from PyQt5.Qsci import QsciScintilla, QsciLexerPython

    QSCI_AVAILABLE = True
except ImportError:
    QSCI_AVAILABLE = False
    qWarning("QScintilla not available. Install with: pip install QScintilla")

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers
from MasterProject.Client_modules.Desq_GUI.scripts.DualMultiCheckboxDialog import DualMultiCheckboxDialog


class FindBar(QFrame):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.setObjectName('FindBar')
        self.editor = editor
        self.setFixedHeight(25)
        self.setFixedWidth(275)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Find...")
        self.search_input.returnPressed.connect(self.find_next)

        self.find_button = Helpers.create_button("Next", "find_button", True, self)
        self.find_button.clicked.connect(self.find_next)

        self.close_findbar_button = Helpers.create_button("", "close_findbar_button", True, self, False)
        self.close_findbar_button.clicked.connect(self.hide)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 1, 0, 1)
        layout.addWidget(self.search_input)
        layout.addWidget(self.find_button)
        layout.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        layout.addWidget(self.close_findbar_button)

        self.setLayout(layout)
        self.hide()

    def find_next(self):
        text = self.search_input.text()
        if QSCI_AVAILABLE and isinstance(self.editor, QsciScintilla):
            # QScintilla find
            self.editor.findFirst(text, False, True, False, True)
        else:
            # Regular QTextEdit find
            if not self.editor.find(text):
                self.editor.moveCursor(self.editor.textCursor().Start)
                self.editor.find(text)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.setObjectName("line_number_widget")
        self.code_editor = editor

    def sizeHint(self):
        return Qt.QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)


class CodeTextEditor(QPlainTextEdit):
    """Enhanced plain text editor with line numbers and basic code features"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.block_signals = []  # store blocked line numbers

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)

        self.update_line_number_area_width(0)

        # Set monospace font
        font = QFont("Courier New", 12)
        self.setFont(font)

        # Tab settings
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)

    def line_number_area_width(self):
        digits = len(str(max(1, self.blockCount())))
        space = 20 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), Qt.white)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = int(top + self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                color = QColor("red") if block_number in self.block_signals else QColor("black")
                painter.setPen(color)
                painter.drawText(0, top, self.line_number_area.width() - 10, self.fontMetrics().height(),
                                 Qt.AlignRight, number)
            block = block.next()
            top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
            bottom = int(top + self.blockBoundingRect(block).height())
            block_number += 1

        # Draw right border
        border_color = QColor("#cccccc")  # light gray
        painter.setPen(border_color)
        painter.drawLine(self.line_number_area.width() - 1, event.rect().top(),
                         self.line_number_area.width() - 1, event.rect().bottom())

    def keyPressEvent(self, event):
        """Handle special key events for code editing"""
        # Ctrl+/ for comment/uncomment
        if event.key() == Qt.Key_Slash and event.modifiers() == Qt.ControlModifier:
            self.toggle_comment()
            return

        # Tab key - insert 4 spaces
        if event.key() == Qt.Key_Tab:
            cursor = self.textCursor()
            if cursor.hasSelection():
                # Indent selected lines
                self.indent_selection()
            else:
                # Insert 4 spaces
                cursor.insertText("    ")
            return

        # Shift+Tab - unindent
        if event.key() == Qt.Key_Backtab:
            self.unindent_selection()
            return

        super().keyPressEvent(event)

    def toggle_comment(self):
        """Toggle comment on selected lines"""
        cursor = self.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        cursor.setPosition(start)
        cursor.movePosition(cursor.StartOfLine)
        start_block = cursor.blockNumber()

        cursor.setPosition(end)
        end_block = cursor.blockNumber()

        cursor.beginEditBlock()

        # Check if all lines are commented
        all_commented = True
        cursor.setPosition(start)
        cursor.movePosition(cursor.StartOfLine)

        for i in range(start_block, end_block + 1):
            cursor.select(cursor.LineUnderCursor)
            line = cursor.selectedText().lstrip()
            if line and not line.startswith('#'):
                all_commented = False
                break
            cursor.movePosition(cursor.Down)
            cursor.movePosition(cursor.StartOfLine)

        # Toggle comments
        cursor.setPosition(start)
        cursor.movePosition(cursor.StartOfLine)

        for i in range(start_block, end_block + 1):
            cursor.movePosition(cursor.StartOfLine)
            cursor.select(cursor.LineUnderCursor)
            line = cursor.selectedText()

            if all_commented:
                # Remove comment
                stripped = line.lstrip()
                if stripped.startswith('#'):
                    indent = len(line) - len(stripped)
                    new_line = line[:indent] + stripped[1:].lstrip()
                    cursor.insertText(new_line)
            else:
                # Add comment
                stripped = line.lstrip()
                indent = len(line) - len(stripped)
                new_line = line[:indent] + '# ' + stripped
                cursor.insertText(new_line)

            cursor.movePosition(cursor.Down)

        cursor.endEditBlock()

    def indent_selection(self):
        """Indent selected lines"""
        cursor = self.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        cursor.setPosition(start)
        cursor.movePosition(cursor.StartOfLine)
        start_block = cursor.blockNumber()

        cursor.setPosition(end)
        end_block = cursor.blockNumber()

        cursor.beginEditBlock()
        cursor.setPosition(start)
        cursor.movePosition(cursor.StartOfLine)

        for i in range(start_block, end_block + 1):
            cursor.insertText("    ")
            cursor.movePosition(cursor.Down)
            cursor.movePosition(cursor.StartOfLine)

        cursor.endEditBlock()

    def unindent_selection(self):
        """Unindent selected lines"""
        cursor = self.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        cursor.setPosition(start)
        cursor.movePosition(cursor.StartOfLine)
        start_block = cursor.blockNumber()

        cursor.setPosition(end)
        end_block = cursor.blockNumber()

        cursor.beginEditBlock()
        cursor.setPosition(start)
        cursor.movePosition(cursor.StartOfLine)

        for i in range(start_block, end_block + 1):
            cursor.select(cursor.LineUnderCursor)
            line = cursor.selectedText()

            # Remove up to 4 leading spaces
            spaces = 0
            for char in line:
                if char == ' ' and spaces < 4:
                    spaces += 1
                else:
                    break

            if spaces > 0:
                cursor.movePosition(cursor.StartOfLine)
                for _ in range(spaces):
                    cursor.deleteChar()

            cursor.movePosition(cursor.Down)
            cursor.movePosition(cursor.StartOfLine)

        cursor.endEditBlock()


class ScintillaCodeEditor(QsciScintilla):
    """Advanced code editor using QScintilla with syntax highlighting and code features"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Set the lexer for Python syntax highlighting
        self.lexer = QsciLexerPython(self)
        self.setLexer(self.lexer)

        font = None
        if sys.platform == "darwin":  # macOS
            font = QFont("JetBrains Mono", 12)
        else:  # Windows / Linux
            font = QFont("JetBrains Mono", 10)
        font.setStyleHint(QFont.Monospace)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setMarginsFont(font)
        self.lexer.setFont(font)

        # Line numbers
        self.setMarginType(0, QsciScintilla.NumberMargin)
        self.setMarginWidth(0, "00000")
        self.setMarginLineNumbers(0, True)

        # Current line highlighting
        self.setCaretLineVisible(True)
        self.setCaretLineBackgroundColor(QColor("#ffe4e4"))

        # Indentation
        self.setIndentationsUseTabs(False)
        self.setTabWidth(4)
        self.setIndentationGuides(True)
        self.setAutoIndent(True)

        # Brace matching
        self.setBraceMatching(QsciScintilla.SloppyBraceMatch)

        # Edge mode
        self.setEdgeMode(QsciScintilla.EdgeLine)
        self.setEdgeColumn(150)  # PEP 8 line length

        # Folding
        self.setFolding(QsciScintilla.BoxedTreeFoldStyle)

        # Auto-completion
        self.setAutoCompletionSource(QsciScintilla.AcsAll)
        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionCaseSensitivity(False)

        # Whitespace
        self.setWhitespaceVisibility(QsciScintilla.WsInvisible)

    def keyPressEvent(self, event):
        """Handle special key events"""
        # Ctrl+/ for comment/uncomment
        if event.key() == Qt.Key_Slash and event.modifiers() == Qt.ControlModifier:
            self.toggle_comment()
            return

        super().keyPressEvent(event)

    def toggle_comment(self):
        """Toggle comments on selected lines"""
        line_from, index_from, line_to, index_to = self.getSelection()

        if line_from == -1:
            # No selection, comment current line
            line_from = line_to = self.getCursorPosition()[0]

        # Check if all lines are commented
        all_commented = True
        for line in range(line_from, line_to + 1):
            text = self.text(line).lstrip()
            if text and not text.startswith('#'):
                all_commented = False
                break

        # Toggle comments
        self.beginUndoAction()
        for line in range(line_from, line_to + 1):
            text = self.text(line)
            stripped = text.lstrip()
            indent = len(text) - len(stripped)

            if all_commented:
                # Remove comment
                if stripped.startswith('# '):
                    new_text = text[:indent] + stripped[2:]
                elif stripped.startswith('#'):
                    new_text = text[:indent] + stripped[1:]
                else:
                    new_text = text
            else:
                # Add comment
                new_text = text[:indent] + '# ' + stripped

            self.setSelection(line, 0, line, len(text))
            self.replaceSelectedText(new_text)

        self.endUndoAction()

    def set_dark_mode(self, dark: bool):
        """Toggle dark mode for the editor"""
        if dark:
            # Dark mode colors
            self.setPaper(QColor("#1e1e1e"))
            self.setColor(QColor("#d4d4d4"))
            self.setCaretLineBackgroundColor(QColor("#2a2a2a"))
            self.setMarginsBackgroundColor(QColor("#1e1e1e"))
            self.setMarginsForegroundColor(QColor("#858585"))

            # Update lexer colors for dark mode
            self.lexer.setDefaultPaper(QColor("#1e1e1e"))
            self.lexer.setDefaultColor(QColor("#d4d4d4"))
            self.lexer.setPaper(QColor("#1e1e1e"))

            # Keywords
            self.lexer.setColor(QColor("#569cd6"), QsciLexerPython.Keyword)
            # Comments
            self.lexer.setColor(QColor("#6a9955"), QsciLexerPython.Comment)
            self.lexer.setColor(QColor("#6a9955"), QsciLexerPython.CommentBlock)
            # Strings
            self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.SingleQuotedString)
            self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.DoubleQuotedString)
            self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.TripleSingleQuotedString)
            self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.TripleDoubleQuotedString)
            # Functions
            self.lexer.setColor(QColor("#dcdcaa"), QsciLexerPython.ClassName)
            self.lexer.setColor(QColor("#dcdcaa"), QsciLexerPython.FunctionMethodName)
            # Numbers
            self.lexer.setColor(QColor("#b5cea8"), QsciLexerPython.Number)
        else:
            # Light mode (default)
            self.setPaper(QColor("#ffffff"))
            self.setColor(QColor("#000000"))
            self.setCaretLineBackgroundColor(QColor("#ffe4e4"))
            self.setMarginsBackgroundColor(QColor("#f0f0f0"))
            self.setMarginsForegroundColor(QColor("#000000"))

            # Reset lexer to defaults
            self.lexer.setDefaultPaper(QColor("#ffffff"))
            self.lexer.setDefaultColor(QColor("#000000"))
            self.lexer.setPaper(QColor("#ffffff"))

            # Use default colors
            self.lexer.setColor(QColor("#0000ff"), QsciLexerPython.Keyword)
            self.lexer.setColor(QColor("#008000"), QsciLexerPython.Comment)
            self.lexer.setColor(QColor("#008000"), QsciLexerPython.CommentBlock)
            self.lexer.setColor(QColor("#a31515"), QsciLexerPython.SingleQuotedString)
            self.lexer.setColor(QColor("#a31515"), QsciLexerPython.DoubleQuotedString)


class ConfigCodeEditor(QWidget):
    extracted_config = pyqtSignal(dict, dict)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        # The current code file
        self.code_file = None
        self.file_last_modified = None
        self.is_modified = False  # Track if document has unsaved changes

        # File watcher for external changes
        self.file_watcher = QFileSystemWatcher()
        self.file_watcher.fileChanged.connect(self.on_file_changed_externally)

        # Dark mode state
        self.dark_mode = False

        self.setContentsMargins(0, 0, 0, 0)
        self.setObjectName("config_code_editor")

        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Main editor Layout
        self.editor_container = QWidget(self)
        self.editor_container.setObjectName("editor_container")
        self.editor_layout = QVBoxLayout()
        self.editor_layout.setContentsMargins(10, 10, 10, 10)
        self.editor_layout.setSpacing(5)
        self.editor_layout.setObjectName("editor_layout")

        # Title
        self.editor_title_label = QLabel("Config Extractor Editor (beta)")
        self.editor_title_label.setObjectName("editor_title_label")
        self.editor_title_label.setAlignment(Qt.AlignCenter)

        # File name with unsaved indicator
        self.code_file_label = QLabel("No File Loaded")
        self.code_file_label.setObjectName("code_file_label")
        self.code_file_label.setAlignment(Qt.AlignCenter)

        # Code Editor - Use QScintilla if available, otherwise fallback
        if QSCI_AVAILABLE:
            self.code_text_editor = ScintillaCodeEditor()
        else:
            self.code_text_editor = CodeTextEditor()

        self.code_text_editor.setObjectName("code_text_editor")

        # Set placeholder text (different methods for different editors)
        placeholder_text = (
            "Blocks socProxy imports and lines corresponding to experiment instantiation or execution. \n"
            "Extracts \"config\" variable if present to send to configuration panel, and additional dictionaries.")
        if hasattr(self.code_text_editor, 'setPlaceholderText'):
            self.code_text_editor.setPlaceholderText(placeholder_text)

        # Connect text changed signal to track modifications
        if isinstance(self.code_text_editor, QsciScintilla):
            self.code_text_editor.textChanged.connect(self.on_text_changed)
            self.code_text_editor.textChanged.connect(self.fix_font_after_paste)
        else:
            self.code_text_editor.textChanged.connect(self.on_text_changed)
            self.code_text_editor.textChanged.connect(self.fix_font_after_paste)

        ### Editor Utilities Bar
        self.editor_utilities_container = QWidget()
        self.editor_utilities_container.setMaximumHeight(25)
        self.editor_utilities = QHBoxLayout(self.editor_utilities_container)
        self.editor_utilities.setContentsMargins(2, 0, 2, 0)
        self.editor_utilities.setSpacing(5)
        self.editor_utilities.setObjectName("editor_utilities")

        spacerItem = QSpacerItem(0, 30, QSizePolicy.Expanding, QSizePolicy.Fixed)  # spacer

        # Find Bar
        self.find_bar = FindBar(self.code_text_editor)

        self.editor_utilities.addWidget(self.editor_title_label)
        self.editor_utilities.addWidget(self.code_file_label)
        self.editor_utilities.addItem(spacerItem)
        self.editor_utilities.addWidget(self.find_bar)

        ### Editor Execution Bar (Vertical Sidebar)
        self.editor_execution_container = QWidget()
        self.editor_execution_container.setMaximumWidth(32)
        self.editor_execution_layout = QVBoxLayout(self.editor_execution_container)
        self.editor_execution_layout.setContentsMargins(4, 4, 4, 4)
        self.editor_execution_layout.setSpacing(0)
        self.editor_execution_container.setObjectName("editor_execution_container")

        # Buttons
        self.run_editor_button = Helpers.create_button("", "run_editor_button", True, self.editor_utilities_container,
                                                       False)
        self.run_editor_button.setToolTip("Extract Config")
        self.run_editor_button.clicked.connect(self.run_script_blocking_funcs)

        self.open_codefile_button = Helpers.create_button("", "open_codefile_button", True,
                                                          self.editor_utilities_container, False)
        self.open_codefile_button.setToolTip("Open File")
        self.open_codefile_button.clicked.connect(self.open_codefile)

        self.save_codefile_button = Helpers.create_button("", "save_codefile_button", True,
                                                          self.editor_utilities_container, False)
        self.save_codefile_button.setToolTip("Save Changes")
        self.save_codefile_button.clicked.connect(self.save_codefile)

        self.search_codefile_button = Helpers.create_button("", "search_codefile_button", True,
                                                            self.editor_utilities_container, False)
        self.search_codefile_button.setToolTip("Search (Ctrl+F)")
        self.search_codefile_button.clicked.connect(self.toggle_find_bar)

        # Dark mode toggle button
        self.darkmode_button = Helpers.create_button("", "darkmode_button", True, self.editor_utilities_container,
                                                     False)
        self.darkmode_button.setToolTip("Toggle Dark Mode")
        self.darkmode_button.clicked.connect(self.toggle_dark_mode)

        spacerItem2 = QSpacerItem(32, 0, QSizePolicy.Fixed, QSizePolicy.Expanding)  # spacer

        self.editor_execution_layout.addWidget(self.run_editor_button)
        self.editor_execution_layout.addWidget(self.open_codefile_button)
        self.editor_execution_layout.addWidget(self.save_codefile_button)
        self.editor_execution_layout.addWidget(self.search_codefile_button)
        self.editor_execution_layout.addWidget(self.darkmode_button)
        self.editor_execution_layout.addItem(spacerItem2)

        ### Horizontal Layout (sidebar on left, editor on right)
        self.editor_horizontal_container = QWidget()
        self.editor_horizontal_layout = QHBoxLayout(self.editor_horizontal_container)
        self.editor_horizontal_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_horizontal_layout.setSpacing(0)
        self.editor_horizontal_layout.setObjectName("editor_horizontal_layout")
        self.editor_horizontal_layout.addWidget(self.editor_execution_container)
        self.editor_horizontal_layout.addWidget(self.code_text_editor)

        # Add everything to editor layout
        self.editor_layout.addWidget(self.editor_utilities_container)
        self.editor_layout.addWidget(self.editor_horizontal_container)

        self.editor_container.setLayout(self.editor_layout)
        self.main_layout.addWidget(self.editor_container)
        self.setLayout(self.main_layout)

        # Shortcuts
        self.save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.save_shortcut.activated.connect(self.save_codefile)

        self.find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.find_shortcut.activated.connect(self.toggle_find_bar)

        self.run_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        self.run_shortcut.activated.connect(self.run_script_blocking_funcs)

    def on_text_changed(self):
        """Called when text in the editor changes"""
        if self.code_file and not self.is_modified:
            self.is_modified = True
            self.update_title_with_modified_indicator()

    def fix_font_after_paste(self):
        """Placeholder for font fixing after paste (from original code)"""
        # font = self.code_text_editor.font()
        # font.setPointSize(12)
        # self.code_text_editor.selectAll()
        # self.code_text_editor.setCurrentFont(font)
        pass

    def update_title_with_modified_indicator(self):
        """Update the file label to show unsaved changes indicator"""
        if self.code_file:
            filename = os.path.basename(self.code_file)
            if self.is_modified:
                self.code_file_label.setText(f"● {filename}")  # Dot indicates unsaved
                self.code_file_label.setStyleSheet("color: orange;")
            else:
                self.code_file_label.setText(filename)
                self.code_file_label.setStyleSheet("")

    def on_file_changed_externally(self, path):
        """Called when the file is modified externally"""
        if path == self.code_file and os.path.exists(path):
            # Check if file was actually modified (not just saved by us)
            current_modified = os.path.getmtime(path)

            if self.file_last_modified and current_modified != self.file_last_modified:
                # File was modified externally
                reply = QMessageBox.question(
                    self,
                    "File Changed",
                    f"The file '{os.path.basename(path)}' has been modified externally.\n\n"
                    "Do you want to reload it?\n"
                    "(Unsaved changes will be lost)",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )

                if reply == QMessageBox.Yes:
                    self.reload_file()
                else:
                    # User chose not to reload, stop watching to avoid repeated dialogs
                    self.file_watcher.removePath(path)
                    qInfo(f"Stopped watching file: {path}")

    def reload_file(self):
        """Reload the current file from disk"""
        if not self.code_file or not os.path.exists(self.code_file):
            return

        try:
            with open(self.code_file, 'r', encoding='utf-8') as f:
                code = f.read()

            # Update editor content
            if isinstance(self.code_text_editor, QsciScintilla):
                self.code_text_editor.setText(code)
            else:
                self.code_text_editor.setPlainText(code)

            # Update modification time and status
            self.file_last_modified = os.path.getmtime(self.code_file)
            self.is_modified = False
            self.update_title_with_modified_indicator()

            # Re-add to watcher if it was removed
            if self.code_file not in self.file_watcher.files():
                self.file_watcher.addPath(self.code_file)

            qInfo(f"Reloaded file: {self.code_file}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not reload file: \n{e}")
            qCritical(f"Could not reload file: \n{traceback.format_exc()}")

    def toggle_dark_mode(self):
        """Toggle dark mode for the editor"""
        self.dark_mode = not self.dark_mode

        if isinstance(self.code_text_editor, ScintillaCodeEditor):
            self.code_text_editor.set_dark_mode(self.dark_mode)
        else:
            # Basic dark mode for plain text editor
            if self.dark_mode:
                self.code_text_editor.setStyleSheet("""
                    QPlainTextEdit {
                        background-color: #1e1e1e;
                        color: #d4d4d4;
                    }
                """)
                # Update line number area colors
                if hasattr(self.code_text_editor, 'line_number_area'):
                    self.code_text_editor.line_number_area.setStyleSheet("""
                        QWidget#line_number_widget {
                            background-color: #1e1e1e;
                        }
                    """)
            else:
                self.code_text_editor.setStyleSheet("")
                if hasattr(self.code_text_editor, 'line_number_area'):
                    self.code_text_editor.line_number_area.setStyleSheet("")

    def closeEvent(self, event):
        """Handle window close event"""
        if self.is_modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )

            if reply == QMessageBox.Save:
                self.save_codefile()
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def toggle_find_bar(self):
        if self.find_bar.isVisible():
            self.find_bar.hide()
        else:
            self.find_bar.show()
            self.find_bar.search_input.setFocus()

    def open_codefile(self):
        # Check for unsaved changes
        if self.is_modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before opening a new file?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )

            if reply == QMessageBox.Save:
                self.save_codefile()
            elif reply == QMessageBox.Cancel:
                return

        code_file = Helpers.open_file_dialog("Open Python Config Extractor File", "Python Files (*.py)",
                                             "open_config_codefile", self, file=True)
        if code_file:
            # Remove old file from watcher
            if self.code_file and self.code_file in self.file_watcher.files():
                self.file_watcher.removePath(self.code_file)

            self.code_file = code_file
            try:
                with open(self.code_file, 'r', encoding='utf-8') as f:
                    code = f.read()

                # Set text based on editor type
                if isinstance(self.code_text_editor, QsciScintilla):
                    self.code_text_editor.setText(code)
                else:
                    self.code_text_editor.setPlainText(code)

                # Update file info
                filename = os.path.basename(self.code_file)
                self.file_last_modified = os.path.getmtime(self.code_file)
                self.is_modified = False
                self.update_title_with_modified_indicator()

                # Add to file watcher
                self.file_watcher.addPath(self.code_file)
                qInfo(f"Watching file for external changes: {self.code_file}")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not open config extractor file: \n{e}")
                qCritical("Could not open config extractor file: \n%s", traceback.format_exc())

    def save_codefile(self):
        if self.code_file is None:
            return

        try:
            # Get text based on editor type
            if isinstance(self.code_text_editor, QsciScintilla):
                text = self.code_text_editor.text()
            else:
                text = self.code_text_editor.toPlainText()

            # Temporarily remove from watcher to avoid triggering external change
            if self.code_file in self.file_watcher.files():
                self.file_watcher.removePath(self.code_file)

            with open(self.code_file, 'w', encoding='utf-8') as f:
                f.write(text)

            # Update modification tracking
            self.file_last_modified = os.path.getmtime(self.code_file)
            self.is_modified = False
            self.update_title_with_modified_indicator()

            # Re-add to watcher
            self.file_watcher.addPath(self.code_file)

            # Visual feedback
            self.save_codefile_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/check.svg');")
            QTimer.singleShot(2000, lambda: self.save_codefile_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/save.svg');"))

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")
            qCritical("Could not save config extractor file: \n%s", traceback.format_exc())

    def run_script_blocking_funcs(self):
        """
        Runs Python code from the editor and extracts a variable, while blocking specific function calls
        and banned imports.

        - Uses an AST check to detect banned imports statically.
        - Uses a runtime import hook to block dynamic/deep imports.
        - Blocks execution of ExperimentClass/ExperimentClassPlus subclasses via dummy class.
        - Also catches and reports execution errors.
        """
        import os
        import sys
        import ast
        import traceback
        from types import SimpleNamespace

        qInfo("Attempting Config Extraction:")
        banned_imports = ["socProxy"]  # Banned Imports

        # Get code based on editor type
        if isinstance(self.code_text_editor, QsciScintilla):
            code = self.code_text_editor.text().replace('\x00', '')
        else:
            code = self.code_text_editor.toPlainText().replace('\x00', '')

        # Step 1: AST static check for banned imports and class definitions
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split('.')[-1] in banned_imports:
                            qWarning(f"[Blocked] Import of '{alias.name}' is not allowed.")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split('.')[-1] in banned_imports:
                        qWarning(f"[Blocked] Import from '{node.module}' is not allowed.")
                elif isinstance(node, ast.ClassDef):
                    for base in node.bases:
                        if isinstance(base, ast.Name) and base.id in ("ExperimentClass", "ExperimentClassPlus"):
                            qWarning(
                                f"[Blocked] Defining subclass of ExperimentClass/ExperimentClassPlus: '{node.name}'")
        except Exception as e:
            print(f"Static analysis error: {e}")

        # Step 2: Define import hook and dummy loader
        class DummyLoader:
            """Simulates empty imports for blocked modules."""

            def __init__(self, app, name):
                self.app = app
                self.name = name

            def create_module(self, spec):
                dummy_module = SimpleNamespace()
                if self.name.endswith('socProxy'):
                    dummy_module.makeProxy = None
                    dummy_module.soc = self.app.soc
                    dummy_module.soccfg = self.app.soccfg
                return dummy_module

            def exec_module(self, module):
                pass  # do nothing

        class BlockImportHook:
            def __init__(self, app):
                self.app = app

            def find_spec(self_inner, fullname, path, target=None):
                if fullname.split('.')[-1] in banned_imports:
                    qWarning(f"[Blocked] Skipping import of '{fullname}'")
                    return importlib.util.spec_from_loader(fullname, DummyLoader(self.app, fullname))
                return None

        import_hook = BlockImportHook(self.app)
        sys.meta_path.insert(0, import_hook)

        # Step 3: Define dummy Experiment classes
        class DummyExperimentClass:
            def __init__(self, *args, **kwargs):
                qWarning("Skipped ExperimentClass/ExperimentClassPlus Initialization")
                pass

            def __getattr__(self, name):
                print("Skipped")
                return lambda *args, **kwargs: None

        # Step 4: Block specific functions (currently empty)
        def blocked_function(*args, **kwargs):
            print("Blocked function call.")

        blocked_funcs = {}

        namespace = {
            **{name: blocked_function for name in blocked_funcs},
            "ExperimentClass": DummyExperimentClass,
            "ExperimentClassPlus": DummyExperimentClass,
            "__builtins__": __builtins__
        }

        orig_cwd = os.getcwd()
        orig_sys_path = sys.path.copy()

        # Step 5: Execute code in script directory to allow relative imports
        try:
            # Use the directory where this script is being run as the current dir
            script_dir = os.path.dirname(os.path.abspath(self.code_file))  # folder of the loaded file
            sys.path.insert(0, script_dir)
            os.chdir(script_dir)

            # Get rid of plt intercept hook during the config extraction
            plt.show = self.app._original_show
            exec(code, namespace)
            plt.show = self._intercept_plt_show_wrapper()

        except Exception as e:
            qCritical("Error while running script:")
            qCritical(traceback.format_exc())
            traceback.print_exc()

        finally:
            os.chdir(orig_cwd)
            sys.path = orig_sys_path

            # List all variables that are dictionaries
            dict_vars = {
                name: value for name, value in namespace.items()
                if isinstance(value, dict) and name != "__builtins__"
            }
            # Prompt user to select classes using multi-checkbox dialog
            dialog = DualMultiCheckboxDialog(list(dict_vars.keys()), "Select Configs")
            if dialog.exec_():
                selected_global, selected_exp = dialog.get_selected()
            else:
                selected_global = []
                selected_exp = []

            global_config = {}
            exp_config = {}

            # Update config with these additional configs
            for dict_var_name in selected_global:
                global_config |= dict_vars[dict_var_name]
            for dict_var_name in selected_exp:
                exp_config |= dict_vars[dict_var_name]

            # Emit the final config
            self.extracted_config.emit(global_config, exp_config)
            qInfo("Extracted config.")

            try:
                sys.meta_path.remove(import_hook)
                self.run_editor_button.setStyleSheet(
                    "image: url('MasterProject/Client_modules/Desq_GUI/assets/check.svg');"
                )
                QTimer.singleShot(
                    2000,
                    lambda: self.run_editor_button.setStyleSheet(
                        "image: url('MasterProject/Client_modules/Desq_GUI/assets/play-green.svg');"
                    )
                )
            except ValueError:
                pass