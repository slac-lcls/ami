from qtpy import QtWidgets, QtCore
from typing import Any
from amitypes import Array1d
from ami.flowchart.library.common import CtrlNode
from ami.flowchart.library.DisplayWidgets import AsyncFetcher, CategoryWidget
import ami.graph_nodes as gn
import collections


class DialogWidget(QtWidgets.QWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(parent=parent)
        self.fetcher = None
        self.terms = terms
        self.sleep_clicked = False
        self.active = True
        self.sleep = QtCore.QTimer()
        self.sleep.timeout.connect(self.set_active)
        if addr:
            self.fetcher = AsyncFetcher(topics, terms, addr, parent=self)
            self.fetcher.start()

    def set_active(self):
        self.active = True

    def update(self):
        if self.sleep_clicked:
            self.sleep_clicked = False
            self.active = False
            self.sleep(30000)
        else:
            while self.fetcher.ready:
                if self.active:
                    self.value_updated(self.fetcher.reply)

    def value_updated(self, data):
        for term, name in self.terms.items():
            if data[name]:
                msg = QtWidgets.QMessageBox()
                sleep_btn = QtWidgets.QPushButton("Sleep 30 seconds")
                msg.setText(f"{name} exceeded threshold!")
                msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
                msg.addButton(sleep_btn, QtWidgets.QMessageBox.ButtonRole.ActionRole)
                msg.exec_()

                if msg.clickedButton() == sleep_btn:
                    self.sleep_clicked = True
                else:
                    self.sleep_clicked = False


class ArrayThreshold(CtrlNode):

    """
    Display an alert when the values and number of values in an array are greater than a threshold and count.
    """

    nodeName = "ArrayThreshold"
    uiTemplate = [("Threshold", 'intSpin', {'value': 0, 'min': 0}),
                  ("Count", 'intSpin', {'value': 0, 'min': 0})]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d}},
                         buffered=True)
        self.dialog = None

    def buffered_topics(self):
        return {in_var: self.name() for term, in_var in self.input_vars().items()}

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, DialogWidget, **kwargs)

    def to_operation(self, inputs, outputs, **kwargs):
        map_outputs = [self.name()+"_map"]
        threshold = self.values['Threshold']
        count = self.values['Count']

        nodes = [gn.Map(name=self.name()+"_operation",
                        inputs=inputs, outputs=map_outputs, **kwargs,
                        func=lambda arr: len(arr[arr > threshold]) > count),
                 gn.PickN(name=self.name()+"_pickN", inputs=map_outputs, outputs=outputs, **kwargs)]

        return nodes


class Monitor(CtrlNode):

    """
    Debug box which plots which boxes have an event in a heartbeat
    """

    nodeName = "Monitor"
    uiTemplate = [("Num Points", "intSpin", {'value': 100, 'min': 1})]

    def __init__(self, name):
        super().__init__(name,
                         terminals={'In': {'io': 'in', 'ttype': Any, 'optional': True}},
                         allowAddInput=True,
                         buffered=True)

    def addTerminal(self, *args, **opts):
        opts['optional'] = True
        return super().addTerminal(*args, **opts)

    def isChanged(self, restore_ctrl, restore_widget):
        return restore_ctrl

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, CategoryWidget, **kwargs)

    def to_operation(self, inputs, outputs, **kwargs):
        outputs = [self.name()+'.'+i for i in inputs.keys()]
        map_outputs = [self.name()+"_mapcounter"]
        buffer_output = [self.name()+"_count", self.name()+"_buffered"]

        def count(*args, **kwargs):
            res = {}
            for n, v in inputs.items():
                res[v.name] = int(kwargs.get(v.mapped_name, None) is not None)
            return res

        def map_unzip(count, a):
            res = collections.defaultdict(list)
            for r in a:
                for k, v in inputs.items():
                    res[v.name].append(r[v.name])

            res = tuple(res.values())
            if len(res) == 1:
                return res[0]
            else:
                return res

        nodes = [gn.Map(name=self.name()+"_counter", inputs=inputs, outputs=map_outputs, func=count, **kwargs),
                 gn.RollingBuffer(name=self.name()+"_buffer", N=self.values['Num Points'],
                                  inputs=map_outputs, outputs=buffer_output, **kwargs),
                 gn.Map(name=self.name()+"_operation", inputs=buffer_output, outputs=outputs,
                        func=map_unzip, **kwargs)]

        return nodes
