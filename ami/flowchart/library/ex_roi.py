
"""Test available types of ROI
"""

import sys
import os
import numpy as np
import pyqtgraph as pg
import ami.flowchart.library.UtilsROI as ur
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QApplication
os.environ['LIBGL_ALWAYS_INDIRECT'] = '1'


class Window(QWidget):
    def __init__(self, roi):
        super().__init__()
        self.setWindowTitle('pyqtgraph')
        self.setGeometry(100, 100, 1000, 800)
        imv = pg.ImageView()
        imv.setImage(np.random.normal(size=(200, 200)))
        imv.addItem(roi)
        layout = QHBoxLayout()
        layout.addWidget(imv)
        self.setLayout(layout)


def test_roi(TNAME):
    a = QApplication(sys.argv)
    roi = ur.ArchROI((50, 50), 100) if TNAME == '1' else\
          pg.TriangleROI((50, 50), 100) if TNAME == '2' else\
          pg.CrosshairROI((50, 50), 20) if TNAME == '3' else\
          pg.EllipseROI((100, 100), 50) if TNAME == '4' else\
          pg.RectROI((50, 50), (50, 70)) if TNAME == '5' else\
          pg.CircleROI((90, 90), 50) if TNAME == '6' else\
          pg.LineROI((20, 10), (100, 90), 3) if TNAME == '7' else\
          pg.PolyLineROI([(10, 20), (30, 10), (10, 50), (80, 90)], closed=True)
    w = Window(roi)
    w.show()
    sys.exit(a.exec())


SCRNAME = sys.argv[0].rsplit('/')[-1]

USAGE = '\nUsage:'\
      + '\n  python %s <test-name>' % SCRNAME\
      + '\n  where test-name: '\
      + '\n    0 - print usage'\
      + '\n    1 - ArcROI'\
      + '\n    2 - TriangleROI'\
      + '\n    3 - CrosshairROI'\
      + '\n    4 - EllipseROI'\
      + '\n    5 - RectROI'\
      + '\n    6 - CircleROI'\
      + '\n    7 - LineROI'\
      + '\n    8 - PolyLineROI'\

TNAME = sys.argv[1] if len(sys.argv) > 1 else '0'

if TNAME in ('1', '2', '3', '4', '5', '6', '7', '8'):
    test_roi(TNAME)
else:
    print(USAGE)
    exit('TEST %s IS NOT IMPLEMENTED' % TNAME)

exit('END OF TEST %s' % TNAME)
