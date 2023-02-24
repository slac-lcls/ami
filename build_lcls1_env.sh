#!/bin/bash
pip install --prefix=${TESTRELDIR} asyncqt mypy setproctitle pyfftw sympy pint pytest-asyncio pytest-qt p4p==3.5.5
pip install --prefix=${TESTRELDIR} pyflakes autopep8 docutils pycodestyle pathspec qtawesome
cd /cds/home/d/ddamiani/Workarea/lcls2-dev/networkfox
pip install --no-deps --prefix=${TESTRELDIR} .
cd /cds/home/d/ddamiani/Workarea/lcls2-dev/amityping
pip install --no-deps --prefix=${TESTRELDIR} .
cd /cds/home/d/ddamiani/Workarea/lcls2-dev/pyqode.qt
pip install --no-deps --prefix=${TESTRELDIR} .
cd /cds/home/d/ddamiani/Workarea/lcls2-dev/pyqode.python
pip install --no-deps --prefix=${TESTRELDIR} .
cd /cds/home/d/ddamiani/Workarea/lcls2-dev/pyqode.core
pip install --no-deps --prefix=${TESTRELDIR} .
