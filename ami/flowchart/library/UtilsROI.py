
"""
Usage::
    import ami.flowchart.library.UtilsROI as ur
"""
import math
import numpy as np
import pyqtgraph as pg
import logging
logger = logging.getLogger(__name__)

QPointF, QRectF = pg.QtCore.QPointF, pg.QtCore.QRectF
QPen, QBrush, QColor = pg.QtGui.QPen, pg.QtGui.QBrush, pg.QtGui.QColor

# def rotate_sincos(x, y, s, c): return x*c-y*s, x*s+y*c
# def rotate(x, y, a): return rotate_sincos(x, y, math.sin(a), math.cos(a))
# def rotate_degree(x, y, a): return rotate(x, y, math.radians(a))

# scene.setClickRadius(r)

try:
    import psana.pyalgos.generic.HPolar as hp

    def polar_histogram(shape, mask, cx, cy, ro, ri, ao, ai, nr, na):
        """Returns hp.HPolar object.
        """
        rows, cols = shape
        xarr1 = np.arange(cols) - cx
        yarr1 = np.arange(rows) - cy
        xarr, yarr = np.meshgrid(xarr1, yarr1)
        hpolar = hp.HPolar(xarr, yarr, mask=mask, radedges=(ri, ro),
                           nradbins=nr, phiedges=(ao, ai), nphibins=na)
        # logger.info('%s %s\n%s' %(hp.info_ndarr(xarr,
        #              'pixel coordinate arrays: xarr'),
        #              hp.info_ndarr(yarr,' yarr'),
        #              hpolar.info_attrs()))
        return hpolar

except ImportError as e:
    print(e)


try:
    import psana.detector.UtilsMask as um
    # mask_arc = um.mask_arc(shape, cx, cy, ro, ri, ao, ai, dtype=np.uint8)
    mask_arc = um.mask_arc

except ImportError as e:
    print(e)


def str_point(p, fmt='(%.1f, %.1f)'):
    return fmt % (p.x(), p.y())


def distance(p):
    x, y = p.x(), p.y()
    return math.sqrt(x*x+y*y)


def angle(p):
    """returns the point angle in radians [-pi,pi] -> [0,2*pi] - clockwise"""
    x, y = p.x(), p.y()
    a = math.atan2(y, x)
    return a if a >= 0 and a <= np.pi+1e-6 else 2*np.pi+a


def angle_deg_in_range(a, ang_range=(0, 360)):
    """returns angle in range contracting periodicity"""
    return (a-ang_range[0]) % 360


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


def handle_positions_normalized(radius_out, radius_int,
                                angle_deg_out, angle_deg_int):
    """handle position in the unit bounding rect of size [1,1]
       center is assumed in (0.5, 0.5), outer radius control handle
       is always in (1.0, 0.5) angle_deg_out rotates the whole bounding rect
       relative its center, so position of the rect defined in the corner
       is changing at this rotation, but all normalised position of handles
       are preserved. radius_int and angle_deg_int changes pos2 only.
    """
    # fr = float(radius_int if radius_int<radius_out else
    #            (radius_out-1))/radius_out
    fr = radius_int/radius_out

    a = math.radians(angle_deg_int)
    pos0 = [0.5, 0.5]  # center position handle
    pos1 = [1.0, 0.5]  # outer circle angle and radius control handle
    pos2 = [0.5*(1+fr*math.cos(a)), 0.5*(1+fr*math.sin(a))]  # internal radius
    return pos0, pos1, pos2


