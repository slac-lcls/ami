import zmq
import logging
import asyncio
import zmq.asyncio
import datetime as dt
import itertools as it
import numpy as np
import pyqtgraph as pg
from qtpy.QtGui import QGridLayout
from qtpy.QtWidgets import QLCDNumber, QLabel, QWidget
from qtpy.QtCore import QRect, Qt, Signal
from ami import LogConfig


logger = logging.getLogger(LogConfig.get_package_name(__name__))

colors = ['b', 'g', 'r']
symbols = ['o', 's', 't', 'd', '+']
symbols_colors = list(it.product(symbols, colors))


class AsyncFetcher(object):

    def __init__(self, topics={}, addr=None, buffered=False):
        self.addr = addr
        self.ctx = zmq.asyncio.Context()
        self.poller = zmq.asyncio.Poller()
        self.sockets = []
        self.buffered = buffered
        self.data = {}
        self.last_updated = "Last Updated: None"
        self.update_topics(topics)

    @property
    def reply(self):
        if self.data.keys() == set(self.subs):
            if self.buffered and len(self.names) > 1:
                reply = {}
                for topic, value in self.data.items():
                    names = [name for name in self.names if self.topics[name] == topic]
                    reply.update(dict(zip(names, zip(*self.data[topic]))))
                return reply
            else:
                return {name: self.data[topic] for name, topic in self.topics.items()}
        else:
            return {}

    def update_topics(self, topics={}):
        self.names = list(topics.keys())
        self.topics = topics
        if self.buffered:
            self.subs = set(topics.values())
        else:
            self.subs = list(topics.values())

        for sock in self.sockets:
            self.poller.unregister(sock)
            sock.close()

        self.sockets = []
        self.view_subs = {}

        for topic in self.subs:
            sub_topic = "view:%s:%s" % (self.addr.name, topic)
            self.view_subs[sub_topic] = topic
            sock = self.ctx.socket(zmq.SUB)
            sock.setsockopt_string(zmq.SUBSCRIBE, sub_topic)
            sock.connect(self.addr.view)
            self.poller.register(sock, zmq.POLLIN)
            self.sockets.append(sock)

    async def fetch(self):
        for sock, flag in await self.poller.poll():
            if flag != zmq.POLLIN:
                continue
            topic = await sock.recv_string()
            await sock.recv_pyobj()
            reply = await sock.recv_pyobj()

            now = dt.datetime.now()
            now = now.strftime("%H:%M:%S")
            self.last_updated = f"Last Updated: {now}"
            self.data[self.view_subs[topic]] = reply


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
        super().__init__(parent)
        self.fetcher = AsyncFetcher(topics, addr)
        handles = self.roi.getHandles()
        self.roi.removeHandle(handles[1])
        self.last_updated = pg.LabelItem(parent=self.getView())
        self.pixel_value = pg.LabelItem(parent=self.getView())
        self.proxy = pg.SignalProxy(self.scene.sigMouseMoved,
                                    rateLimit=30,
                                    slot=self.cursor_hover_evt)

    def cursor_hover_evt(self, evt):
        pos = evt[0]
        pos = self.view.mapSceneToView(pos)
        if self.imageItem.image is not None:
            shape = self.imageItem.image.shape
            if 0 <= pos.x() <= shape[0] and 0 <= pos.y() <= shape[1]:
                x = int(pos.x())
                y = int(pos.y())
                z = self.imageItem.image[x, y]
                self.pixel_value.setText(f"x={x}, y={y}, z={z:.5g}")
                self.pixel_value.item.moveBy(0, 12)

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.last_updated.setText(self.fetcher.last_updated)
            for k, v in self.fetcher.reply.items():
                self.setImage(v)


class PixelDetWidget(pg.ImageView):

    sigClicked = Signal(object, object)

    def __init__(self, topics, addr, parent=None, **kwargs):
        self.plot = pg.PlotItem()
        self.plot.hideAxis('left')
        self.plot.hideAxis('bottom')
        super().__init__(parent=parent, view=self.plot)
        self.fetcher = AsyncFetcher(topics, addr)
        self.last_updated = pg.LabelItem(parent=self.plot)
        self.point = self.plot.plot([0], [0], symbolBrush=(200, 0, 0), symbol='+', symbolSize=25)
        self.pixel_value = pg.LabelItem(parent=self.getView())
        self.proxy = pg.SignalProxy(self.scene.sigMouseMoved,
                                    rateLimit=30,
                                    slot=self.cursor_hover_evt)

    def cursor_hover_evt(self, evt):
        pos = evt[0]
        pos = self.plot.getViewBox().mapSceneToView(pos)
        if self.imageItem.image is not None:
            shape = self.imageItem.image.shape
            if 0 <= pos.x() <= shape[0] and 0 <= pos.y() <= shape[1]:
                x = int(pos.x())
                y = int(pos.y())
                z = self.imageItem.image[x, y]
                self.pixel_value.setText(f"x={x}, y={y}, z={z:.5g}")
                self.pixel_value.item.moveBy(0, 12)

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.last_updated.setText(self.fetcher.last_updated)
            for k, v in self.fetcher.reply.items():
                self.setImage(v)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            ev.accept()
            view = self.plot.getViewBox()
            if self.imageItem.image is not None:
                shape = self.imageItem.image.shape
                pos = view.mapSceneToView(ev.pos())
                if 0 <= pos.x() <= shape[0] and 0 <= pos.y() <= shape[1]:
                    x = int(pos.x())
                    y = int(pos.y())
                    self.update_cursor(x, y)
                    self.sigClicked.emit(x, y)
        else:
            ev.ignore()

    def update_cursor(self, x, y):
        self.plot.removeItem(self.point)
        self.point = self.plot.plot([x], [y], symbolBrush=(200, 0, 0), symbol='+', symbolSize=25)


