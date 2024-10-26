#!/bin/bash

# if no env is setup activate the script
if [ -z "${TESTRELDIR}" ]; then
    # if the caller of this export RELDIR use that
    if [ -z "${RELDIR}" ]; then
        source "${PWD}/setup_env.sh"
    else
        source "${RELDIR}/setup_env.sh"
    fi
fi

# run the build script
if [ -z "${RELDIR}" ]; then
    "${PWD}/build_all.sh"
else
    "${RELDIR}/build_all.sh"
fi
