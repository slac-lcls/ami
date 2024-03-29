#!/bin/bash

BUILDDIR=${1:-$PWD}

pip install --prefix=${TESTRELDIR} asyncqt setproctitle pyfftw sympy pint pytest-asyncio pytest-qt p4p==3.5.5
pip install --prefix=${TESTRELDIR} pyflakes autopep8 docutils pycodestyle pathspec qtawesome
if [ -n "${MYPYRELDIR}" ]; then
    pip install --prefix=${MYPYRELDIR} mypy
fi
cd "${BUILDDIR}/networkfox"
pip install --no-deps --prefix=${TESTRELDIR} .
cd "${BUILDDIR}/amityping"
pip install --no-deps --prefix=${TESTRELDIR} .
cd "${BUILDDIR}/pyqode.qt"
pip install --no-deps --prefix=${TESTRELDIR} .
cd "${BUILDDIR}/pyqode.python"
pip install --no-deps --prefix=${TESTRELDIR} .
cd "${BUILDDIR}/pyqode.core"
pip install --no-deps --prefix=${TESTRELDIR} .
