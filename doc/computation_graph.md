
# Computation Graph

The computation graph is implemented by a set of python objects that derive from a common base class.
Data are represented as numpy arrays and arithmetic is performed by numpy.
This base class supports a set of built-in commutative operations, typically within a Region-of-Interest (ROI).
All relevant data (e.g. accumulators) is stored within the object.

## Built-in primitive operations

These apply to any data object.

ROI specification,
sum, (mean), standard deviation

## Built-in complex operations

(1-dimensional data support?)

Contour projection,
Peak Finder,
Blob Finder,
Droplet Finder

## User-supplied code

The user can install packages using Conda.
The user can provide Python source code to be imported into the computation graph and executed by objects.

When the user starts a session they go through steps to define the new packages or code.
The Python Conda environment is located on an NFS mount point that accessible to all cluster nodes.
Use supplied code is copied with directory structure intact to a well-known place.


User-supplied code can cause runtime failures.
Some of these failures cannot be detected by the Graph Manager.
Such errors can only be detected by a Worker or Reducer.

A user can decide whether to invalidate a graph that throws an execution error, or to keep using it.
If the graph is to be invalidated then the Worker complains to the GraphManager, who distributes a previously-known-to-be-good computation graph via the normal mechanism.
If the graph is to continue in use then the system will log the failures and present them to the user.


## Client and server architecture

Following is pseudocode that outlines the structure of a simple client and server (worker).
This pseudocode has been executed using a file as a replacement for the Control store.

A client prepares an AMI.Graph by calling graph.export() on a set of objects from the AMI.GraphElement base class.
Objects can be decorated with ROIs, requests for built-in computations like sum, etc.
Each of these objects will be exported to the Result store.

AMI.submitToGraphManager() pickles the graph as a tuple of objects and sends the pickled result to the GraphManager.
The GraphManager performs basic correctness checks and merges the objects into the overall computation graph.


### Client pseudocode

This client  displays 0-, 1- and 2-dimensional data.

```
import AMI_client as AMI
import useDefined

def workerGraph():
  graph = AMI.Graph('workerGraph_Env_one_scalar') # create an empty graph

  # Env data source, plot mean v time, normalize by, weight by
  dataPoint = AMI.Point('field0') # 'field0' matches an XTC field name
  dataPoint.setMean() # compute the mean of this field
  graph.export(dataPoint) # export to the Result store
  graph.export(AMI.Point('normalizeField')) # export XTC field to the Result store
  graph.export(AMI.Point('weightField')) # export XTC field to the Result store
  graph.export(AMI.Point('timestamp')) # export XTC field to the Result store

  # 1D array with recirculated datum
  sourceVector = AMI.vector('intensityVector') # 'intensityVector' is an XTC field
  userObject = userDefined.object('userObject0', sourceVector) # a custom user object
  graph.export(userObject) # export to the Result store, must support computation and reduction
  meanIntensity = AMI.Result('userObject0').meanIntensity # obtain from the result store
  userObject2 = userDefine.object2('userObject2', sourceVector, dataPoint, meanIntensity)
  graph.export(userObject2) # export to the Result store

  # 2D cspad with ROI computation
  image = AMI.cspad('cspad0') # 'cspad0' is an XTC field, 2D image
  shape = image.shape() # get dimensions
  roi = [ shape[2] * .1, shape[3] * .1, shape[2] * .9, shape[3] * .9 ]
  image.setROI(roi) # set an inset ROI
  image.setMean() # compute the mean in the ROI
  graph.export(image) # export to Result store

  return graph


def normalizedWeighted(x, normalize, weight):
  return x / normalize * weight


graph = workerGraph()
AMI.submitGraphToManager(graph) # pickle the graph and send to GraphManager

while(True):
  data = AMI.displayResult() # get the current frame of subscribed data
  x = data['timestamp']
  y = normalizedWeighted(data['field0'].mean.0, data['normalizeField'], data['weightField'])
  print x, y
  userObject = data['userObject0']
  userObject2 = data['userObject2']
  print userObject.fieldA, userObject2.fieldB
  image = data['cspad0']
  print image.mean.0

```


