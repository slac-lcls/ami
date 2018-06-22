# Local Reducer, Gloal Reducer 


The purpose of the reducers is to apply the computation graph to intermediate data from workers or other reducers.
The results are written to the Result store.

An example would be computing the sum of an image detector (e.g. CSPAD) during a time interval.
Each worker computes a local sum according to the events that it sees within an interval.
Within each node a Local Reducer obtains these local sums and combines them into a locally reduced sum for one cluster node.
A Global Reducer combines these localls reduced sums to produce a global result.
The client divides this sum by the number of terms in order to disply an average intensity.

Note that a reduction might be different from the worker computation is was based on.
For example, peak finding in the worker consists of examining all of the pixels in an image.
The corresponding reduction only requires comparing the magnitude of the peak inorder to select which of n peak to retain (a "max" operation).
