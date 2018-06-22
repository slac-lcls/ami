# Graph Manager

The GraphManager maintains the current computation graph and makes it available to workers through the Control store.

The Graph Manager listens for graph modification requests from clients.
It approves or denies each request so the client can raise an error if appropriate.
After modifying the graph the GraphManager optimizes it before writing to the Control store.

The GraphManager ensures that clients are subscribed to the right channels in order to receive the information they have requested from the Result stored.

TODO: explain how a subscription is removed if the client exits.

In a small system their is one instance of the GraphManager.
In a larger system with many clients the GraphManager is replicated (not distributed).
Both configurations allow concurrent modification of the graph by different clients.

