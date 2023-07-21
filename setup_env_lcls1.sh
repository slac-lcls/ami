unset LD_LIBRARY_PATH
unset PYTHONPATH

CONDA_ENV_NAME=ana-4.0.49-py3

if [[ ${HOSTNAME} == sdf* ]]
then
    # for s3df
    # sdf conda envs seem to mangle the ps1 badly
    PS1_BACKUP="${PS1}"
    source /sdf/group/lcls/ds/ana/sw/conda2/inst/etc/profile.d/conda.sh
    export CONDA_ENVS_DIRS=/sdf/group/lcls/ds/ana/sw/conda1/inst/envs
    export SIT_ROOT=/sdf/group/lcls/ds/ana/
    export SIT_PSDM_DATA=/sdf/data/lcls/ds/
    export SIT_ARCH=x86_64-rhel8-gcc85-opt
    export SIT_DATA="${CONDA_ENVS_DIRS}/${CONDA_ENV_NAME}/data:${SIT_ROOT}/data/"
else
    # for psana
    source /cds/sw/ds/ana/conda1-v2/inst/etc/profile.d/conda.sh
    export CONDA_ENVS_DIRS=/cds/sw/ds/ana/conda1/inst/envs/
    export SIT_ROOT=/cds/group/psdm
    export SIT_PSDM_DATA=/cds/data/psdm
    export SIT_ARCH=x86_64-rhel7-gcc48-opt
    export SIT_DATA="${CONDA_ENVS_DIRS}/${CONDA_ENV_NAME}/data:${SIT_ROOT}/data/"
fi

conda activate "${CONDA_ENV_NAME}"
if [ -n "${PS1_BACKUP}" ]; then
    PS1="(${CONDA_ENV_NAME}) ${PS1_BACKUP}"
    unset PS1_BACKUP
fi
unset CONDA_ENV_NAME

RELDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export PATH=$RELDIR/install-lcls1/bin:${PATH}
pyver=$(python -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))")
export PYTHONPATH=$RELDIR/install-lcls1/lib/python$pyver/site-packages
# for procmgr
export TESTRELDIR=$RELDIR/install-lcls1
# needed so mypy finds type stubs in local dir
export MYPYPATH=$PYTHONPATH

# needed for SRCF
export OPENBLAS_NUM_THREADS=1
export HDF5_USE_FILE_LOCKING=FALSE
