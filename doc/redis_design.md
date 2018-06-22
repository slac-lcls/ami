# Redis design

<img src="images/AMI2_system_diagram/AMI2_system_diagram.003.jpeg" width=800>

In the Redis design all of the components are separate processes.
The stores are implemented by the distributed resilient in-memory database Redis.
A local Redis runs privately on each node to support event processing.
A global distributed Redis runs across the cluster to provide data to manage Control and Results.

Event data is provided from a data source to the local Redis.
Workers subscribe to channels from the local Redis.
When a worker gets event data it checks the Control Redis to see if there is a new computation graph.
If there is a new graph the worker retrieves it.
Then the worker runs the computation graph on the event data.
The worker passes the results to a Local Reducer.

