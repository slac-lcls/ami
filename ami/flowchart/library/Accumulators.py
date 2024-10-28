from typing import Any
from qtpy import QtWidgets
from amitypes import Array1d, Array2d, Array3d, T
from ami.flowchart.Node import Node
from ami.flowchart.library.common import CtrlNode
import ami.graph_nodes as gn


class Pick1(Node):

    """
    Pick1 collects one of its input.
    """

    nodeName = "Pick1"

    def __init__(self, name):
        super().__init__(name,
                         terminals={'In': {'io': 'in', 'ttype': T},
                                    'Out': {'io': 'out', 'ttype': T}},
                         global_op=True)

    def to_operation(self, **kwargs):
        return gn.PickN(name=self.name()+"_operation", N=1, **kwargs)


class PickN(CtrlNode):

    """
    PickN collects N of its input.
    """

    nodeName = "PickN"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2})]

    def __init__(self, name):
        super().__init__(name,
                         terminals={'In': {'io': 'in', 'ttype': T},
                                    'Out': {'io': 'out', 'ttype': Array1d}},
                         allowAddInput=True,
                         global_op=True)

    def to_operation(self, **kwargs):
        return gn.PickN(name=self.name()+"_operation", N=self.values['N'], **kwargs)


class SumN(CtrlNode):

    """
    SumN sums N of its input.
    """

    nodeName = "SumN"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2})]

    def __init__(self, name):
        super().__init__(name,
                         global_op=True)
        self.ttype_prompt = None

    def terminal_prompt(self, name='', title='', **kwargs):
        prompt = QtWidgets.QWidget()
        prompt.layout = QtWidgets.QFormLayout(parent=prompt)
        prompt.type_selector = QtWidgets.QComboBox(prompt)
        prompt.ok = QtWidgets.QPushButton('Ok', parent=prompt)
        for typ in [Any, bool, float, Array1d, Array2d, Array3d]:
            prompt.type_selector.addItem(str(typ), typ)
        prompt.layout.addRow("Type:", prompt.type_selector)
        prompt.layout.addRow("", prompt.ok)
        prompt.setLayout(prompt.layout)
        prompt.setWindowTitle("Add " + name)
        return prompt

    def onCreate(self):
        self.ttype_prompt = self.terminal_prompt()
        self.ttype_prompt.ok.clicked.connect(self._addTerminals)
        self.ttype_prompt.show()

    def _addTerminals(self, **kwargs):
        ttype = self.ttype_prompt.type_selector.currentData()
        self.ttype_prompt.close()
        kwargs['name'] = self.nextTerminalName('In')
        kwargs['ttype'] = ttype
        kwargs['removable'] = False
        self.addInput(**kwargs)
        kwargs['name'] = 'Count'
        kwargs['ttype'] = int
        self.addOutput(**kwargs)
        kwargs['name'] = self.nextTerminalName('Out')
        kwargs['ttype'] = ttype
        self.addOutput(**kwargs)

    def to_operation(self, **kwargs):
        return gn.SumN(name=self.name()+"_operation", N=self.values['N'], **kwargs)


class RollingBuffer(CtrlNode):

    """
    RollingBuffer collects N of its input.
    """

    nodeName = "RollingBuffer"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2})]

    def __init__(self, name):
        super().__init__(name,
                         terminals={'In': {'io': 'in', 'ttype': T},
                                    'Out': {'io': 'out', 'ttype': Array1d}},
                         allowAddInput=True,
                         global_op=True)

    def to_operation(self, **kwargs):
        return gn.RollingBuffer(name=self.name()+"_operation", N=self.values['N'], **kwargs)


try:
    from ami.flowchart.library.PythonEditorWidget import PythonEditorWidget
    import tempfile
    import importlib

    class AccumulatorProc(object):

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
            self.accumulator = self.mod.Accumulator()

        def __call__(self, res, *rest):
            if self.file is None:
                self.load()

            return self.accumulator.reduction(res, *rest)

        def res_factory(self, *args):
            if self.file is None:
                self.load()

            return self.accumulator.reset(*args)

    class Accumulator(CtrlNode):
        """
        Accumulator
        """

        nodeName = "Accumulator"

        def __init__(self, name):
            super().__init__(name,
                             terminals={'In': {'io': 'in', 'ttype': Any},
                                        'Count': {'io': 'out', 'ttype': int},
                                        'Sum': {'io': 'out', 'ttype': Any}},
                             allowAddInput=True,
                             global_op=True)

            self.values = {'text': ''}

        def display(self, topics, terms, addr, win, **kwargs):
            if self.widget is None:
                if not self.values['text']:
                    self.values['text'] = self.generate_template()

                self.widget = PythonEditorWidget(win, self.values['text'], False)
                self.widget.sigStateChanged.connect(self.state_changed)

            return self.widget

        def generate_template(self):
            template = """
class Accumulator():

    def __init__(self):
        pass

    def reduction(self, res, *rest):
        pass

    def reset(self, *args):
        return 0, ()
            """

            return template

        def to_operation(self, **kwargs):
            proc = AccumulatorProc(self.values['text'])
            node = gn.Accumulator(name=self.name()+"_accumulated", **kwargs,
                                  res_factory=proc.res_factory, reduction=proc)
            return node

    class ReduceByKeyProc(object):

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
            self.reducebykey = self.mod.ReduceByKey()

        def __call__(self, res, *rest):
            if self.file is None:
                self.load()

            return self.reducebykey.reduction(res, *rest)

    class ReduceByKey(CtrlNode):
        """
        ReduceByKey
        """

        nodeName = "ReduceByKey"

        def __init__(self, name):
            super().__init__(name,
                             terminals={'Key': {'io': 'in', 'ttype': Any},
                                        'Value': {'io': 'in', 'ttype': Any},
                                        'Out': {'io': 'out', 'ttype': dict}},
                             global_op=True)

            self.values = {'text': ''}

        def display(self, topics, terms, addr, win, **kwargs):
            if self.widget is None:
                if not self.values['text']:
                    self.values['text'] = self.generate_template()

                self.widget = PythonEditorWidget(win, self.values['text'], False)
                self.widget.sigStateChanged.connect(self.state_changed)

            return self.widget

        def generate_template(self):
            template = """
class ReduceByKey():

    def __init__(self):
        pass

    def reduction(self, res, *rest):
        pass
            """

            return template

        def to_operation(self, **kwargs):
            proc = ReduceByKeyProc(self.values['text'])
            node = gn.ReduceByKey(name=self.name()+"_reduced", **kwargs, reduction=proc)
            return node

except ImportError:
    pass
