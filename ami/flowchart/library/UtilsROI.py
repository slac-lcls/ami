
"""
import ami.flowchart.library.UtilsROI as ur
"""
import math
import numpy as np
import pyqtgraph as pg
import logging
logger = logging.getLogger(__name__)

QPointF, QRectF = pg.QtCore.QPointF, pg.QtCore.QRectF
QPen, QBrush, QColor = pg.QtGui.QPen, pg.QtGui.QBrush, pg.QtGui.QColor


def distance(p):
    x, y = p.x(), p.y()
    return math.sqrt(x*x+y*y)


def angle(p):
    """returs the point angle in radians [-pi,pi] -> [0,2*pi] - clockwise"""
    x, y = p.x(), p.y()
    a = math.atan2(y,x)
    return a if a>=0 and a<np.pi else 2*np.pi+a


def unit_vector(p):
    r = distance(p)
    return QPointF(p.x()/r, p.y()/r)


def path_add_ellipse(p, br, a1=0, a2=2*np.pi, npoints=36):
    center = br.center()
    r1 = br.width() / 2.
    r2 = br.height() / 2.
    theta = np.linspace(a1, a2, npoints)
    x = center.x() + r1 * np.cos(theta)
    y = center.y() + r2 * np.sin(theta)
    p.moveTo(x[0], y[0])
    for i in range(1, len(x)):
      p.lineTo(x[i], y[i])
    return p


def path_add_cross(p, br, w=10):
    """arr cross to the bounding box center"""
    c = br.center()
    xc, yc = c.x(), c.y()
    p.moveTo(xc, yc-w)
    p.lineTo(xc, yc+w)
    p.moveTo(xc-w, yc)
    p.lineTo(xc+w, yc)
    p.moveTo(xc, yc)
    return p


class ArcROI(pg.ROI):
    def __init__(self, pos, size=None, radius=None, **kwargs):
        if size is None:
            if radius is None:
                raise TypeError("Must provide either size or radius.")
            size = (radius*2, radius*2)
        pg.ROI.__init__(self, pos, size, aspectLocked=True, **kwargs)

        self.sigRegionChanged.connect(self._clearPath)
        hlwidth = kwargs.get('hlwidth', None)
        self._addHandles(width=hlwidth)


    def _addHandles(self, width=4):
        h0 = self.addTranslateHandle([0.5, 0.5],             name='TranslateHandle  ')
        h1 = self.addScaleRotateHandle([1, 0.5], [0.5, 0.5], name='ScaleRotateHandle')
        h2 = self.addFreeHandle([0.8, 0.4], [0.5, 0.5], name='FreeHandle       ')
        if width is None: return
        h0.pen = h0.currentPen = QPen(QBrush(QColor('blue')),  width)
        h1.pen = h1.currentPen = QPen(QBrush(QColor('green')), width)
        h2.pen = h2.currentPen = QPen(QBrush(QColor('red')),   width)


    def _clearPath(self):
        self.path = None


    def _fix_free_handle_norm_position(self):
        """fix free-handle local position"""
        br1 = self.boundingRect()
        br1size = br1.size()
        #br1cent = br1.center()
        h = self.handles[2]
        p = QPointF(h['item'].pos()) # relative to boundingRect origin
        xrel, yrel = p.x()/br1size.width(), p.y()/br1size.height() # free handle normalized coordinates
        h['pos'] = pg.Point(xrel, yrel)


    def _constrain_handle_motion(self):
        """fix free-handle local position"""
        br1 = self.boundingRect()
        br1size = br1.size()
        h0,h1,h2 = self.handles # center / external / internal circle
        p0,p1,p2 = h0['pos'], h1['pos'], h2['pos']
        n1,n2 = p1-p0, p2-p0
        print(' normalized handle coordinates relative center n1: %s n2: %s' % (str(n1), str(n2)))
        print(' p2 x: %.3f y: %.3f' % (p2.x(), p2.y()))

        if n2.y()<0: h2['pos'] = pg.Point(p2.x(), 0.5)


    def shape(self):
        p = pg.QtGui.QPainterPath()

        br1 = self.boundingRect()
        for i,h in enumerate(self.handles): print(' %d %s handle position %s' % (i, h['name'], str(h['pos'])))
        for i,h in enumerate(self.handles): print(' %d %s h.item position %s' % (i, h['name'], str(h['item'].pos())))

        self._fix_free_handle_norm_position()
        #self._constrain_handle_motion()

        h0,h1,h2 = self.handles # center / external / internal circle
        p0,p1,p2 = h0['item'].pos(), h1['item'].pos(), h2['item'].pos()

        vh1 = p1 - p0 # br1.center() # point defining vector from center to h2
        vh2 = p2 - p0 # br1.center() # point defining vector from center to h2
        rad1 = distance(vh1)
        rad2 = distance(vh2)
        p3 = p0 + rad1*unit_vector(vh2)
        ang2 = angle(vh2)
        #print(' ang2[rad] : %.2f x: %.2f y: %.2f ' % (ang2, vh2.x(), vh2.y()))

        width = 2*rad2
        br2 = QRectF(0, 0, width, width)
        br2.moveCenter(br1.center()) #pg.QtCore.QPointF(100,100)
        logger.info('ArcROI.shape br2.center(): %s br2.size(): %s' % (str(br2.center()), str(br2.size())))

        p = path_add_ellipse(p, br1, a2=ang2)
        p.moveTo(p1)
        p.lineTo(p0)
        path_add_cross(p, br1, w=10)
        p.moveTo(p2)
        p.lineTo(p3)
        p = path_add_ellipse(p, br2, a2=ang2)

        #logger.info
        #print('center: %s h1: %s h2: %s' % (str(h0['item'].pos()), str(h1['item'].pos()), str(h2['item'].pos())))
        #print('ArcROI.boundingRect() center: %s size: %s' % (str(br1.center()), str(br1.size())))
        print('ArcROI.boundingRect() x: %.1f y: %.1f size: %s' % (br1.x(), br1.y(), str(br1.size())))
        print('center: %s r1: %.1f r2: %.1f a1: %.1f a2: %.1f' % (str(br1.center()), rad1, rad2, self.angle(), math.degrees(ang2)))
        #print('dir(self): %s' % str(dir(self)))
        o = self.mapToScene(br1.center())
        print('self.mapToScene: %s' % str(o))
        #extent, _, origin = self.getAffineSliceParams(self.widget.imageItem.image, self.widget.imageItem)

        return p


    def paint(self, p, opt, widget):
        p.setRenderHints(p.RenderHint.Antialiasing, True)
        #pen = QPen(QBrush(QColor('white')), 1)
        p.setPen(self.currentPen)
        p.drawPath(self.shape())

# EOF
