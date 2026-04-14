"""
===================
ConfigCodeEditor.py
===================

A sandboxed code editor for extracting configuration dictionaries from Python scripts.

This module provides a GUI editor window for loading, editing, and executing Python
configuration scripts in a controlled environment. The execution sandbox blocks
dangerous imports (e.g., ``socProxy``) and prevents actual hardware operations
(e.g., ``.acquire``) while allowing configuration dictionaries to be extracted.

.. note::
    Currently uses a **ban-list** approach for blocking dangerous operations.
    A safer **allow-list** approach should be considered for future versions.

Features
--------
- File watching for external changes with autosave sync
- Unsaved changes indicator (``•`` prefix on filename)
- Advanced code editing with QsciScintilla (syntax highlighting, auto-indent, commenting)
- Fallback to basic QPlainTextEdit when QScintilla unavailable
- Dark mode toggle for editor themes
- Find bar with Ctrl+F shortcut

Matplotlib Backend Integration
------------------------------
This module integrates with :mod:`BackendDesq` for plot interception:

- Uses BackendDesq for plot routing (not Agg backend)
- Config extraction temporarily disables plot sink to prevent figures from
  routing to GUI tabs (which would have no valid target)
- No ``plt.show`` monkey-patching needed - handled at canvas level

.. seealso::
    :mod:`BackendDesq` for plot sink management functions.
    :mod:`CheckboxDialogs` for the configuration selection dialog.

Module-level Variables
----------------------

:var QSCI_AVAILABLE: Whether QScintilla is available for advanced editing.
:vartype QSCI_AVAILABLE: bool
"""

import os
import traceback
import sys
import ast
import importlib.util
from types import SimpleNamespace
from typing import Optional, Dict, Any, List, Tuple

# NOTE: Do NOT set matplotlib backend here!
# The backend is already configured in Desq.py before this module is imported.
# Using matplotlib.use() here would conflict with BackendDesq.
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

    QSCI_AVAILABLE: bool = True
except ImportError:
    QSCI_AVAILABLE: bool = False
    qWarning("QScintilla not available. Install with: pip install QScintilla")

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers
from MasterProject.Client_modules.Desq_GUI.scripts.CheckboxDialogs import DualMultiCheckboxDialog

# Import BackendDesq functions for plot sink management
from MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq import (
    get_plot_sink, set_plot_sink, clear_plot_sink
)


class FindBar(QFrame):
    """
    A collapsible search bar widget for finding text in the code editor.

    Provides a text input field with a "Next" button and close button.
    Supports both QScintilla and QPlainTextEdit editor backends.

    :param editor: The code editor widget to search within.
    :type editor: QsciScintilla or QPlainTextEdit
    :param parent: Parent widget, defaults to None.
    :type parent: QWidget or None

    :ivar editor: Reference to the attached code editor.
    :vartype editor: QsciScintilla or QPlainTextEdit
    :ivar search_input: Text field for entering search queries.
    :vartype search_input: QLineEdit
    :ivar find_button: Button to trigger find next operation.
    :vartype find_button: QPushButton
    :ivar close_findbar_button: Button to hide the find bar.
    :vartype close_findbar_button: QPushButton
    """

    def __init__(self, editor: QWidget, parent: Optional[QWidget] = None) -> None:
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

    def find_next(self) -> None:
        """
        Find and highlight the next occurrence of the search text.

        Uses QScintilla's ``findFirst`` method for QScintilla editors,
        or the standard ``find`` method for QTextEdit/QPlainTextEdit.
        Wraps to the beginning of the document if no match is found.
        """
        text = self.search_input.text()
        if QSCI_AVAILABLE and isinstance(self.editor, QsciScintilla):
            # QScintilla find - parameters: text, re, cs, wo, wrap
            self.editor.findFirst(text, False, True, False, True)
        else:
            # Regular QTextEdit find - wrap to start if not found
            if not self.editor.find(text):
                self.editor.moveCursor(self.editor.textCursor().Start)
                self.editor.find(text)


