from qtpy import QtWidgets
from amitypes import Array1d
from ami.flowchart.library.common import CtrlNode, MAX
from ami.flowchart.library.DisplayWidgets import AsyncFetcher
import ami.graph_nodes as gn


class DialogWidget(QtWidgets.QWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(parent=parent)
        if topics and terms and addr:
            self.fetcher = AsyncFetcher(topics, terms, addr)
        else:
            self.fetcher = None

    async def update(self):
        while True:
            await self.fetcher.fetch()
            if self.fetcher.reply:
                self.value_updated(self.fetcher.reply)

    def value_updated(self, data):
        for term, name in self.terms.items():
            if data[name]:
                msg = QtWidgets.QMessageBox()
                msg.setText(f"{name} exceeded threshold!")
                msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
                msg.exec_()


class ArrayThreshold(CtrlNode):

    """
    Display an alert when the values and number of values in an array are greater than a threshold and count.
    """

    nodeName = "ArrayThreshold"
    uiTemplate = [("Threshold", 'intSpin', {'value': 0, 'min': 0, 'max': MAX}),
                  ("Count", 'intSpin', {'value': 0, 'min': 0, 'max': MAX})]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d}},
                         buffered=True)
        self.dialog = None

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, DialogWidget, **kwargs)

    def to_operation(self, inputs, conditions={}):
        map_outputs = [self.name()+"_map"]
        outputs = [self.name()]
        threshold = self.Threshold
        count = self.Count

        nodes = [gn.Map(name=self.name()+"_operation",
                        condition_needs=list(conditions.values()),
                        inputs=list(inputs.values()), outputs=map_outputs,
                        func=lambda arr: len(arr[arr > threshold]) > count, parent=self.name()),
                 gn.PickN(name=self.name()+"_pickN", inputs=map_outputs, outputs=outputs, parent=self.name())]

        return nodes
