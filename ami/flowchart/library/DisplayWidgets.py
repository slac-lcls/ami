import logging
import asyncio
import itertools as it
import pyqtgraph as pg
from PyQt5.QtWidgets import QLCDNumber
from PyQt5.QtCore import QRect
from ami import LogConfig
from ami.comm import AsyncGraphCommHandler


logger = logging.getLogger(LogConfig.get_package_name(__name__))

colors = ['b', 'g', 'r']
symbols = ['o', 's', 't', 'd', '+']
symbols_colors = list(it.product(symbols, colors))


class AsyncFetcher(object):

    def __init__(self, topics={}, addr=None):
        self.names = list(topics.keys())
        self.topics = list(topics.values())
        self.comm_handler = AsyncGraphCommHandler(addr)
        self.reply = {}

    async def fetch(self):
        await asyncio.sleep(1)
        reply = await self.comm_handler.fetch(self.topics)
        if reply:
            self.reply = dict(zip(self.names, reply))
        else:
            self.reply = {}
            logger.warn("failed to fetch %s from manager!" % self.topics.values())


class ScalarWidget(QLCDNumber):

    def __init__(self, topics, addr, parent=None):
        super(ScalarWidget, self).__init__(parent)
        self.fetcher = AsyncFetcher(topics, addr)
        self.setGeometry(QRect(320, 180, 191, 81))
        self.setDigitCount(10)

    async def update(self):
        while True:
            await self.fetcher.fetch()
            for k, v in self.fetcher.reply.items():
                self.display(v)


class AreaDetWidget(pg.ImageView):

    def __init__(self, topics, addr, parent=None):
        super(AreaDetWidget, self).__init__(parent)
        self.fetcher = AsyncFetcher(topics, addr)

    async def update(self):
        while True:
            await self.fetcher.fetch()
            for k, v in self.fetcher.reply.items():
                self.setImage(v)


class HistogramWidget(pg.GraphicsLayoutWidget):

    def __init__(self, topics, addr, parent=None):
        super(HistogramWidget, self).__init__(parent)
        self.fetcher = AsyncFetcher(topics, addr)
        self.plot_view = self.addPlot()
        self.plot_view.addLegend()
        self.plot = {}

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.histogram_updated(self.fetcher.reply)

    def histogram_updated(self, data):
        i = 0
        for name, data in data.items():
            x, y = map(list, zip(*sorted(data.items())))

            if name not in self.plot:
                symbol, color = symbols_colors[i]
                i += 1
                self.plot[name] = self.plot_view.plot(x, y, name=name,
                                                      symbol=symbol,
                                                      symbolBrush=color)
            else:
                self.plot[name].setData(x=x, y=y)


class ScatterWidget(pg.GraphicsLayoutWidget):

    def __init__(self, topics, addr, parent=None):
        super(ScatterWidget, self).__init__(parent)
        self.fetcher = AsyncFetcher(topics, addr)
        self.plot_view = self.addPlot()
        self.plot = {}

    async def update(self):
        while True:
            await self.fetcher.fetch()
            if self.fetcher.reply is not None:
                self.scatter_updated(self.fetcher.reply)

    def scatter_updated(self, data):
        x, y = data
        if self.plot is None:
            self.plot = self.plot_view.plot([x], [y], symbol='o')
        else:
            self.plot.setData(x=[x], y=[y])