class LineNumberArea(QWidget):
    """
    A widget that displays line numbers alongside a code editor.

    This widget is designed to be placed in the left margin of a
    :class:`CodeTextEditor` and repaints itself when the editor scrolls
    or resizes.

    :param editor: The code editor this line number area is attached to.
    :type editor: CodeTextEditor

    :ivar code_editor: Reference to the parent code editor.
    :vartype code_editor: CodeTextEditor
    """

    def __init__(self, editor: 'CodeTextEditor') -> None:
        super().__init__(editor)
        self.setObjectName("line_number_widget")
        self.code_editor = editor

    def sizeHint(self) -> 'Qt.QSize':
        """
        Return the recommended size for the line number area.

        :returns: Size hint with width based on digit count, height of 0.
        :rtype: Qt.QSize
        """
        return Qt.QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event: 'QPaintEvent') -> None:
        """
        Delegate painting to the code editor's paint method.

        :param event: The paint event containing the region to repaint.
        :type event: QPaintEvent
        """
        self.code_editor.line_number_area_paint_event(event)


class CodeTextEditor(QPlainTextEdit):
    """
    Enhanced plain text editor with line numbers and basic code editing features.

    Provides a fallback code editor when QScintilla is not available. Features
    include:

    - Line number display with error highlighting (red for flagged lines)
    - Tab key inserts 4 spaces
    - Ctrl+/ toggles comments on selected lines
    - Shift+Tab unindents selected lines

    :param parent: Parent widget, defaults to None.
    :type parent: QWidget or None

    :ivar line_number_area: Widget displaying line numbers.
    :vartype line_number_area: LineNumberArea
    :ivar block_signals: List of line numbers to highlight in red (e.g., errors).
    :vartype block_signals: list[int]
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.block_signals: List[int] = []  # Store blocked/error line numbers for red highlighting

        # Connect signals for line number area updates
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)

        self.update_line_number_area_width(0)

        # Set monospace font for code readability
        font = QFont("Courier New", 12)
        self.setFont(font)

        # Configure tab width to 4 spaces
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)

    def line_number_area_width(self) -> int:
        """
        Calculate the required width for the line number area.

        Width is based on the number of digits in the highest line number
        plus padding for visual spacing.

        :returns: Width in pixels for the line number margin.
        :rtype: int
        """
        digits = len(str(max(1, self.blockCount())))
        # 20px base padding + width per digit character
        space = 20 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _: int) -> None:
        """
        Update the viewport margins to accommodate the line number area.

        :param _: Block count (unused, required by signal signature).
        :type _: int
        """
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect: QRect, dy: int) -> None:
        """
        Update the line number area when the editor viewport changes.

        Handles both scrolling (dy != 0) and content changes (dy == 0).

        :param rect: The rectangle that needs updating.
        :type rect: QRect
        :param dy: Vertical scroll delta in pixels; 0 means no scroll.
        :type dy: int
        """
        if dy:
            # Scrolling - just scroll the line number area
            self.line_number_area.scroll(0, dy)
        else:
            # Content changed - repaint affected region
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        # Update width if viewport needs it
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event: 'QResizeEvent') -> None:
        """
        Handle resize events to reposition the line number area.

        :param event: The resize event.
        :type event: QResizeEvent
        """
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event: 'QPaintEvent') -> None:
        """
        Paint line numbers in the line number area.

        Draws line numbers right-aligned with a light gray border on the right.
        Lines in :attr:`block_signals` are drawn in red to indicate errors.

        :param event: The paint event containing the region to repaint.
        :type event: QPaintEvent
        """
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), Qt.white)

        # Iterate through visible blocks and draw line numbers
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = int(top + self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                # Use red color for error lines, black otherwise
                color = QColor("red") if block_number in self.block_signals else QColor("black")
                painter.setPen(color)
                painter.drawText(0, top, self.line_number_area.width() - 10, self.fontMetrics().height(),
                                 Qt.AlignRight, number)
            block = block.next()
            top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
            bottom = int(top + self.blockBoundingRect(block).height())
            block_number += 1

        # Draw right border separating line numbers from code
        border_color = QColor("#cccccc")  # Light gray
        painter.setPen(border_color)
        painter.drawLine(self.line_number_area.width() - 1, event.rect().top(),
                         self.line_number_area.width() - 1, event.rect().bottom())

    def keyPressEvent(self, event: 'QKeyEvent') -> None:
        """
        Handle special key events for code editing.

        Intercepts:
        - Ctrl+/ : Toggle comment on selected lines
        - Tab : Insert 4 spaces (or indent selection)
        - Shift+Tab : Unindent selection

        :param event: The key press event.
        :type event: QKeyEvent
        """
        # Ctrl+/ for comment/uncomment
        if event.key() == Qt.Key_Slash and event.modifiers() == Qt.ControlModifier:
            self.toggle_comment()
            return

        # Tab key - insert 4 spaces or indent selection
        if event.key() == Qt.Key_Tab:
            cursor = self.textCursor()
            if cursor.hasSelection():
                # Indent all selected lines
                self.indent_selection()
            else:
                # Insert 4 spaces at cursor
                cursor.insertText("    ")
            return

        # Shift+Tab - unindent selection
        if event.key() == Qt.Key_Backtab:
            self.unindent_selection()
            return

        super().keyPressEvent(event)

    def toggle_comment(self) -> None:
        """
        Toggle Python comments on selected lines.

        If all selected lines are commented (start with ``#``), removes the
        comment prefix. Otherwise, adds ``# `` prefix to all lines.
        Preserves indentation when adding/removing comments.
        """
        cursor = self.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        # Find the range of blocks (lines) in selection
        cursor.setPosition(start)
        cursor.movePosition(cursor.StartOfLine)
        start_block = cursor.blockNumber()

        cursor.setPosition(end)
        end_block = cursor.blockNumber()

        cursor.beginEditBlock()

        # Check if all non-empty lines are already commented
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

        # Toggle comments based on current state
        cursor.setPosition(start)
        cursor.movePosition(cursor.StartOfLine)

        for i in range(start_block, end_block + 1):
            cursor.movePosition(cursor.StartOfLine)
            cursor.select(cursor.LineUnderCursor)
            line = cursor.selectedText()

            if all_commented:
                # Remove comment - preserve indentation
                stripped = line.lstrip()
                if stripped.startswith('#'):
                    indent = len(line) - len(stripped)
                    new_line = line[:indent] + stripped[1:].lstrip()
                    cursor.insertText(new_line)
            else:
                # Add comment - preserve indentation
                stripped = line.lstrip()
                indent = len(line) - len(stripped)
                new_line = line[:indent] + '# ' + stripped
                cursor.insertText(new_line)

            cursor.movePosition(cursor.Down)

        cursor.endEditBlock()

    def indent_selection(self) -> None:
        """
        Indent all lines in the current selection by 4 spaces.

        Adds 4 spaces at the beginning of each selected line.
        """
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

    def unindent_selection(self) -> None:
        """
        Unindent all lines in the current selection by up to 4 spaces.

        Removes up to 4 leading spaces from each selected line.
        """
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

            # Count and remove up to 4 leading spaces
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
    """
    Advanced code editor using QScintilla with syntax highlighting and code features.

    Provides a feature-rich Python code editor with:

    - Python syntax highlighting via QsciLexerPython
    - Line numbers in left margin
    - Current line highlighting
    - Auto-indentation and indentation guides
    - Brace matching
    - Code folding
    - Auto-completion from document and APIs
    - Dark mode support

    :param parent: Parent widget, defaults to None.
    :type parent: QWidget or None

    :ivar lexer: Python syntax highlighter lexer.
    :vartype lexer: QsciLexerPython

    .. note::
        This class is only available when ``QSCI_AVAILABLE`` is True.
        Otherwise, :class:`CodeTextEditor` is used as a fallback.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # Set the lexer for Python syntax highlighting
        self.lexer = QsciLexerPython(self)
        self.setLexer(self.lexer)

        # Configure platform-specific monospace font
        font: Optional[QFont] = None
        if sys.platform == "darwin":  # macOS
            font = QFont("Menlo", 12)
        else:  # Windows / Linux
            font = QFont("Consolas", 10)
        font.setStyleHint(QFont.Monospace)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setMarginsFont(font)
        self.lexer.setFont(font)

        # Line numbers margin (margin 0)
        self.setMarginType(0, QsciScintilla.NumberMargin)
        self.setMarginWidth(0, "00000")
        self.setMarginLineNumbers(0, True)

        # Current line highlighting with light red background
        self.setCaretLineVisible(True)
        self.setCaretLineBackgroundColor(QColor("#ffe4e4"))

        # Indentation settings - use spaces, not tabs
        self.setIndentationsUseTabs(False)
        self.setTabWidth(4)
        self.setIndentationGuides(True)
        self.setAutoIndent(True)

        # Brace matching - highlights matching brackets/parens
        self.setBraceMatching(QsciScintilla.SloppyBraceMatch)

        # Edge mode - vertical line at column 150 (PEP 8 extended)
        self.setEdgeMode(QsciScintilla.EdgeLine)
        self.setEdgeColumn(150)

        # Code folding with boxed tree style
        self.setFolding(QsciScintilla.BoxedTreeFoldStyle)

        # Auto-completion from all sources after 2 characters
        self.setAutoCompletionSource(QsciScintilla.AcsAll)
        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionCaseSensitivity(False)

        # Whitespace visibility - hidden by default
        self.setWhitespaceVisibility(QsciScintilla.WsInvisible)

    def keyPressEvent(self, event: 'QKeyEvent') -> None:
        """
        Handle special key events for code editing.

        Intercepts Ctrl+/ for comment toggling.

        :param event: The key press event.
        :type event: QKeyEvent
        """
        # Ctrl+/ for comment/uncomment
        if event.key() == Qt.Key_Slash and event.modifiers() == Qt.ControlModifier:
            self.toggle_comment()
            return

        super().keyPressEvent(event)

    def toggle_comment(self) -> None:
        """
        Toggle Python comments on selected lines.

        Uses QScintilla's undo grouping for single-step undo/redo.
        If all selected lines are commented, removes comments.
        Otherwise, adds ``# `` prefix to all lines.
        """
        line_from, index_from, line_to, index_to = self.getSelection()

        if line_from == -1:
            # No selection - comment current line only
            line_from = line_to = self.getCursorPosition()[0]

        # Check if all non-empty lines are already commented
        all_commented = True
        for line in range(line_from, line_to + 1):
            text = self.text(line).lstrip()
            if text and not text.startswith('#'):
                all_commented = False
                break

        # Toggle comments in a single undo action
        self.beginUndoAction()
        for line in range(line_from, line_to + 1):
            text = self.text(line)
            stripped = text.lstrip()
            indent = len(text) - len(stripped)

            if all_commented:
                # Remove comment - handle both '# ' and '#' prefixes
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

    def set_dark_mode(self, dark: bool) -> None:
        """
        Toggle dark mode color scheme for the editor.

        :param dark: True for dark mode, False for light mode.
        :type dark: bool
        """
        if dark:
            # Dark mode colors (VS Code inspired)
            self.setPaper(QColor("#1e1e1e"))
            self.setColor(QColor("#d4d4d4"))
            self.setCaretLineBackgroundColor(QColor("#2a2a2a"))
            self.setMarginsBackgroundColor(QColor("#1e1e1e"))
            self.setMarginsForegroundColor(QColor("#858585"))

            # Update lexer colors for dark mode
            self.lexer.setDefaultPaper(QColor("#1e1e1e"))
            self.lexer.setDefaultColor(QColor("#d4d4d4"))
            self.lexer.setPaper(QColor("#1e1e1e"))

            # Syntax highlighting colors - VS Code dark theme inspired
            self.lexer.setColor(QColor("#569cd6"), QsciLexerPython.Keyword)
            self.lexer.setColor(QColor("#6a9955"), QsciLexerPython.Comment)
            self.lexer.setColor(QColor("#6a9955"), QsciLexerPython.CommentBlock)
            self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.SingleQuotedString)
            self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.DoubleQuotedString)
            self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.TripleSingleQuotedString)
            self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.TripleDoubleQuotedString)
            self.lexer.setColor(QColor("#dcdcaa"), QsciLexerPython.ClassName)
            self.lexer.setColor(QColor("#dcdcaa"), QsciLexerPython.FunctionMethodName)
            self.lexer.setColor(QColor("#b5cea8"), QsciLexerPython.Number)
        else:
            # Light mode (default colors)
            self.setPaper(QColor("#ffffff"))
            self.setColor(QColor("#000000"))
            self.setCaretLineBackgroundColor(QColor("#ffe4e4"))
            self.setMarginsBackgroundColor(QColor("#f0f0f0"))
            self.setMarginsForegroundColor(QColor("#000000"))

            # Reset lexer to light mode defaults
            self.lexer.setDefaultPaper(QColor("#ffffff"))
            self.lexer.setDefaultColor(QColor("#000000"))
            self.lexer.setPaper(QColor("#ffffff"))

            # Standard light mode syntax colors
            self.lexer.setColor(QColor("#0000ff"), QsciLexerPython.Keyword)
            self.lexer.setColor(QColor("#008000"), QsciLexerPython.Comment)
            self.lexer.setColor(QColor("#008000"), QsciLexerPython.CommentBlock)
            self.lexer.setColor(QColor("#a31515"), QsciLexerPython.SingleQuotedString)
            self.lexer.setColor(QColor("#a31515"), QsciLexerPython.DoubleQuotedString)


