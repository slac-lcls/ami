import pyqtgraph as pg
import asyncio
from ami.comm import AsyncGraphCommHandler


class AsyncFetcher(object):

    def __init__(self, name, topic, addr):
        self.name = name
        self.topic = topic
        self.addr = addr
        self.comm_handler = AsyncGraphCommHandler(addr)
        self.reply = None

    async def fetch(self):
        await asyncio.sleep(1)
        reply = await self.comm_handler.fetch(self.topic)
        if reply is not None:
            self.reply = reply
        else:
            print("failed to fetch %s from manager!" % self.topic)


class AreaDetWidget(pg.ImageView):
    def __init__(self, name, topic, addr, parent=None):
        super(AreaDetWidget, self).__init__(parent)
        self.fetcher = AsyncFetcher(name, topic, addr)
        self.roi.sigRegionChangeFinished.connect(self.roi_updated)

    async def update(self):
        while True:
            await self.fetcher.fetch()
            if self.fetcher.reply is not None:
                self.setImage(self.fetcher.reply)

    def roi_updated(self, roi):
        shape, vector, origin = roi.getAffineSliceParams(self.image, self.getImageItem())

        def roi_func(image):
            return pg.affineSlice(image, shape, origin, vector, (0, 1))

        self.func = roi_func


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
