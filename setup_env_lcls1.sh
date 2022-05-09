unset LD_LIBRARY_PATH
unset PYTHONPATH
# Setup standard py3 version of the ana conda env
source /reg/g/psdm/etc/psconda.sh -py3
RELDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export PATH=$RELDIR/install/bin:${PATH}
pyver=$(python -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))")
export PYTHONPATH=$RELDIR/install/lib/python$pyver/site-packages
# for procmgr
export TESTRELDIR=$RELDIR/install
# needed so mypy finds type stubs in local dir
export MYPYPATH=$PYTHONPATH