class ConfigCodeEditor(QWidget):
    """
    Main widget for the sandboxed configuration code editor.

    This widget provides a complete code editing environment for loading,
    editing, and executing Python configuration scripts. Execution is
    sandboxed to block dangerous imports and hardware operations.

    :param app: Reference to the main application for accessing soc/soccfg.
    :type app: QWidget
    :param parent: Parent widget, defaults to None.
    :type parent: QWidget or None

    :ivar app: Reference to main application.
    :vartype app: QWidget
    :ivar code_file: Path to the currently loaded Python file.
    :vartype code_file: str or None
    :ivar file_last_modified: Timestamp of last file modification on disk.
    :vartype file_last_modified: float or None
    :ivar is_modified: Whether the editor has unsaved changes.
    :vartype is_modified: bool
    :ivar file_watcher: Watches loaded file for external modifications.
    :vartype file_watcher: QFileSystemWatcher
    :ivar dark_mode: Current dark mode state.
    :vartype dark_mode: bool
    :ivar code_text_editor: The code editor widget (QScintilla or fallback).
    :vartype code_text_editor: ScintillaCodeEditor or CodeTextEditor
    :ivar find_bar: The find/search bar widget.
    :vartype find_bar: FindBar

    **Signals:**

    .. py:attribute:: extracted_config
        :type: pyqtSignal(dict, dict)

        Emitted when configuration is successfully extracted.
        First dict is global config, second is experiment config.

    **Keyboard Shortcuts:**

    - Ctrl+S : Save file
    - Ctrl+F : Toggle find bar
    - Ctrl+R : Run config extraction
    - Ctrl+/ : Toggle comments (handled by editor)

    .. seealso::
        :meth:`run_script_blocking_funcs` for the sandboxed execution logic.
    """

    extracted_config = pyqtSignal(dict, dict)

    def __init__(self, app: QWidget, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.app = app
        self.code_file: Optional[str] = None
        self.file_last_modified: Optional[float] = None
        self.is_modified: bool = False

        # File watcher for external changes
        self.file_watcher = QFileSystemWatcher()
        self.file_watcher.fileChanged.connect(self.on_file_changed_externally)

        # Dark mode state
        self.dark_mode: bool = False

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

        # Title label
        self.editor_title_label = QLabel("Config Extractor Editor (beta)")
        self.editor_title_label.setObjectName("editor_title_label")
        self.editor_title_label.setAlignment(Qt.AlignCenter)

        # File name label with unsaved indicator
        self.code_file_label = QLabel("No File Loaded")
        self.code_file_label.setObjectName("code_file_label")
        self.code_file_label.setAlignment(Qt.AlignCenter)

        # Code Editor - Use QScintilla if available, otherwise fallback
        if QSCI_AVAILABLE:
            self.code_text_editor: 'QsciScintilla | CodeTextEditor' = ScintillaCodeEditor()
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
        self.code_text_editor.textChanged.connect(self.on_text_changed)
        self.code_text_editor.textChanged.connect(self.fix_font_after_paste)

        ### Editor Utilities Bar (top bar with title, filename, find bar)
        self.editor_utilities_container = QWidget()
        self.editor_utilities_container.setMaximumHeight(25)
        self.editor_utilities = QHBoxLayout(self.editor_utilities_container)
        self.editor_utilities.setContentsMargins(2, 0, 2, 0)
        self.editor_utilities.setSpacing(5)
        self.editor_utilities.setObjectName("editor_utilities")

        spacerItem = QSpacerItem(0, 30, QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Find Bar
        self.find_bar = FindBar(self.code_text_editor)

        self.editor_utilities.addWidget(self.editor_title_label)
        self.editor_utilities.addWidget(self.code_file_label)
        self.editor_utilities.addItem(spacerItem)
        self.editor_utilities.addWidget(self.find_bar)

        ### Editor Execution Bar (Vertical Sidebar on left)
        self.editor_execution_container = QWidget()
        self.editor_execution_container.setMaximumWidth(32)
        self.editor_execution_layout = QVBoxLayout(self.editor_execution_container)
        self.editor_execution_layout.setContentsMargins(4, 4, 4, 4)
        self.editor_execution_layout.setSpacing(0)
        self.editor_execution_container.setObjectName("editor_execution_container")

        # Sidebar Buttons
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

        spacerItem2 = QSpacerItem(32, 0, QSizePolicy.Fixed, QSizePolicy.Expanding)

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

        # Keyboard Shortcuts
        self.save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.save_shortcut.activated.connect(self.save_codefile)

        self.find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.find_shortcut.activated.connect(self.toggle_find_bar)

        self.run_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        self.run_shortcut.activated.connect(self.run_script_blocking_funcs)

    def on_text_changed(self) -> None:
        """
        Handle text changes in the editor.

        Marks the document as modified and updates the title indicator.
        Only triggers on first change after save/load.
        """
        if self.code_file and not self.is_modified:
            self.is_modified = True
            self.update_title_with_modified_indicator()

    def fix_font_after_paste(self) -> None:
        """
        Placeholder for font fixing after paste operations.

        .. note::
            Currently disabled. Original implementation would reset font
            size after paste to handle clipboard formatting issues.
        """
        # font = self.code_text_editor.font()
        # font.setPointSize(12)
        # self.code_text_editor.selectAll()
        # self.code_text_editor.setCurrentFont(font)
        pass

    def update_title_with_modified_indicator(self) -> None:
        """
        Update the file label to show unsaved changes indicator.

        Displays ``* filename`` in orange when modified, plain filename
        otherwise.
        """
        if self.code_file:
            filename = os.path.basename(self.code_file)
            if self.is_modified:
                self.code_file_label.setText(f"* {filename}")  # Dot indicates unsaved
                self.code_file_label.setStyleSheet("color: orange;")
            else:
                self.code_file_label.setText(filename)
                self.code_file_label.setStyleSheet("")

    def on_file_changed_externally(self, path: str) -> None:
        """
        Handle external file modifications detected by file watcher.

        Prompts user to reload the file if it was modified externally.
        User can choose to reload (losing unsaved changes) or ignore
        (and stop watching the file to prevent repeated prompts).

        :param path: Path to the changed file.
        :type path: str
        """
        if path == self.code_file and os.path.exists(path):
            # Check if file was actually modified (not just saved by us)
            current_modified = os.path.getmtime(path)

            if self.file_last_modified and current_modified != self.file_last_modified:
                # File was modified externally - prompt user
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
                    # User chose not to reload - stop watching to avoid repeated dialogs
                    self.file_watcher.removePath(path)
                    qInfo(f"Stopped watching file: {path}")

    def reload_file(self) -> None:
        """
        Reload the current file from disk.

        Refreshes editor content from the file system, resetting the
        modification state and updating the file watcher.

        :raises: Shows error dialog if file cannot be read.
        """
        if not self.code_file or not os.path.exists(self.code_file):
            return

        try:
            with open(self.code_file, 'r', encoding='utf-8') as f:
                code = f.read()

            # Update editor content based on editor type
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

    def toggle_dark_mode(self) -> None:
        """
        Toggle dark mode for the editor.

        Switches between light and dark color schemes. Uses QScintilla's
        built-in theming for ScintillaCodeEditor, or CSS for fallback.
        """
        self.dark_mode = not self.dark_mode

        if isinstance(self.code_text_editor, ScintillaCodeEditor):
            self.code_text_editor.set_dark_mode(self.dark_mode)
        else:
            # Basic dark mode for plain text editor using stylesheets
            if self.dark_mode:
                self.code_text_editor.setStyleSheet("""
                    QPlainTextEdit {
                        background-color: #1e1e1e;
                        color: #d4d4d4;
                    }
                """)
                # Update line number area colors if available
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

    def closeEvent(self, event: 'QCloseEvent') -> None:
        """
        Handle window close event.

        Prompts user to save unsaved changes before closing.

        :param event: The close event.
        :type event: QCloseEvent
        """
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

    def toggle_find_bar(self) -> None:
        """
        Toggle visibility of the find bar.

        Shows the find bar and focuses the search input if hidden,
        hides it if visible.
        """
        if self.find_bar.isVisible():
            self.find_bar.hide()
        else:
            self.find_bar.show()
            self.find_bar.search_input.setFocus()

    def open_codefile(self) -> None:
        """
        Open a Python file in the editor.

        Prompts to save unsaved changes first, then opens a file dialog
        to select a Python file. Sets up file watching for external changes.

        :raises: Shows error dialog if file cannot be read.
        """
        # Check for unsaved changes first
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

    def save_codefile(self) -> None:
        """
        Save the current editor content to the loaded file.

        Temporarily removes the file from the watcher during save to
        prevent triggering external change detection. Shows visual
        feedback (checkmark icon) on successful save.

        :raises: Shows error dialog if file cannot be written.
        """
        if self.code_file is None:
            return

        try:
            # Get text based on editor type
            if isinstance(self.code_text_editor, QsciScintilla):
                text = self.code_text_editor.text()
            else:
                text = self.code_text_editor.toPlainText()

            # Temporarily remove from watcher to avoid triggering external change detection
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

            # Visual feedback - temporarily show checkmark icon
            self.save_codefile_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/check.svg');")
            QTimer.singleShot(2000, lambda: self.save_codefile_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/save.svg');"))

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")
            qCritical("Could not save config extractor file: \n%s", traceback.format_exc())

    def run_script_blocking_funcs(self) -> None:
        """
        Execute the editor code in a sandboxed environment and extract configuration.

        This method runs Python code from the editor while blocking specific function
        calls and banned imports. The execution sandbox provides multiple layers of
        protection:

        1. **AST static check**: Scans for banned imports and ExperimentClass subclasses
           before execution.
        2. **Runtime import hook**: Intercepts and blocks dynamic/deep imports of banned
           modules, replacing them with dummy modules.
        3. **Dummy ExperimentClass**: Prevents instantiation of experiment classes that
           could trigger hardware operations.

        After execution, prompts the user to select which dictionary variables to use
        as global and experiment configurations.

        **Matplotlib Integration:**

        Temporarily clears the plot sink so figures generated during config extraction
        don't route to GUI tabs (which would have no valid target). Restores the
        previous sink state after execution.

        **Emits:**
        - :attr:`extracted_config` with (global_config, exp_config) on success.

        .. warning::
            Uses ``exec()`` for code execution. While banned imports are blocked,
            this is inherently risky. The ban-list approach should be replaced with
            an allow-list for production environments in the future.

        .. note::
            The import hook is registered globally in ``sys.meta_path`` and removed
            in the finally block to avoid affecting other imports.

        :raises: Logs errors via qCritical but does not raise exceptions.
        """
        import os
        import sys
        import ast
        import traceback
        from types import SimpleNamespace

        qInfo("Attempting Config Extraction:")
        banned_imports: List[str] = ["socProxy"]  # Modules that should never be imported

        # Get code from editor, removing any null bytes that might cause issues
        if isinstance(self.code_text_editor, QsciScintilla):
            code = self.code_text_editor.text().replace('\x00', '')
        else:
            code = self.code_text_editor.toPlainText().replace('\x00', '')

        # ==========================================
        # Step 1: AST static check for banned imports and class definitions
        # This catches imports that are visible in the source code before execution
        # ==========================================
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
                    # Block subclassing of ExperimentClass which could trigger hardware
                    for base in node.bases:
                        if isinstance(base, ast.Name) and base.id in ("ExperimentClass"):
                            qWarning(
                                f"[Blocked] Defining subclass of ExperimentClass: '{node.name}'")
        except Exception as e:
            print(f"Static analysis error: {e}")

        # ==========================================
        # Step 2: Define import hook and dummy loader
        # This catches dynamic imports that the AST check might miss
        # ==========================================
        class DummyLoader:
            """
            Simulates empty imports for blocked modules.

            Returns a SimpleNamespace with appropriate dummy attributes
            for known blocked modules like socProxy.
            """

            def __init__(self, app: QWidget, name: str) -> None:
                self.app = app
                self.name = name

            def create_module(self, spec: Any) -> SimpleNamespace:
                """Create a dummy module with safe placeholder attributes."""
                dummy_module = SimpleNamespace()
                if self.name.endswith('socProxy'):
                    # Provide expected attributes that config scripts might reference
                    dummy_module.makeProxy = None
                    dummy_module.soc = self.app.soc
                    dummy_module.soccfg = self.app.soccfg
                return dummy_module

            def exec_module(self, module: Any) -> None:
                """No-op execution for dummy modules."""
                pass

        class BlockImportHook:
            """
            Import hook that intercepts and blocks banned module imports.

            Registered in sys.meta_path to catch all import attempts.
            """

            def __init__(self, app: QWidget) -> None:
                self.app = app

            def find_spec(self_inner, fullname: str, path: Any, target: Any = None) -> Any:
                """Check if import should be blocked and return dummy spec if so."""
                if fullname.split('.')[-1] in banned_imports:
                    qWarning(f"[Blocked] Skipping import of '{fullname}'")
                    return importlib.util.spec_from_loader(fullname, DummyLoader(self.app, fullname))
                return None

        import_hook = BlockImportHook(self.app)
        sys.meta_path.insert(0, import_hook)

        # ==========================================
        # Step 3: Define dummy Experiment classes
        # Prevents actual experiment instantiation which could trigger hardware
        # ==========================================
        class DummyExperimentClass:
            """
            Placeholder for ExperimentClass that prevents hardware operations.

            All method calls return no-op lambdas.
            """

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                qWarning("Skipped ExperimentClass Initialization")
                pass

            def __getattr__(self, name: str) -> Any:
                """Return no-op for any attribute access."""
                print("Skipped")
                return lambda *args, **kwargs: None

        # ==========================================
        # Step 4: Define blocked functions namespace
        # Currently empty but extensible for future function blocking
        # ==========================================
        def blocked_function(*args: Any, **kwargs: Any) -> None:
            """Placeholder for explicitly blocked function calls."""
            print("Blocked function call.")

        blocked_funcs: Dict[str, Any] = {}

        # Build the execution namespace with blocked items and builtins
        namespace: Dict[str, Any] = {
            **{name: blocked_function for name in blocked_funcs},
            "ExperimentClass": DummyExperimentClass,
            "__builtins__": __builtins__
        }

        # Save original directory state for restoration
        orig_cwd = os.getcwd()
        orig_sys_path = sys.path.copy()

        # ==========================================
        # Step 5: Execute code in script directory
        # Allows relative imports from the config file's location
        # ==========================================

        # Save and clear the plot sink so figures don't route to GUI during extraction
        saved_sink = get_plot_sink()

        try:
            # Change to the script's directory to allow relative imports
            script_dir = os.path.dirname(os.path.abspath(self.code_file))
            sys.path.insert(0, script_dir)
            os.chdir(script_dir)

            # Clear plot sink during config extraction
            # This prevents any matplotlib figures generated during extraction from
            # being routed to GUI tabs (which would fail since there's no valid target)
            clear_plot_sink()

            # Execute the user's code in the sandboxed namespace
            exec(code, namespace)

        except Exception as e:
            qCritical("Error while running script:")
            qCritical(traceback.format_exc())
            traceback.print_exc()

        finally:
            # Restore the plot sink to its previous state
            if saved_sink is not None:
                set_plot_sink(saved_sink)

            # Restore original directory and path state
            os.chdir(orig_cwd)
            sys.path = orig_sys_path

            # ==========================================
            # Extract dictionary variables for configuration selection
            # ==========================================
            dict_vars: Dict[str, dict] = {
                name: value for name, value in namespace.items()
                if isinstance(value, dict) and name != "__builtins__"
            }

            # Prompt user to select which dictionaries to use as configs
            dialog = DualMultiCheckboxDialog(list(dict_vars.keys()), "Select Configs")
            if dialog.exec_():
                selected_global, selected_exp = dialog.get_selected()
            else:
                selected_global = []
                selected_exp = []

            global_config: Dict[str, Any] = {}
            exp_config: Dict[str, Any] = {}

            # Merge selected dictionaries into config outputs
            for dict_var_name in selected_global:
                global_config |= dict_vars[dict_var_name]
            for dict_var_name in selected_exp:
                exp_config |= dict_vars[dict_var_name]

            # Emit the final configuration
            self.extracted_config.emit(global_config, exp_config)
            qInfo("Extracted config.")

            # Cleanup: remove import hook and show success feedback
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
                # Import hook already removed - ignore
                pass