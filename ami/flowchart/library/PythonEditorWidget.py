from pyqtgraph.Qt import QtWidgets, QtCore
from pyqode.python.backend import server
# from pyqode.python.widgets import PyCodeEdit
from pyqode.core import api, modes, panels
from pyqode.python import modes as pymodes, panels as pypanels, widgets
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

    def __init__(self, parent=None, text="", export=False):
        super().__init__(parent)
        self.layout = QtWidgets.QGridLayout(self)

        # try:
        #     self.editor = PyCodeEdit(server_script=server.__file__, parent=self)
        # except Exception as e:
        #     self.editor = QtWidgets.QPlainTextEdit(parent=self)
        self.editor = MyPythonCodeEdit(parent=self)
        self.editor.setPlainText(text)
        self.editor.textChanged.connect(self.stateChanged)

        if export:
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
        pass
