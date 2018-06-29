# Worker 


The purpose of the worker is to apply the current computation graph to a set of event data newly acquired from a data source.
The results are passed to a Local Reducer.

The computation graph is a python program.
Clients add operations to the graph by submitting requests to the GraphManager.
This can include user-supplied python code.

A worker accesses the graph definition from the Control store and updates its local copy when the graph changes.
When the data source has new data the worker executes the computation graph using the new data as input with results written to the Result store.

There are two policies for handling runtime failures of the computation graph.
In the "intolerant" policy
if a worker finds that a computation graph has execution failures it marks the current computation graph as invalid in the control store.
Then it reverts to using the last-known-valid computation graph.
In the "tolerant" policy if a worker sees a failure in an element of the graph it skips that element and sends a notification to the user.
This policy is necessary for user defined software that may contain bugs.


The scalability of the system is not limited by the latency through the worker.
This is because we can increase the number of workers and cluster nodes arbitrarily to support any input data rate.

## worker reductions

Workers can reduce data from the dac in two ways: through a "pick-N" pattern or through a time interval.
A typical reduction in this case would be a summation or mean.

### Pick-N reduction

Data is divided into equally-sized sets so that for example a client may request exactly 100 instances of data to be summed.
When a client makes a request for pick-N reduction the requested number of samples is divided by the number of workers and this number is sent to the workers.
The workers count data points and contribute them to a current buffer until the expected number of data have arrived.
At this point the work sends the result to the local reducer.
When subsequent data points arrive they will be contributed to a new buffer.

A consequence of this algorithm is that if data is missing from a worker then that worker will take longer to deliver its result because it waits for further data to replace the missing data.
This delay will ripple through the reducers and require them to hold onto incomplete buffers while they wait for completion.

### Time interval reduction

Wall clock time is divided into intervals that correspond to an output display rate, e.g. 20 Hz.
The arriving data includes timestamps.
Workers use those timestamps to partition the data between a current interval and a future interval.
Workers send the reduced current interval data to the local reducer when the time interval has elapsed, as measured from receipt of the first datum for that interval, or when a new datum arrives that is later than the current interval.