class ArchROI(pg.ROI):
    def __init__(self, center=(100, 100), radius_out=100, radius_int=50,
                 angle_deg_out=0, angle_deg_int=60, hlwidth=None, handleSize=5,
                 **kwargs):
        cx, cy = center
        ro, ri, ao, ai = radius_out, radius_int, angle_deg_out, angle_deg_int
        ro = radius_out
        pos = (cx-ro, cy-ro)
        size = (2*ro, 2*ro)
        pg.ROI.__init__(self, pos, size, aspectLocked=True, **kwargs)
        self.handleSize = handleSize
        self._addHandles(radius_out, radius_int, angle_deg_out,
                         angle_deg_int, width=hlwidth)
        self.sigRegionChanged.connect(self._clearPath)
        self.set_shape_parameters(cx, cy, ro, ri, ao, ai)

    def _addHandles(self, radius_out=100, radius_int=50,
                    angle_deg_out=0, angle_deg_int=60, width=None):
        pos0, pos1, pos2 = handle_positions_normalized(
            radius_out, radius_int, angle_deg_out, angle_deg_int)
        center = pos0
        h0 = self.addTranslateHandle(pos0,           name='TranslateHandle  ')
        h1 = self.addScaleRotateHandle(pos1, center, name='ScaleRotateHandle')
        h2 = self.addFreeHandle(pos2, center,        name='FreeHandle       ')

        for h in (h0, h1, h2):
            h.setZValue(1000)

        radius = 5
        h0.radius = radius
        h1.radius = radius
        h2.radius = radius
        if width is None:
            return
        h0.pen = h0.currentPen = QPen(QBrush(QColor('blue')),  width)
        h1.pen = h1.currentPen = QPen(QBrush(QColor('green')), width)
        h2.pen = h2.currentPen = QPen(QBrush(QColor('red')),   width)

    def _clearPath(self):
        self.path = None

    def _fix_free_handle_norm_position(self):
        """fix free-handle normalized position using local position"""
        h = self.handles[2]
        br1 = self.boundingRect()
        br1size = br1.size()  # br1.center()
        p = QPointF(h['item'].pos())  # relative to boundingRect origin
        xrel, yrel = p.x()/br1size.width(), p.y()/br1size.height()
        h['pos'] = (xrel, yrel)

    def _fix_free_handle_local_position(self, x, y):
        h2 = self.handles[2]
        h2['item'].setPos(x, y)

    def set_shape_parameters(self, *args):
        """center_x, center_y, radius_out, radius_int,
           angle_deg_out, angle_deg_int = *args
        """
        cx, cy, ro, ri, ao, ai = args
        e = 2*ro

        # set handles' positions in normalized position for
        # center / external / internal circle
        h0, h1, h2 = self.handles  # center / external / internal circle
        p0, p1, p2 = handle_positions_normalized(ro, ri, ao, ai)
        h0['pos'], h1['pos'], h2['pos'] = p0, p1, p2

        self._fix_free_handle_local_position(p2[0]*e, p2[1]*e)

        self.setSize((e, e), finish=False)
        self.setAngle(ao, center=(0.5, 0.5), update=True, finish=False)
        cview = self.mapToView(self.boundingRect().center())  # QPointF
        p = self.pos()  # Point
        if cview is not None:
            self.setPos(p.x() + cx - cview.x(),
                        y=p.y() + cy - cview.y(), finish=True)

    def handle_positions_local(self):
        """Returns 3 handle positios in the ROI bounding rect local coordinates
           for center / external / internal circle
        """
        h0, h1, h2 = self.handles  # center / external / internal circle
        p0, p1, p2 = h0['item'].pos(), h1['item'].pos(), h2['item'].pos()
        logger.debug('handle positions p0:%s p1:%s p2:%s' % (p0, p1, p2))
        return p0, p1, p2

    def shape_parameters(self):
        """retreives shape parameters from current handles' positions
           and roi.pos/size
        """
        p0, p1, p2 = self.handle_positions_local()
        vh1 = p1 - p0  # br1.center() # point defining vector from center to h1
        vh2 = p2 - p0  # br1.center() # point defining vector from center to h2
        rad1 = distance(vh1)
        rad2 = distance(vh2)

        if rad2 > rad1:  # constrain h2 motion in radial direction
            rad2 = rad1 - 1
            p2 = p0 + rad2*unit_vector(vh2)
            self._fix_free_handle_local_position(p2[0], p2[1])

        p3 = p0 + rad1*unit_vector(vh2)
        # self.angle() is not constrained by period, e.g. [0,360]
        ang1_deg = angle_deg_in_range(self.angle())
        ang1 = math.radians(ang1_deg)
        ang2 = angle(vh2)
        ang2_deg = math.degrees(ang2)
        pos = self.pos()
        size = self.size()
        br1 = self.boundingRect()
        center = self.mapToView(br1.center())
        fmt = 'ArchROI.pos: (%.1f, %.1f) size(%.1f, %.1f) rad1:%.1f '\
            + 'rad2:%.1f angle1:%.1f angle1:%.2f center view:%s'
        logger.debug(fmt % (pos.x(), pos.y(), size.x(), size.y(), rad1, rad2,
                     ang1_deg, ang2_deg, str(center)))
        return pos, size, center, rad1, rad2, ang1_deg, ang2_deg,\
            ang1, ang2, p0, p1, p2, p3

    def shape(self):
        """returns QtGui.QPainterPath for shape defined by bounding rect
           and handles' positions.
        """
        for i, h in enumerate(self.handles):
            logger.debug(' %d %s norm position %s' %
                         (i, h['name'], str(h['pos'])))

        self._fix_free_handle_norm_position()

        pos, size, center, rad1, rad2, ang1_deg, ang2_deg,\
            ang1, ang2, p0, p1, p2, p3 = self.shape_parameters()
        br1 = self.boundingRect()
        width1 = br1.width()
        width2 = 2*rad2
        br2 = QRectF(0, 0, width2, width2)
        br2.moveCenter(br1.center())

        p = pg.QtGui.QPainterPath()
        p = path_add_ellipse(p, br1, a2=ang2)
        p.moveTo(p1)
        p.lineTo(p0)
        path_add_cross(p, br1, w=0.05*width1)
        p.moveTo(p2)
        p.lineTo(p3)
        p = path_add_ellipse(p, br2, a2=ang2)
        return p

    def paint(self, p, opt, widget):
        p.setRenderHints(p.RenderHint.Antialiasing, True)
        p.setPen(self.currentPen)
        p.drawPath(self.shape())

# EOF
