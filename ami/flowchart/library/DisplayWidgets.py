import logging
import asyncio
import datetime as dt
import itertools as it
import numpy as np
import pyqtgraph as pg
from qtpy.QtWidgets import QLCDNumber
from qtpy.QtCore import QRect
from ami import LogConfig
from ami.comm import AsyncGraphCommHandler


logger = logging.getLogger(LogConfig.get_package_name(__name__))

colors = ['b', 'g', 'r']
symbols = ['o', 's', 't', 'd', '+']
symbols_colors = list(it.product(symbols, colors))


class AsyncFetcher(object):

    def __init__(self, topics={}, addr=None, buffered=False):
        self.names = list(topics.keys())
        if buffered:
            self.topics = list(topics.values())[0]
        else:
            self.topics = list(topics.values())
        self.comm_handler = AsyncGraphCommHandler(addr.name, addr.uri)
        self.buffered = buffered
        self.reply = {}
        self.last_updated = "Last Updated: None"

    def update_topics(self, topics={}):
        self.names = list(topics.keys())
        if self.buffered:
            self.topics = list(topics.values())[0]
        else:
            self.topics = list(topics.values())

    async def fetch(self):
        await asyncio.sleep(1)
        reply = await self.comm_handler.fetch(self.topics)

        if reply is not None:
            now = dt.datetime.now()
            now = now.strftime("%H:%M:%S")
            self.last_updated = f"Last Updated: {now}"
            if self.buffered and len(self.names) > 1:
                self.reply = dict(zip(self.names, zip(*reply)))
            elif self.buffered:
                self.reply = {self.names[0]: reply}
            else:
                self.reply = dict(zip(self.names, reply))
        else:
            self.reply = {}
            logger.warn("failed to fetch %s from manager!" % self.topics)


class ScalarWidget(QLCDNumber):

    def __init__(self, topics, addr, parent=None, **kwargs):
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

    def __init__(self, topics, addr, parent=None, **kwargs):
        super(AreaDetWidget, self).__init__(parent)
        self.fetcher = AsyncFetcher(topics, addr)
        handles = self.roi.getHandles()
        self.roi.removeHandle(handles[1])
        self.last_updated = pg.LabelItem(parent=self.getView())

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.last_updated.setText(self.fetcher.last_updated)
            for k, v in self.fetcher.reply.items():
                v = v.astype(np.float, copy=False)
                self.setImage(v)


class HistogramWidget(pg.GraphicsLayoutWidget):

    def __init__(self, topics, addr, parent=None, **kwargs):
        super(HistogramWidget, self).__init__(parent)
        self.fetcher = AsyncFetcher(topics, addr)
        self.plot_view = self.addPlot()
        self.plot_view.addLegend()
        self.plot = {}
        self.terms = kwargs.get('terms', {})
        self.last_updated = pg.LabelItem(parent=self.plot_view.getViewBox())

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.last_updated.setText(self.fetcher.last_updated)
            if self.fetcher.reply:
                self.histogram_updated(self.fetcher.reply)

    def histogram_updated(self, data):
        i = 0
        for term, name in self.terms.items():

            x, y = map(list, zip(*sorted(data[name].items())))

            if name not in self.plot:
                symbol, color = symbols_colors[i]
                i += 1
                self.plot[name] = self.plot_view.plot(x, y, name=name,
                                                      symbol=symbol,
                                                      symbolBrush=color)
            else:
                self.plot[name].setData(x=x, y=y)


class ScatterWidget(pg.GraphicsLayoutWidget):

    def __init__(self, topics, addr, parent=None, **kwargs):
        super(ScatterWidget, self).__init__(parent)
        self.fetcher = AsyncFetcher(topics, addr, buffered=True)
        self.plot_view = self.addPlot()
        self.plot_view.addLegend()
        self.plot = {}
        self.terms = kwargs.get('terms', {})
        self.last_updated = pg.LabelItem(parent=self.plot_view.getViewBox())

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.last_updated.setText(self.fetcher.last_updated)
            if self.fetcher.reply:
                self.scatter_updated(self.fetcher.reply)

    def scatter_updated(self, data):
        num_terms = int(len(self.terms)/2)
        for i in range(0, num_terms):
            x = "X"
            y = "Y"
            if i > 0:
                x += ".%d" % i
                y += ".%d" % i
            x = self.terms[x]
            y = self.terms[y]
            name = " vs ".join((x, y))
            x = data[x]
            y = data[y]

            if name not in self.plot:
                self.plot[name] = pg.ScatterPlotItem(name=name)
                self.plot_view.addItem(self.plot[name])
                self.plot_view.addLegend().addItem(self.plot[name], name=name)
            scatter = self.plot[name]
            symbol, color = symbols_colors[i]
            scatter.setData(x=x, y=y, symbol=symbol, brush=color)


class WaveformWidget(pg.GraphicsLayoutWidget):

    def __init__(self, topics, addr, parent=None, **kwargs):
        super(WaveformWidget, self).__init__(parent)
        self.fetcher = AsyncFetcher(topics, addr, buffered=True)
        self.plot_view = self.addPlot()
        self.plot_view.addLegend()
        self.plot = {}
        self.terms = kwargs.get('terms', {})
        self.last_updated = pg.LabelItem(parent=self.plot_view.getViewBox())

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.last_updated.setText(self.fetcher.last_updated)
            if self.fetcher.reply:
                self.waveform_updated(self.fetcher.reply)

    def waveform_updated(self, data):
        i = 0
        for term, name in self.terms.items():

            if name not in self.plot:
                symbol, color = symbols_colors[i]
                i += 1
                self.plot[name] = self.plot_view.plot(y=np.array(data[name]), name=name,
                                                      symbol=symbol, symbolBrush=color)
            else:
                self.plot[name].setData(y=np.array(data[name]))


class LineWidget(pg.GraphicsLayoutWidget):

    def __init__(self, topics, addr, parent=None, **kwargs):
        super(LineWidget, self).__init__(parent)
        self.fetcher = AsyncFetcher(topics, addr)
        self.plot_view = self.addPlot()
        self.plot_view.addLegend()
        self.plot = {}
        self.terms = kwargs.get('terms', {})
        self.last_updated = pg.LabelItem(parent=self.plot_view.getViewBox())

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.last_updated.setText(self.fetcher.last_updated)
            if self.fetcher.reply:
                self.line_updated(self.fetcher.reply)

    def line_updated(self, data):
        num_terms = int(len(self.terms)/2)
        for i in range(0, num_terms):
            x = "X"
            y = "Y"
            if i > 0:
                x += ".%d" % i
                y += ".%d" % i
            x = self.terms[x]
            y = self.terms[y]
            name = " vs ".join((x, y))
            x = data[x]
            y = data[y]

            if name not in self.plot:
                symbol, color = symbols_colors[i]
                i += 1
                self.plot[name] = self.plot_view.plot(x=x, y=y, name=name, symbol=symbol, symbolBrush=color)
            else:
                self.plot[name].setData(x=y, y=y)
