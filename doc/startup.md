# Startup

## Software location

Requirements:
We will not require a global filesystem for software distribution, although global filesystem will be an option
We will require software installations be local on the node, either through a docker image (preferred) or a local installation

## Launching executables

Options:
DAQ procmgr daemon
mpirun

Requirements:
need to be able to restart individual executables if they crash
parallel launching of executables on remote machines

Issue: need to understand how the above startup mechanisms interact with docker

Preferred option: procmgr because it more naturally starts up heterogeneous executables, and can restart individual executables

## Connection discovery mechanism

Requirements:
Should be a minimum number of "well-known ports" (or well-known-redis)

Options:
command-line parameters
DAQ collection manager
redis

if we use mpirun, could use mpi to communicate IP addresses/ports, but feels ugly

Preferred option:  DAQ collection manager or redis?
