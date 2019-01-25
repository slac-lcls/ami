Manager
=======

The GraphManager maintains the current computation graph and makes it
available to workers through the Control store.

The Graph Manager listens for graph modification requests from clients.
It approves or denies each request so the client can raise an error if
appropriate. After modifying the graph the GraphManager optimizes it
before writing to the Control store.

The GraphManager ensures that clients are subscribed to the right
channels in order to receive the information they have requested from
the Result stored.

In a small system their is one instance of the GraphManager. In a larger
system with many clients the GraphManager is replicated (not
distributed). Both configurations allow concurrent modification of the
graph by different clients.

If the GraphManager is notified of a failure in the current computation
graph then the GraphManager is responsible for distributing a version of
the computation graph to replace the bad version.

Modification requests
---------------------

A graph modification request can: remove all graph elements that belong
exclusively to the requesting client; or add a new set of graph
elements.

Add graph elements
~~~~~~~~~~~~~~~~~~

The GraphManager derives a DAG from the requested graph elements. It
checks that each object supports the following functions:
initializeComputation; computation; terminateComputation; reduction. If
user code is involved it makes sure that user code can be imported from
a well known location. It runs pyLint on all of the objects. It combines
the graph elements into the computation graph and maintains a resulting
DAG which it writes to the ControlStore. The GraphManager eliminates
duplicate graph elements and performs any sanity checks that are
possible at this time.

Remove graph elements
~~~~~~~~~~~~~~~~~~~~~

The graph manager either removes all graph elements that were originated
exclusively by the requesting client, or removes a set of graph elements
that are provided in a list.
