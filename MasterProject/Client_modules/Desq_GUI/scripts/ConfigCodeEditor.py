"""
==================
ConfigCodeEditor.py
==================

This class contains the window for the config extractor code editor.

Running this config extractor runs the script via .exec(). Before execution, certain built-ins are applied. Notably, it
prevents the importing of certain dangerous modules such as socProxy, and blocks actual code execution such as .acquire.

Currently, this is a ban-list type of approach. Safer to move to a allow-list type of approach.
"""

import os
import traceback
import sys
import ast
import importlib.util
from types import SimpleNamespace

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QToolBar, QAction,
    QLineEdit, QHBoxLayout, QPushButton, QApplication,
    QFrame, QSpacerItem, QSizePolicy, QShortcut, QLabel,
    QMessageBox, QPlainTextEdit
)
from PyQt5.QtGui import QKeySequence, QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QPainter, QTextFormat
from PyQt5.QtCore import Qt, pyqtSignal, qCritical, qInfo, QTimer, QRegExp, QRect

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers

class FindBar(QFrame):
    def __init__(self, editor: QTextEdit, parent=None):
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.block_signals = []  # store blocked line numbers

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)

        self.update_line_number_area_width(0)

    def line_number_area_width(self):
        digits = len(str(max(1, self.blockCount())))
        space = 20 + self.fontMetrics().width('9') * digits
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


