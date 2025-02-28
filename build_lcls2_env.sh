#!/bin/bash

BUILDDIR=${1:-$PWD}

# if no env is setup activate the script
if [ -z "${TESTRELDIR}" ]; then
    # if the caller sets builddir use setup_env.sh from there
    if [ -n "${BUILDDIR}" ]; then
        source "${BUILDDIR}/setup_env.sh"
    elif [ -n "${RELDIR}" ]; then
        source "${RELDIR}/setup_env.sh"
    else
        source "${PWD}/setup_env.sh"
    fi
fi

# run the build script
if [ -n "${RELDIR}" ]; then
    "${RELDIR}/build_all.sh"
else
    "${PWD}/build_all.sh"
fi
