import sys
import os
os.environ['LIBGL_ALWAYS_INDIRECT'] = '1' # fix libGL messages
import math
import numpy as np
from PyQt5.QtWidgets import *
import pyqtgraph as pg


class ArcROI(pg.ROI):
    def __init__(self, pos, size=None, radius=None, **kwargs):

        if size is None:
            if radius is None:
                raise TypeError("Must provide either size or radius.")
            size = (radius*2, radius*2)
        pg.ROI.__init__(self, pos, size, aspectLocked=True, **kwargs)

        self.sigRegionChanged.connect(self._clearPath)
        self._addHandles()

        print('pyqtgraph.__version__', pg.__version__)
        print('pyqtgraph.Qt.VERSION_INFO', pg.Qt.VERSION_INFO)

    def _addHandles(self):
        h0 = self.addScaleRotateHandle([1, 0.5], [0.5, 0.5], name='ScaleRotateHandle')
        h1 = self.addTranslateHandle([0.5, 0.5],             name='TranslateHandle  ')
        h2 = self.addFreeHandle([0.8, 0.5], [0.5, 0.5],      name='FreeHandle       ') #pos=None, axes=None, item=None, name=None, index=None
        width = 4
        h0.pen = h0.currentPen = pg.QtGui.QPen(pg.QtGui.QBrush(pg.QtGui.QColor('blue')),  width)
        h1.pen = h1.currentPen = pg.QtGui.QPen(pg.QtGui.QBrush(pg.QtGui.QColor('green')), width)
        h2.pen = h2.currentPen = pg.QtGui.QPen(pg.QtGui.QBrush(pg.QtGui.QColor('red')),   width)


    def _clearPath(self):
        self.path = None


    def _fix_free_handle_norm_position(self):
        """fix free-handle local position"""
        br1 = self.boundingRect()
        br1size = br1.size()
        br1cent = br1.center()
        h = self.handles[2]
        p = pg.QtCore.QPointF(h['item'].pos()) - br1cent # free handle position(QPointF) relative to boundingRect center
        xrel, yrel = p.x()/br1size.width()+0.5, p.y()/br1size.height()+0.5 # free handle normalized coordinates
        h['pos'] = pg.Point(xrel, yrel)


    def shape(self):
        br1 = self.boundingRect()
        print('ArcROI.boundingRect() center: %s size: %s' % (str(br1.center()), str(br1.size())))
        for i,h in enumerate(self.handles): print(' %d %s handle position %s' % (i, h['name'], str(h['pos'])))
        for i,h in enumerate(self.handles): print(' %d %s h.item position %s' % (i, h['name'], str(h['item'].pos())))

        #self._fix_free_handle_norm_position()

        p = pg.QtGui.QPainterPath()
        return p


    def paint(self, p, opt, widget):
        p.setRenderHints(p.RenderHint.Antialiasing, True)
        p.setPen(self.currentPen)
        p.drawPath(self.shape())



class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('pyqtgraph')
        self.setGeometry(100, 100, 700, 500)
        imv = pg.ImageView()
        imv.setImage(np.random.normal(size=(250, 200)))
        imv.addItem(ArcROI((30,30), radius=40))
        layout = QHBoxLayout()
        layout.addWidget(imv)
        self.setLayout(layout)


a = QApplication(sys.argv)
w = Window()
w.show()
sys.exit(a.exec())
