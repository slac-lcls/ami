import amitypes
from pyqtgraph import FileDialog
from qtpy import QtWidgets, QtCore
try:
    from pyqode.python.backend import server
    # from pyqode.python.widgets import PyCodeEdit
    from pyqode.core import api, modes, panels
    from pyqode.python import modes as pymodes, panels as pypanels, widgets
    HAS_PYQODE = False
except ImportError:
    HAS_PYQODE = False
import tempfile
import importlib


class PythonEditorProc(object):

    def __init__(self, text):
        self.text = text
        self.file = None
        self.mod = None

    def load(self):
        self.file = tempfile.NamedTemporaryFile(mode='w', suffix='.py')
        self.file.write(self.text)
        self.file.flush()
        spec = importlib.util.spec_from_file_location("module.name", self.file.name)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

        if hasattr(self.mod, 'EventProcessor'):
            self.proc = self.mod.EventProcessor()
            self.func = self.proc.on_event
        else:
            self.proc = None
            self.func = self.mod.func

    def __call__(self, *args, **kwargs):
        if self.file is None:
            self.load()

        return self.func(*args, **kwargs)

    def __del__(self):
        if self.file:
            del self.mod
            self.file.close()

    def begin_run(self):
        if self.file is None:
            self.load()

        if self.proc:
            return self.proc.begin_run()

    def end_run(self):
        if self.file is None:
            self.load()

        if self.proc:
            return self.proc.end_run()

    def begin_step(self, step):
        if self.file is None:
            self.load()

        if self.proc:
            return self.proc.begin_step(step)

    def end_step(self, step):
        if self.file is None:
            self.load()

        if self.proc:
            return self.proc.end_step(step)

if HAS_PYQODE:
    class MyPythonCodeEdit(widgets.PyCodeEditBase):
        def __init__(self, parent=None):
            super().__init__(parent=parent)

            # starts the default pyqode.python server (which enable the jedi code
            # completion worker).
            self.backend.start(server.__file__)

            # some other modes/panels require the analyser mode, the best is to
            # install it first
            # self.modes.append(pymodes.DocumentAnalyserMode())

            # --- core panels
            self.panels.append(panels.FoldingPanel())
            self.panels.append(panels.LineNumberPanel())
            self.panels.append(panels.CheckerPanel())
            # self.panels.append(panels.SearchAndReplacePanel(),
            #                    panels.SearchAndReplacePanel.Position.BOTTOM)
            # self.panels.append(panels.EncodingPanel(), api.Panel.Position.TOP)
            # add a context menu separator between editor's
            # builtin action and the python specific actions
            self.add_separator()

            # --- python specific panels
            self.panels.append(pypanels.QuickDocPanel(), api.Panel.Position.BOTTOM)

            # --- core modes
            self.modes.append(modes.CaretLineHighlighterMode())
            self.modes.append(modes.CodeCompletionMode())
            self.modes.append(modes.ExtendedSelectionMode())
            self.modes.append(modes.FileWatcherMode())
            self.modes.append(modes.OccurrencesHighlighterMode())
            self.modes.append(modes.RightMarginMode())
            self.modes.append(modes.SmartBackSpaceMode())
            self.modes.append(modes.SymbolMatcherMode())
            self.modes.append(modes.ZoomMode())

            # ---  python specific modes
            self.modes.append(pymodes.CommentsMode())
            self.modes.append(pymodes.CalltipsMode())
            self.modes.append(pymodes.FrostedCheckerMode())
            self.modes.append(pymodes.PEP8CheckerMode())
            self.modes.append(pymodes.PyAutoCompleteMode())
            self.modes.append(pymodes.PyAutoIndentMode())
            self.modes.append(pymodes.PyIndenterMode())
            self.modes.append(pymodes.PythonSH(self.document()))


class PythonEditorWidget(QtWidgets.QWidget):

    sigStateChanged = QtCore.Signal(object, object, object)

    def __init__(self, parent=None, text="", export=False, node=None):
        super().__init__(parent)
        self.layout = QtWidgets.QGridLayout(self)

        if HAS_PYQODE:
            self.editor = MyPythonCodeEdit(parent=self)
        else:
            self.editor = QtWidgets.QPlainTextEdit(parent=self)
        self.editor.setPlainText(text)
        self.editor.textChanged.connect(self.stateChanged)

        if export:
            self.node = node
            self.exportBtn = QtWidgets.QPushButton("Export", parent=self)
            self.exportBtn.clicked.connect(self.export)

            self.layout.addWidget(self.exportBtn, 0, 0)

        self.layout.addWidget(self.editor, 1, 0, -1, -1)

    def stateChanged(self, *args):
        self.sigStateChanged.emit("text", None, self.editor.toPlainText())

    def saveState(self):
        return {'text': self.editor.toPlainText()}

    def restoreState(self, state):
        self.editor.setPlainText(state['text'])

    def close(self):
        self.editor.close()
        super().close()

    def export(self):
        self.exportWidget = ExportWidget(self.node, self.editor.toPlainText())
        self.exportWidget.show()


class ExportWidget(QtWidgets.QWidget):

    def __init__(self, node, text):
        super().__init__()

        self.node = node
        self.text = text

        self.setWindowTitle("Export")
        self.layout = QtWidgets.QFormLayout(self)
        self.setLayout(self.layout)

        self.name = QtWidgets.QLineEdit(parent=self)
        self.docstring = QtWidgets.QTextEdit(parent=self)
        self.ok = QtWidgets.QPushButton("Ok", parent=self)
        self.ok.clicked.connect(self.ok_clicked)

        self.layout.addRow("Name:", self.name)
        self.layout.addRow("Docstring:", self.docstring)
        self.layout.addWidget(self.ok)

    def ok_clicked(self):
        self.fileDialog = FileDialog(None, "Save File..", '.', "Python (*.py)")
        self.fileDialog.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        self.fileDialog.show()
        self.fileDialog.fileSelected.connect(self.saveFile)

    def saveFile(self, fileName):
        node_name = self.name.text()
        docstring = self.docstring.toPlainText()

        terminals = {}
        for name, term in self.node.terminals.items():
            state = term.saveState()
            state['ttype'] = amitypes.TypeDumper(term._type)
            terminals[name] = state

        template = self.export(node_name, docstring, terminals, self.text)
        if not fileName.endswith('.py'):
            fileName += '.py'
        with open(fileName, 'w') as f:
            f.write(template)

    def export(self, name, docstring, terminals, text):
        template = f"""
from ami.flowchart.Node import Node
import typing
import amitypes
import ami.graph_nodes as gn


{text}


class {name}(Node):

    \"""
    {docstring}
    \"""

    nodeName = "{name}"

    def __init__(self, name):
        super().__init__(name, terminals={terminals})

    def to_operation(self, **kwargs):
        proc = EventProcessor()

        return gn.Map(name=self.name()+"_operation", **kwargs,
                      func=proc.on_event,
                      begin_run=proc.begin_run,
                      end_run=proc.end_run,
                      begin_step=proc.begin_step,
                      end_step=proc.end_step)
        """

        return template
