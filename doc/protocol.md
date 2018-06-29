# Protocol Handlers

Communication between clients and the system occurs through modular protocol handlers.

## EPICS
<a href="https://epics.anl.gov">Experimental Physics and Industrial Control System</a> (EPICS) is a DOE supported protocol.

Protocol handlers are processes that mediate between Epics and Redis.
For example, clients may subscribe to receive certain output data from the computation graph.
The outut data will first be published by Redis, then received by the protocol handler, which will retransmit the data using Epics.

## TCP/IP

