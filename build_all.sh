#!/bin/bash

set -e

# choose local directory where packages will be installed
if [ -z "$TESTRELDIR" ]; then
  export INSTDIR=`pwd`/install
else
  export INSTDIR="$TESTRELDIR"
fi

pyInstallStyle="develop"

echo "Python install option:" $pyInstallStyle

pyver=$(python -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))")
# "python setup.py develop" seems to not create this for you
# (although "install" does)
mkdir -p $INSTDIR/lib/python$pyver/site-packages/
if [ $pyInstallStyle == "develop" ]; then
    pipOptions="--editable"
else
    pipOptions=""
fi

# to build ami with setuptools
pip install --no-deps --prefix=$INSTDIR $pipOptions .

# The removeal of site.py in setup 49.0.0 breaks "develop" installations
# which are outside the normal system directories: /usr, /usr/local,
# $HOME/.local. etc. See: https://github.com/pypa/setuptools/issues/2295
# The suggested fix, in the bug report, is the following: "I recommend
# that the project use pip install --prefix or possibly pip install
# --target to install packages and supply a sitecustomize.py to ensure
# that directory ends up as a site dir and gets .pth processing. That
# approach should be future-proof (at least against the sunset of
# easy_install). All python setup.py commands in the code above have
# been replaced with pip commands. The following code implements the
# sitecustomize.py file. Pip bilds the python modules in a sandbox,
# so it requires all the code for the module to be in the same
# folder. The C++ code for the modules built in psana was therefore
# moved from psalg to psana.
if [ $pyInstallStyle == "develop" ]; then
  if [ ! -f $INSTDIR/lib/python$pyver/site-packages/site.py ] && \
     [ ! -f $INSTDIR/lib/python$pyver/site-packages/sitecustomize.py ]; then
cat << EOF > $INSTDIR/lib/python$pyver/site-packages/sitecustomize.py
import site

site.addsitedir('$INSTDIR/lib/python$pyver/site-packages')
EOF
  fi
fi