class HistogramWidget(pg.GraphicsLayoutWidget):

    def __init__(self, topics, addr, parent=None, **kwargs):
        super().__init__(parent)
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

        num_terms = int(len(self.terms)/2)
        for i in range(0, num_terms):
            x = "Bins"
            y = "Counts"

            if i > 0:
                x += f".{i}"
                y += f".{i}"

            x = self.terms[x]
            y = self.terms[y]
            name = y

            x = data[x]
            y = data[y]

            if name not in self.plot:
                _, color = symbols_colors[i]
                self.plot[name] = self.plot_view.plot(x, y, name=name, brush=color,
                                                      stepMode=True, fillLevel=0)
            else:
                self.plot[name].setData(x=x, y=y)


class Histogram2DWidget(pg.ImageView):

    def __init__(self, topics, addr, parent=None, **kwargs):
        self.plot = pg.PlotItem()
        super().__init__(parent, view=self.plot)
        self.fetcher = AsyncFetcher(topics, addr)
        self.terms = kwargs.get('terms', {})
        self.last_updated = pg.LabelItem(parent=self.plot)
        self.pixel_value = pg.LabelItem(parent=self.plot)
        self.proxy = pg.SignalProxy(self.scene.sigMouseMoved,
                                    rateLimit=30,
                                    slot=self.cursor_hover_evt)
        self.xbins = None
        self.ybins = None

    def cursor_hover_evt(self, evt):
        pos = evt[0]
        pos = self.plot.getViewBox().mapSceneToView(pos)
        if self.imageItem.image is not None:
            shape = self.imageItem.image.shape
            if self.xbins[0] <= pos.x() <= self.xbins[-1] and \
               self.ybins[0] <= pos.y() <= self.ybins[-1]:
                idxx = int(pos.x() - self.xbins[0]) % shape[0]
                idxy = int(pos.y() - self.ybins[0]) % shape[1]
                z = self.imageItem.image[idxx, idxy]
                self.pixel_value.setText(f"x={int(pos.x())}, y={int(pos.y())}, z={z:.5g}")
                self.pixel_value.item.moveBy(0, 12)

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.last_updated.setText(self.fetcher.last_updated)
            if self.fetcher.reply:
                data = self.fetcher.reply

                xbins = self.terms['XBins']
                ybins = self.terms['YBins']
                counts = self.terms['Counts']

                self.xbins = data[xbins]
                self.ybins = data[ybins]
                counts = data[counts]
                xscale = self.xbins[1] - self.xbins[0]
                yscale = self.ybins[1] - self.ybins[0]
                self.setImage(counts, pos=(self.xbins[0], self.ybins[0]), scale=(xscale, yscale))


class ScatterWidget(pg.GraphicsLayoutWidget):

    def __init__(self, topics, addr, parent=None, **kwargs):
        super().__init__(parent)
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
        super().__init__(parent)
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
        super().__init__(parent)
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
                self.plot[name].setData(x=x, y=y)


class ArrayWidget(QWidget):

    def __init__(self, topics, addr, parent=None, **kwargs):
        super().__init__(parent)
        self.fetcher = AsyncFetcher(topics, addr)
        self.terms = kwargs.get('terms', {})
        self.update_rate = kwargs.get('update_rate', 30)
        self.grid = QGridLayout(self)
        self.table = pg.TableWidget()
        self.last_updated = QLabel(parent=self)
        self.grid.addWidget(self.table, 0, 0)
        self.grid.setRowStretch(0, 10)
        self.grid.addWidget(self.last_updated, 1, 0)

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.last_updated.setText(self.fetcher.last_updated)
            if self.fetcher.reply:
                self.array_updated(self.fetcher.reply)
            await asyncio.sleep(self.update_rate)

    def array_updated(self, data):
        for term, name in self.terms.items():
            self.table.setData(data[name])
