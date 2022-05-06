
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


def str_point(p, fmt='(%.1f, %.1f)'):
    return fmt % (p.x(), p.y())


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


def norm_handle_positions(radius_out, radius_int, angle_deg_out, angle_deg_int):
    """handle position in the unit bounding rect of size [1,1]
       center is assumed in (0.5, 0.5), outer radius control handle is always in (1.0, 0.5)
       angle_deg_out rotates the whole bounding rect relative its center,
       so position of the rect defined in the corner is changing at this rotation,
       but all normalised position of handles are preserved.
       radius_int and angle_deg_int changes pos2 only.
    """
    fr = radius_int / radius_out
    a = math.radians(angle_deg_int)
    pos0 = [0.5, 0.5] # center position handle
    pos1 = [1.0, 0.5] # outer circle angle and radius control handle
    pos2 = [0.5*(1+fr*math.cos(a)), 0.5*(1+fr*math.sin(a))] # internale circle radius and cut angle
    return pos0, pos1, pos2


class ArcROI(pg.ROI):
    def __init__(self, center=(100,100), radius_out=100, radius_int=50, angle_deg_out=0, angle_deg_int=60, **kwargs):
        cx, cy = center
        ro, ri, ao, ai = radius_out, radius_int, angle_deg_out, angle_deg_int
        pos = (cx-ro, cy-ro) # for angle_deg_out=0 ONLY!
        size = (2*ro, 2*ro)
        pg.ROI.__init__(self, pos, size, aspectLocked=True, **kwargs)
        self._addHandles(radius_out, radius_int, angle_deg_out, angle_deg_int, width=kwargs.get('hlwidth', None))
        #self.set_shape_parameters(cx, cy, ro, ri, ao, ai)
        self.sigRegionChanged.connect(self._clearPath)


    def _addHandles(self, radius_out=100, radius_int=50, angle_deg_out=0, angle_deg_int=60, width=4):
        center, pos1, pos2 = norm_handle_positions(radius_out, radius_int, angle_deg_out, angle_deg_int)
        h0 = self.addTranslateHandle(center,         name='TranslateHandle  ')
        h1 = self.addScaleRotateHandle(pos1, center, name='ScaleRotateHandle')
        h2 = self.addFreeHandle(pos2, center,        name='FreeHandle       ')
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
        #h['pos'] = pg.Point(xrel, yrel)
        h['pos'] = (xrel, yrel)


    def set_shape_parameters(self, *args):
        #center_x, center_y, radius_out, radius_int, angle_deg_out, angle_deg_int = *args
        cx, cy, ro, ri, ao, ai = args
        e = 2*ro # extension - width and heights of the bounding rect

        # set handles' positions in normalized position
        h0,h1,h2 = self.handles # center / external / internal circle
        h0['pos'], h1['pos'], h2['pos'] = norm_handle_positions(ro, ri, ao, ai)

        self.setSize((e, e), finish=False)
        self.setAngle(ao, center=(0.5,0.5), update=True, finish=True) #centerLocal=(cx,cy)
        cview = self.mapToView(self.boundingRect().center()) # QPointF
        p = self.pos() # Point
        #print('YYY cx, cy, center_current, pos_cur:', cx, cy, cview, pos_cur)
        self.setPos(p.x() + cx - cview.x(), y=p.y() + cy - cview.y(), finish=False) # origin of the bounding box
        #self.setPos(cx-ro, y=cy-ro, finish=False) # origin of the bounding box

        ##self.roi.translate(p.x(), p.y(), False)
        #self.roi.rotate(10, center=None, snap=False, update=True, finish=True)


    def shape_parameters(self):
        """retreives shape parameters from current handles' positions and roi.pos/size
        """

        h0,h1,h2 = self.handles # center / external / internal circle
        p0,p1,p2 = h0['item'].pos(), h1['item'].pos(), h2['item'].pos()

        vh1 = p1 - p0 # br1.center() # point defining vector from center to h2
        vh2 = p2 - p0 # br1.center() # point defining vector from center to h2
        rad1 = distance(vh1)
        rad2 = distance(vh2)
        p3 = p0 + rad1*unit_vector(vh2)
        ang1_deg = self.angle()
        ang1 = math.radians(ang1_deg)
        ang2 = angle(vh2)
        ang2_deg = math.degrees(ang2)

        pos = self.pos()
        size = self.size()
        br1 = self.boundingRect()
        center  = self.mapToView(br1.center())
        #print('XXX ArcROI.pos: (%.1f, %.1f) size(%.1f, %.1f) rad1:%.1f rad2:%.1f angle1:%.1f angle1:%.2f center view:%s' %\
        #       (pos.x(), pos.y(), size.x(), size.y(), rad1, rad2, ang1_deg, ang2_deg, str(center)))

        return pos, size, center, rad1, rad2, ang1_deg, ang2_deg, ang1, ang2, p0, p1, p2, p3


    def shape(self):

        for i,h in enumerate(self.handles): print(' %d %s norm position %s' % (i, h['name'], str(h['pos'])))
        #for i,h in enumerate(self.handles): print(' %d %s item position %s' % (i, h['name'], str(h['item'].pos())))

        self._fix_free_handle_norm_position()

        pos, size, center, rad1, rad2, ang1_deg, ang2_deg, ang1, ang2, p0, p1, p2, p3 = self.shape_parameters()

        br1 = self.boundingRect()
        width1 = br1.width()
        width2 = 2*rad2
        br2 = QRectF(0, 0, width2, width2)
        br2.moveCenter(br1.center()) #pg.QtCore.QPointF(100,100)
        #logger.info('ArcROI.shape br2.center(): %s br2.size(): %s' % (str(br2.center()), str(br2.size())))

        p = pg.QtGui.QPainterPath()
        p = path_add_ellipse(p, br1, a2=ang2)
        p.moveTo(p1)
        p.lineTo(p0)
        path_add_cross(p, br1, w=0.05*width1)
        p.moveTo(p2)
        p.lineTo(p3)
        p = path_add_ellipse(p, br2, a2=ang2)


        #logger.info
        #print('center: %s h1: %s h2: %s' % (str(h0['item'].pos()), str(h1['item'].pos()), str(h2['item'].pos())))
        #print('ArcROI.boundingRect() center: %s size: %s' % (str(br1.center()), str(br1.size())))
        #print('ArcROI.boundingRect() x: %.1f y: %.1f size: %s' % (br1.x(), br1.y(), str(br1.size())))
        #print('center: %s r1: %.1f r2: %.1f a1: %.1f a2: %.1f' % (str(br1.center()), rad1, rad2, self.angle(), math.degrees(ang2)))
        #print('dir(self): %s' % str(dir(self)))
        #o = self.mapToScene(br1.center())
        #print('self.mapToScene: %s' % str(o))
        #extent, _, origin = self.getAffineSliceParams(self.widget.imageItem.image, self.widget.imageItem)

        return p


    def paint(self, p, opt, widget):
        p.setRenderHints(p.RenderHint.Antialiasing, True)
        #pen = QPen(QBrush(QColor('white')), 1)
        p.setPen(self.currentPen)
        p.drawPath(self.shape())

# EOF