class ConfigCodeEditor(QWidget):

    extracted_config = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        # The current code file
        self.code_file = None

        self.setContentsMargins(0,0,0,0)
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
        self.editor_title_label = QLabel("Experiment Runner Editor (beta)")  # estimated experiment time
        self.editor_title_label.setObjectName("editor_title_label")
        self.editor_title_label.setAlignment(Qt.AlignCenter)
        # File name
        self.code_file_label = QLabel("No File Loaded")  # estimated experiment time
        self.code_file_label.setObjectName("code_file_label")
        self.code_file_label.setAlignment(Qt.AlignCenter)

        # Code Editor
        self.code_text_editor = CodeTextEditor()
        self.code_text_editor.setObjectName("code_text_editor")
        self.code_text_editor.setPlaceholderText("Blocks socProxy imports and lines corresponding to experiment instantiation or execution. \n"
                                                 "Extracts \"config\" variable if present to send to configuration panel.")

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

        ### Editor Execution Bar
        self.editor_execution_container = QWidget()
        self.editor_execution_container.setMaximumWidth(32)
        self.editor_execution_layout = QVBoxLayout(self.editor_execution_container)
        self.editor_execution_layout.setContentsMargins(4, 4, 4, 4)
        self.editor_execution_layout.setSpacing(0)
        self.editor_execution_container.setObjectName("editor_execution_container")

        self.run_editor_button = Helpers.create_button("", "run_editor_button", True, self.editor_utilities_container, False)
        self.run_editor_button.setToolTip("Extract Config")
        self.open_codefile_button = Helpers.create_button("", "open_codefile_button", True, self.editor_utilities_container, False)
        self.open_codefile_button.setToolTip("Open File")
        self.save_codefile_button = Helpers.create_button("", "save_codefile_button", True, self.editor_utilities_container, False)
        self.save_codefile_button.setToolTip("Save Changes")
        self.search_codefile_button = Helpers.create_button("", "search_codefile_button", True, self.editor_utilities_container, False)
        self.search_codefile_button.setToolTip("Search (Ctrl+F)")

        spacerItem = QSpacerItem(32, 0, QSizePolicy.Fixed, QSizePolicy.Expanding)  # spacer
        self.editor_execution_layout.addWidget(self.run_editor_button)
        self.editor_execution_layout.addWidget(self.open_codefile_button)
        self.editor_execution_layout.addWidget(self.save_codefile_button)
        self.editor_execution_layout.addWidget(self.search_codefile_button)
        self.editor_execution_layout.addItem(spacerItem)

        ### Horizontal Layout
        self.editor_horizontal_container = QWidget()
        self.editor_horizontal_layout = QHBoxLayout(self.editor_horizontal_container)
        self.editor_horizontal_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_horizontal_layout.setSpacing(0)
        self.editor_horizontal_layout.setObjectName("editor_horizontal_layout")
        self.editor_horizontal_layout.addWidget(self.editor_execution_container)
        self.editor_horizontal_layout.addWidget(self.code_text_editor)

        # Adding it all together
        self.editor_layout.addWidget(self.editor_utilities_container)
        self.editor_layout.addWidget(self.editor_horizontal_container)
        self.editor_container.setLayout(self.editor_layout)
        self.main_layout.addWidget(self.editor_container)
        self.setLayout(self.main_layout)

        self.setup_signals()

    def setup_signals(self):

        self.run_editor_button.clicked.connect(self.run_script_blocking_funcs)
        self.open_codefile_button.clicked.connect(self.open_codefile)
        self.save_codefile_button.clicked.connect(self.save_codefile)
        self.search_codefile_button.clicked.connect(self.toggle_find_bar)

        # Ctrl F Signals
        self.find_shortcut = QKeySequence("Ctrl+F")
        self.find_shortcut_handler = QShortcut(self.find_shortcut, self)
        self.find_shortcut_handler.activated.connect(self.toggle_find_bar)

        # Syntax highlighting
        self.code_text_editor.textChanged.connect(self.fix_font_after_paste)

    def fix_font_after_paste(self):
        # font = self.code_text_editor.font()
        # font.setPointSize(12)
        # self.code_text_editor.selectAll()
        # self.code_text_editor.setCurrentFont(font)

        # PythonHighlighter(self.code_text_editor.document())  # Adding IDEA like highlighting
        pass

    def toggle_find_bar(self):
        if self.find_bar.isVisible():
            self.find_bar.hide()
        else:
            self.find_bar.show()
            self.find_bar.search_input.setFocus()

    def open_codefile(self):
        self.code_file = Helpers.open_file_dialog("Open Python Config Extractor File", "Python Files (*.py)",
                                        "open_config_codefile", self, file=True)
        try:
            with open(self.code_file, 'r', encoding='utf-8') as f:
                code = f.read()
                self.code_text_editor.setPlainText(code)
                filename = os.path.basename(self.code_file)
                self.code_file_label.setText(filename)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open config extractor file: \n{e}")
            qCritical("Could not open config extractor file: \n%s", traceback.format_exc())

    def save_codefile(self):
        if self.code_file is None:
            return

        try:
            with open(self.code_file, 'w', encoding='utf-8') as f:
                f.write(self.code_text_editor.toPlainText())

            self.save_codefile_button.setStyleSheet("image: url('MasterProject/Client_modules/Desq_GUI/assets/check.svg');")
            QTimer.singleShot(2000, lambda: self.save_codefile_button.setStyleSheet("image: url('MasterProject/Client_modules/Desq_GUI/assets/save.svg');"))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")
            qCritical("Could not save config extractor file: \n%s", traceback.format_exc())

    # def run_script_blocking_funcs(self):
    #     """
    #     Safely execute a Python config file from the editor, with:
    #     - AST static analysis to block banned imports and subclasses of ExperimentClass
    #     - Runtime import hook to block dynamic/deep imports
    #     - Relative imports work correctly
    #     - Emits 'config' even if execution fails
    #     """
    #     banned_imports = ["socProxy"]
    #     code_file = self.code_file
    #     if code_file is None:
    #         QMessageBox.warning(self, "No File", "Please open a Python config file first.")
    #         return
    #
    #     # Step 1: Static AST analysis
    #     try:
    #         with open(code_file, "r", encoding="utf-8") as f:
    #             code = f.read().replace("\x00", "")
    #         tree = ast.parse(code)
    #         for node in ast.walk(tree):
    #             # Block banned imports
    #             if isinstance(node, ast.Import):
    #                 for alias in node.names:
    #                     if alias.name.split('.')[-1] in banned_imports:
    #                         raise ImportError(f"[Blocked] Import of '{alias.name}' is not allowed.")
    #             elif isinstance(node, ast.ImportFrom):
    #                 if node.module and node.module.split('.')[-1] in banned_imports:
    #                     raise ImportError(f"[Blocked] Import from '{node.module}' is not allowed.")
    #             # Block ExperimentClass subclasses
    #             elif isinstance(node, ast.ClassDef):
    #                 for base in node.bases:
    #                     if isinstance(base, ast.Name) and base.id == "ExperimentClass":
    #                         raise RuntimeError(f"[Blocked] Defining subclass of ExperimentClass: '{node.name}'")
    #     except Exception as e:
    #         qCritical(f"Static analysis blocked code: {e}")
    #         QMessageBox.critical(self, "Blocked Code", f"Code cannot be executed:\n{e}")
    #         return
    #
    #     # Step 2: Runtime import hook
    #     class DummyLoader:
    #         def __init__(self, name):
    #             self.name = name
    #
    #         def create_module(self, spec):
    #             return SimpleNamespace()
    #
    #         def exec_module(self, module):
    #             pass
    #
    #     class BlockImportHook:
    #         def __init__(self, banned):
    #             self.banned = banned
    #
    #         def find_spec(self_inner, fullname, path, target=None):
    #             if fullname.split('.')[-1] in self_inner.banned:
    #                 qInfo(f"[Blocked] Skipping import: {fullname}")
    #                 return importlib.util.spec_from_loader(fullname, DummyLoader(fullname))
    #             return None
    #
    #     import_hook = BlockImportHook(banned_imports)
    #     sys.meta_path.insert(0, import_hook)
    #
    #     # Step 3: Load file as a module
    #     try:
    #         spec = importlib.util.spec_from_file_location("__temp_config_module__", code_file)
    #         module = importlib.util.module_from_spec(spec)
    #         spec.loader.exec_module(module)
    #
    #         config = getattr(module, "config", {})
    #         self.extracted_config.emit(config)
    #         qInfo("Config extracted successfully.")
    #     except Exception as e:
    #         qCritical("Error during execution:")
    #         qCritical(traceback.format_exc())
    #         QMessageBox.critical(self, "Execution Error",
    #                              f"Error while running script:\n{e}\nConfig extraction will continue if possible.")
    #         # attempt to extract config even if partial execution
    #         config = getattr(module, "config", {}) if 'module' in locals() else {}
    #         self.extracted_config.emit(config)
    #     finally:
    #         try:
    #             sys.meta_path.remove(import_hook)
    #         except ValueError:
    #             pass
    #
    #         # Update run button icon
    #         self.run_editor_button.setStyleSheet(
    #             "image: url('MasterProject/Client_modules/Desq_GUI/assets/check.svg');")
    #         QTimer.singleShot(2000, lambda: self.run_editor_button.setStyleSheet(
    #             "image: url('MasterProject/Client_modules/Desq_GUI/assets/play-green.svg');"))

    def run_script_blocking_funcs(self):
        """
        Runs Python code from a QTextEdit and extracts a variable,while blocking specific function calls and banned imports.

        - Uses an AST check to detect banned imports statically.
        - Uses a runtime import hook to block dynamic/deep imports.
        - Stops execution of certain banned functions
        - Also catches and reports execution errors.

        """
        banned_imports = ["socProxy"] # Banned Imports

        code = self.code_text_editor.toPlainText().replace('\x00', '')

        # Step 1: AST static check for banned imports
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split('.')[-1] in banned_imports:
                            raise ImportError(f"[Blocked] Import of '{alias.name}' is not allowed.")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split('.')[-1] in banned_imports:
                        raise ImportError(f"[Blocked] Import from '{node.module}' is not allowed.")
        except Exception as e:
            print(f"Static analysis error: {e}")
            return

        # Step 2: Define import hook
        class BlockImportHook:
            def find_spec(self_inner, fullname, path, target=None):
                if fullname.split('.')[-1] in banned_imports:
                    print(f"[Blocked] Skipping import of '{fullname}'")
                    return importlib.util.spec_from_loader(fullname, DummyLoader(fullname))
                return None

        class DummyLoader:
            """
            The DummyLoader class is used to simulate an empty import and skip execution.
            """

            def __init__(self, name):
                self.name = name

            def create_module(self, spec):
                # Create a dummy module with the expected attributes as None or dummy functions
                dummy_module = SimpleNamespace()
                if self.name.endswith('socProxy'):
                    dummy_module.makeProxy = None  # or a dummy function if needed
                    dummy_module.soc = None
                    dummy_module.soccfg = None
                return dummy_module

            def exec_module(self, module):
                pass  # do nothing

        import_hook = BlockImportHook()
        sys.meta_path.insert(0, import_hook)

        # Step 3: Block selected function names
        def blocked_function(*args, **kwargs):
            print("Blocked function call.")

        blocked_funcs = {}  # Blocked Global Functions

        namespace = {
            **{name: blocked_function for name in blocked_funcs},
            "__builtins__": __builtins__
        }

        try:
            exec(code, namespace)

            config = namespace.get("config", {})
            self.extracted_config.emit(config)
            qInfo("Extracted config.")
        except Exception as e:
            qCritical("Error while running script:")
            qCritical(traceback.format_exc())
            QMessageBox.critical(self, "Error", f"Error while running script: \n{e}. "
                                                f"Still attempting config extraction. See Log.")
            traceback.print_exc()

            config = namespace.get("config", {})
            self.extracted_config.emit(config)
        finally:
            try:
                sys.meta_path.remove(import_hook)

                self.run_editor_button.setStyleSheet("image: url('MasterProject/Client_modules/Desq_GUI/assets/check.svg');")
                QTimer.singleShot(2000, lambda: self.run_editor_button.setStyleSheet("image: url('MasterProject/Client_modules/Desq_GUI/assets/play-green.svg');"))
            except ValueError:
                pass
