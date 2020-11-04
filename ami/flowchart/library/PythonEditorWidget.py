from pyqtgraph.Qt import QtWidgets, QtCore
from pyqode.python.backend import server
from pyqode.python.widgets import PyCodeEdit


class PythonEditorWidget(QtWidgets.QWidget):

    sigStateChanged = QtCore.Signal(object, object, object)

    def __init__(self, inputs, outputs, parent=None, text=""):
        super().__init__(parent)
        self.layout = QtWidgets.QGridLayout(self)

        self.inputs = inputs
        self.outputs = outputs
        try:
            self.editor = PyCodeEdit(server_script=server.__file__, parent=self)
        except Exception as e:
            print(e)
            self.editor = QtWidgets.QPlainTextEdit(parent=self)

        if text:
            self.editor.setPlainText(text)
        elif self.inputs:
            text = self.generate_template()
            self.editor.setPlainText(text)

        self.editor.textChanged.connect(self.stateChanged)
        self.layout.addWidget(self.editor, 0, 0, -1, -1)

    def generate_template(self):
        args = ', '.join([v.replace('.', '') for k, v in self.inputs.items()])
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
