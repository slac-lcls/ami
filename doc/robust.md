# Robustness

The system is robust to failures in components or cluster nodes, and recovers automatically from a crash.

All component behavior is based on state.
Components write volatile state to the control store whenever it changes.
This must be done atomically before acting on the state change.

Assume the stores are resilient and always available.
When a component starts up it checks the control store to see if it previously crashed.
If previous state exists it reloads its state from the store.

A cron job makes sure the store is always available.
It restarts the store if the store is not running.
It also restarts a minimum set of processes required to bootstrap the system if they are not running.

## Robustness Monitor

A Robustness Monitor runs on every cluster node.
The Monitor ensures that every component running on that node gets restarted if it fails.
On worker nodes this means data sources, workers, and local reducers.
On client nodes this means client processes.
And other nodes support the graph manager.

Robustness Monitors also monitor each other.
They can restart each other across nodes using ssh.
This cross-checking ensures that the components will not go down except in the case of a catastrophic system failure.
