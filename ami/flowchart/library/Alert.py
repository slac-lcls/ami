from PyQt5 import QtWidgets
from ami.flowchart.library.common import CtrlNode, MAX
from ami.flowchart.library.DisplayWidgets import AsyncFetcher
import ami.graph_nodes as gn
import asyncio


class DialogWidget:

    def __init__(self, topics, addr, parent=None, **kwargs):
        # super(DialogWidget, self).__init__(parent)
        self.parent = parent
        self.fetcher = AsyncFetcher(topics, addr)
        self.terms = kwargs.get('terms', {})

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


class Threshold(CtrlNode):

    """
    Display an alert when a scalar is greater than a threshold.
    """

    nodeName = "Threshold"
    uiTemplate = [("Threshold", 'intSpin', {'value': 0, 'min': 0, 'max': MAX})]

    def __init__(self, name):
        super(Threshold, self).__init__(name, terminals={'In': {'io': 'in', 'ttype': float}},
                                        buffered=True)
        self.dialog = None

    def display(self, topics, addr, win, **kwargs):
        if self.dialog is None:
            self.dialog = DialogWidget(topics, addr, win, **kwargs)

        if self.task is None:
            self.task = asyncio.ensure_future(self.dialog.update())

    def to_operation(self, inputs, conditions={}):
        map_outputs = [self.name()+"_map"]
        outputs = [self.name()]
        threshold = self.Threshold
        nodes = [gn.Map(name=self.name()+"_operation",
                        condition_needs=list(conditions.values()),
                        inputs=list(inputs.values()), outputs=map_outputs,
                        func=lambda i: i > threshold),
                 gn.PickN(name=self.name()+"_pickN",
                          inputs=map_outputs,
                          outputs=outputs)]
        return nodes
