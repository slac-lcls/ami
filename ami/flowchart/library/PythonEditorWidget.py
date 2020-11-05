from pyqtgraph.Qt import QtWidgets, QtCore
from pyqode.python.backend import server
# from pyqode.python.widgets import PyCodeEdit
from pyqode.core import api, modes, panels
from pyqode.python import modes as pymodes, panels as pypanels, widgets


class MyPythonCodeEdit(widgets.PyCodeEditBase):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # starts the default pyqode.python server (which enable the jedi code
        # completion worker).
        self.backend.start(server.__file__)

        # some other modes/panels require the analyser mode, the best is to
        # install it first
        # self.modes.append(pymodes.DocumentAnalyserMode())

        #--- core panels
        self.panels.append(panels.FoldingPanel())
        self.panels.append(panels.LineNumberPanel())
        self.panels.append(panels.CheckerPanel())
        # self.panels.append(panels.SearchAndReplacePanel(),
        #                    panels.SearchAndReplacePanel.Position.BOTTOM)
        # self.panels.append(panels.EncodingPanel(), api.Panel.Position.TOP)
       # add a context menu separator between editor's
        # builtin action and the python specific actions
        self.add_separator()

        #--- python specific panels
        self.panels.append(pypanels.QuickDocPanel(), api.Panel.Position.BOTTOM)

        #--- core modes
        self.modes.append(modes.CaretLineHighlighterMode())
        self.modes.append(modes.CodeCompletionMode())
        self.modes.append(modes.ExtendedSelectionMode())
        self.modes.append(modes.FileWatcherMode())
        self.modes.append(modes.OccurrencesHighlighterMode())
        self.modes.append(modes.RightMarginMode())
        self.modes.append(modes.SmartBackSpaceMode())
        self.modes.append(modes.SymbolMatcherMode())
        self.modes.append(modes.ZoomMode())

        #---  python specific modes
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

    def __init__(self, inputs, outputs, parent=None, text=""):
        super().__init__(parent)
        self.layout = QtWidgets.QGridLayout(self)

        self.inputs = inputs
        self.outputs = outputs
        # try:
        #     self.editor = PyCodeEdit(server_script=server.__file__, parent=self)
        # except Exception as e:
        #     self.editor = QtWidgets.QPlainTextEdit(parent=self)
        self.editor = MyPythonCodeEdit(parent=self)
        
        if text:
            self.editor.setPlainText(text)
        elif self.inputs:
            text = self.generate_template()
            self.editor.setPlainText(text)

        self.editor.textChanged.connect(self.stateChanged)
        self.layout.addWidget(self.editor, 0, 0, -1, -1)

    def generate_template(self):
        args = []

        for arg in self.inputs.values():
            rarg = arg.replace('.', '_')
            rarg = rarg.replace(':', '_')
            rarg = rarg.replace(' ', '_')
            args.append(rarg)

        args = ', '.join(args)
        template = f"""

# entry point must be called func
def func({args}, *args, **kwargs):

    # return {len(self.outputs)} output(s)
    return"""

        return template

    def stateChanged(self, *args):
        self.sigStateChanged.emit("text", None, self.editor.toPlainText())

    def saveState(self):
        return {'text': self.editor.toPlainText()}

    def restoreState(self, state):
        self.editor.setPlainText(state['text'])

    def close(self):
        self.editor.close()
        super().close()
