#!/bin/bash

BUILDDIR="${1}"

# find directory of the script
export RELDIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"; pwd -P)"

# change to that directory
cd -P -- "${RELDIR}"

# build the lcls1 version of the environment
"${RELDIR}/build_lcls1_env.sh" "${BUILDDIR}"

# build the lcls2 version of the environment
"${RELDIR}/build_lcls2_env.sh" "${BUILDDIR}"
