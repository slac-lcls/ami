import psana

if hasattr(psana, '_psana'):
    import logging
    import numpy as np

    logger = logging.getLogger(__name__)
    DTYPE_MASK = np.uint8
    DTYPE_STATUS = np.uint64

    def merge_masks(mask1=None, mask2=None, dtype=DTYPE_MASK):
        """Merging masks using np.logical_and rule: (0,1,0,1)^(0,0,1,1) = (0,0,0,1)
        """
        assert mask1.size == mask2.size, 'Mask sizes should be equal'

        if mask1 is None:
            return mask2
        if mask2 is None:
            return mask1

        if mask1.shape != mask2.shape:
            if mask1.ndim > mask2.ndim:
                mask2.shape = mask1.shape
            else:
                mask1.shape = mask2.shape

        cond = np.logical_and(mask1, mask2)
        return np.asarray(np.select((cond,), (1,), default=0), dtype=dtype)

    def cart2r(x, y):
        return np.sqrt(x*x + y*y)

    def meshgrids(shape):
        """returns np.meshgrid arrays of cols, rows for specified shape"""
        assert len(shape) == 2
        return np.meshgrid(np.arange(shape[1]), np.arange(shape[0]))

    def mask_ring(shape, center_row, center_col, radius_min, radius_max, dtype=DTYPE_MASK):
        c, r = meshgrids(shape)
        rad = cart2r(r-center_row, c-center_col)
        return np.select([rad < radius_min, rad > radius_max,], [0, 0,], default=1).astype(dtype)

    def mask_halfplane(shape, r1, c1, r2, c2, rm, cm, dtype=DTYPE_MASK):
        """Half-plane contains the boarder line through the points (r1, c1) and (r2, c2)
           Off-line point (rm, cm) picks the half-plane marked with ones.
        """
        f = 0 if c1 == c2 else (r2-r1)/(c2-c1)
        c, r = meshgrids(shape)
        signgt = rm > r1+f*(cm-c1)
        cond = (r > r1 if rm < r1 else r < r1) if r1 == r2 else\
               (c > c1 if cm < c1 else c < c1) if c1 == c2 else\
               ((r > r1+f*(c-c1)) if signgt else (r < r1+f*(c-c1)))
        # rm, cm = int(rm), int(cm)
        # if not cond[rm, cm]: cond = ~cond
        return np.select([cond,], [0,], default=1).astype(dtype)

    def mask_arc(shape, cx, cy, ro, ri, ao, ai, dtype=DTYPE_MASK):
        """Returns arc mask for ami2 ArcROI set of parameters. Ones in the arc zeroes outside.
           Carthesian (x,y) emulated by returned *.T as in ami.
           cx, cy - arc center (col, row)
           ro, ri - radii of the outer and inner arc corner points
           ao, ai - angles of the outer and arc angular size from outer to inner corner points
        """
        logger.debug('shape:%s  cx:%.2f  cy:%.2f  ro:%.2f  ri:%.2f  ao:%.2f  ai:%.2f' %
                     (str(shape), cx, cy, ro, ri, ao, ai))
        from math import radians, sin, cos  # floor, ceil
        assert ro > ri, 'outer radius %d shold be greater than inner %d' % (ro, ri)
        assert ai > 0, 'arc span angle %.2f deg > 0' % ai
        # assert ao > 0, 'outer arc corner angle %.2f deg > 0' % ao
        row1, col1 = cy, cx
        mring = mask_ring(shape, row1, col1, ri, ro, dtype=dtype)
        ao_rad = radians(ao)
        ai_rad = radians(ao + ai)
        delta = -0.1  # radian
        row2, col2 = row1 + ro * sin(ao_rad), col1 + ro * cos(ao_rad)
        rm, cm = row1 + ro * sin(ao_rad+delta), col1 + ro * cos(ao_rad+delta)
        mhpo = mask_halfplane(shape, row1, col1, row2, col2, rm, cm, dtype=dtype)
        row2, col2 = row1 + ri * sin(ai_rad), col1 + ri * cos(ai_rad)
        rm, cm = row1 + ri * sin(ai_rad-delta), col1 + ri * cos(ai_rad-delta)
        mhpi = mask_halfplane(shape, row1, col1, row2, col2, rm, cm, dtype=dtype)
        mhro = merge_masks(mask1=mring, mask2=mhpo, dtype=dtype)
        mhri = merge_masks(mask1=mring, mask2=mhpi, dtype=dtype)
        return (np.bitwise_and(mhro, mhri) if ai < 180 else np.bitwise_or(mhro, mhri)).T
else:
    from psana.detector.UtilsMask import * # noqa ignore=F405
