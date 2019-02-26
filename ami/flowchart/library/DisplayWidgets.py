import logging
import asyncio
import pyqtgraph as pg
from PyQt5.QtWidgets import QLCDNumber
from PyQt5.QtCore import QRect
from ami import LogConfig
from ami.comm import AsyncGraphCommHandler


logger = logging.getLogger(LogConfig.get_package_name(__name__))


class AsyncFetcher(object):

    def __init__(self, name, topic, addr):
        self.name = name
        self.topic = topic
        self.addr = addr
        self.comm_handler = AsyncGraphCommHandler(addr)
        self.reply = None

    async def fetch(self):
        await asyncio.sleep(1)
        self.reply = await self.comm_handler.fetch(self.topic)
        if self.reply is None:
            logger.warn("failed to fetch %s from manager!" % self.topic)


class ScalarWidget(QLCDNumber):
    def __init__(self, name, topic, addr, parent=None):
        super(ScalarWidget, self).__init__(parent)
        self.fetcher = AsyncFetcher(name, topic, addr)
        self.setGeometry(QRect(320, 180, 191, 81))
        self.setDigitCount(10)
        self.setObjectName(topic)

    async def update(self):
        while True:
            await self.fetcher.fetch()
            if self.fetcher.reply is not None:
                self.display(self.fetcher.reply)


class AreaDetWidget(pg.ImageView):
    def __init__(self, name, topic, addr, parent=None):
        super(AreaDetWidget, self).__init__(parent)
        self.fetcher = AsyncFetcher(name, topic, addr)

    async def update(self):
        while True:
            await self.fetcher.fetch()
            if self.fetcher.reply is not None:
                self.setImage(self.fetcher.reply)


class WaveformWidget(pg.GraphicsLayoutWidget):
    def __init__(self, name, topic, addr, parent=None):
        super(WaveformWidget, self).__init__(parent)
        self.fetcher = AsyncFetcher(name, topic, addr)
        self.plot_view = self.addPlot()
        self.plot = None

    async def update(self):
        while True:
            await self.fetcher.fetch()
            if self.fetcher.reply is not None:
                self.waveform_updated(self.fetcher.reply)

    def waveform_updated(self, data):
        if self.plot is None:
            x, y = (list(data.keys()), list(data.values()))
            self.plot = self.plot_view.plot(x, y)
        else:
            self.plot.setData(y=list(data.values()))
