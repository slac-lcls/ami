# Worker 


The purpose of the worker is to apply the current computation graph to a set of event data newly acquired from a data source.
The results are passed to a Local Reducer.

The computation graph is a python program.
Clients add operations to the graph by submitting requests to the GraphManager.
This can include user-supplied python code.

A worker accesses the graph definition from the Control store and updates its local copy when the graph changes.
When the data source has new data the worker executes the computation graph using the new data as input with results written to the Result store.

If a worker finds that a computation graph has execution failures it marks the current computation graph as invalid in the control store.
Then it reverts to using the last-known-valid computation graph.

The scalability of the system is not limited by the latency through the worker.
This is because we can increase the number of workers and cluster nodes arbitrarily to support any input data rate.


