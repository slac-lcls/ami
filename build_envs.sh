#!/bin/bash

PSANADIR=""
DEPSDIR=""

usage() { echo "Usage: $0 [-d <lcls1 deps dir>] [-p <lcls2 psana dir>]" 1>&2; exit 1; }

# parse cli args
while getopts ":d:p:" o; do
    case "${o}" in
        d)
            DEPSDIR=${OPTARG}
            ;;
        p)
            PSANADIR=${OPTARG}
            ;;
        *)
            usage
            ;;
    esac
done
shift $((OPTIND-1))

# check if specified lcls2 psana directory exists and if so resolve paths to absolute paths
if [ -n "${PSANADIR}" ]; then
    if [ -d "${PSANADIR}" ]; then
        PSANADIR="$(cd "$(readlink -f "${PSANADIR}")"; pwd -P)"
    else
        echo "The specified psana install directory does not exist: ${PSANADIR}"
        exit 1
    fi
fi
# check if specified lcls1 deps directory exists and if so resolve paths to absolute paths
if [ -n "${DEPSDIR}" ]; then
    if [ -d "${DEPSDIR}" ]; then
        DEPSDIR="$(cd "$(readlink -f "${DEPSDIR}")"; pwd -P)"
    else
        echo "The specified dependencies directory does not exist: ${DEPSDIR}"
        exit 1
    fi
fi

# find directory of the script
export RELDIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"; pwd -P)"

# change to that directory
cd -P -- "${RELDIR}"

# build the lcls1 version of the environment
"${RELDIR}/build_lcls1_env.sh" "${DEPSDIR}"

# build the lcls2 version of the environment
"${RELDIR}/build_lcls2_env.sh" "${PSANADIR}"
