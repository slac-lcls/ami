#!/bin/bash

BUILDDIR=${1:-$PWD}

# if no env is setup activate the script
if [ -z "${TESTRELDIR}" ]; then
    # if the caller of this export RELDIR use that
    if [ -z "${RELDIR}" ]; then
        source "${PWD}/setup_env_lcls1.sh"
    else
        source "${RELDIR}/setup_env_lcls1.sh"
    fi
fi

#PYPI_DEPS_NOT_ENV="asyncqt setproctitle pyfftw sympy pint pytest-asyncio pytest-qt p4p==3.5.5 pyflakes autopep8 docutils pycodestyle pathspec qtawesome"
PYPI_DEPS_NOT_ENV="p4p"
if [ -n "${PYPI_DEPS_NOT_ENV}" ]; then
    pip install --prefix=${TESTRELDIR} ${PYPI_DEPS_NOT_ENV}
fi

# install mypy if it is needed
if [ -n "${MYPYRELDIR}" ]; then
    pip install --prefix=${MYPYRELDIR} mypy
fi

#DEPS_NOT_ENV="networkfox amityping pyqode.qt pyqode.python pyqode.core"
LOCAL_DEPS_NOT_ENV=""
for DEP in ${LOCAL_DEPS_NOT_ENV}
do
    cd "${BUILDDIR}/${DEP}"
    pip install --no-deps --prefix=${TESTRELDIR} .
done

# run the build script
if [ -z "${RELDIR}" ]; then
    "${PWD}/build_all.sh"
else
    "${RELDIR}/build_all.sh"
fi

# create a symlink so lcls procmgr can find the conda env
ln -sfn "${CONDA_PREFIX}" "${TESTRELDIR}/condadir"
