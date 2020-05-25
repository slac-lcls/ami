from qtpy import QtWidgets
from amitypes import Array1d
from ami.flowchart.library.common import CtrlNode
from ami.flowchart.library.DisplayWidgets import AsyncFetcher
import ami.graph_nodes as gn
import asyncio


class DialogWidget(QtWidgets.QWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(parent=parent)
        self.fetcher = None
        self.terms = terms
        self.sleep_clicked = False
        if addr:
            self.fetcher = AsyncFetcher(topics, terms, addr)

    async def update(self):
        while True:
            if self.sleep_clicked:
                self.sleep_clicked = False
                await asyncio.sleep(30)

            await self.fetcher.fetch()
            if self.fetcher.reply:
                self.value_updated(self.fetcher.reply)

    def value_updated(self, data):
        for term, name in self.terms.items():
            if data[name]:
                msg = QtWidgets.QMessageBox()
                sleep_btn = QtWidgets.QPushButton(f"Sleep 30 seconds")
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

    def to_operation(self, inputs, conditions={}):
        map_outputs = [self.name()+"_map"]
        outputs = [self.name()]
        threshold = self.values['Threshold']
        count = self.values['Count']

        nodes = [gn.Map(name=self.name()+"_operation",
                        condition_needs=conditions, inputs=inputs, outputs=map_outputs,
                        func=lambda arr: len(arr[arr > threshold]) > count, parent=self.name()),
                 gn.PickN(name=self.name()+"_pickN", inputs=map_outputs, outputs=outputs, parent=self.name())]

        return nodes
