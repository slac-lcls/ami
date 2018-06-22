
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
These components can invalidate a graph when it is discovered to be bad,
and return to using the previously known good graph.


## Pseudocode

Following is pseudocode that outlines the structure of a simple client and server (worker).
This pseudocode has been executed using a file as a replacement for the Control store.


### Server pseudocode

This is a simple server example.
It accepts a computation graph once and executes it repeatedly.
This corresponds to a Worker.


```
import AMI_server as AMI

graph = AMI.workerGraph()
for element in graph.elements:
  element.initializeComputation()


nextSampleTime = 0
samplingInterval = 100

if True:
  eventData = AMI.ingestEvent()
  result = {}
  for element in graph.elements:
    result.update(element.executeComputation(eventData))
  timestamp = eventData['timestamp']
  if timestamp >= nextSampleTime:
    AMI.submitResultToCollector(result)
    nextSampleTime = timestamp + samplingInterval

```

### Client pseudocode

This pseudocode includes graph creation which would normally be done by the graph manager.
This client corresponds to an Env display from AMI-1 with a single data field.

```
import AMI_client as AMI

def workerGraph():
  graph = AMI.Graph('workerGraph_Env_one_scalar')
  dataPoint = AMI.Point('field0')
  dataPoint.setMean()
  graph.add(dataPoint)
  graph.add(AMI.Point('normalizeField'))
  graph.add(AMI.Point('weightField'))
  graph.add(AMI.Point('timestamp'))
  return graph

def normalizedWeighted(x, normalize, weight):
  return x / normalize * weight


graph = workerGraph()
AMI.submitGraphToManager(graph)

while(True):
  data = AMI.displayResult() # returns data from pub/sub results
  x = data['timestamp']
  y = normalizedWeighted(data['field0.mean.0'], data['normalizeField'], data['weightField'])
  print x, y

```


### Base class

Here is a common class that underlies the client and server code.

```
import numpy
import pickle
import math


###
### graphs
###


class Graph(object):
  
  def __init__(self, name):
    self.name = name
    self.elements = []
  
  def serialize(self):
    filename = "controlStore_" + self.__class__.__name__ + ".dat"
    print(filename)
    pickle.dump(self, open(filename, "wb"))
  
  def deserialize(self):
    filename = "controlStore_" + self.__class__.__name__ + ".dat"
    print(filename)
    return pickle.load(open(filename, "rb"))
  
  def add(self, element):
    self.elements.append(element)
  
  def broadcast(self):
    self.serialize()


###
### graph elements
###

class GraphElement(object):
  
  def __init__(self, *args, **kwargs):
    self.name = args[0]
    self.dimensions = []
    #
    self.ROI = []
    self.filter = None
    self.mean = False
    self.sum = False
    self.standardDeviation = False
    self.channel = None
    #
    if kwargs is not None:
      for key, value in kwargs.iteritems():
        eval('self.' + key + ' = ' + value)
    self.data = self.allocateData()

  def allocateData(self):
    return numpy.zeros(self.shape())
  
  def getData(self):
    pass#TODO
  
  def defaultROI(self):
    return [0]
  
  def shape(self):
    return (1)

  def setROI(self, roi):
    self.ROI.append(roi)

  def setFilter(self, filter):
    self.filter = filter

  def setMean(self):
    self.mean = True

  def setSum(self):
    self.sum = True

  def setStandardDeviation(self):
    self.standardDeviation = True
    self.sumSquaredDifferences = self.allocateData()
# standard deviation is sqrt( sumSquaredDifferences / (count-1) )

  def setChannel(self, channel):
    self.channel = channel

  def initializeComputation(self):
    self.allocateData()
  
  def resultName(self, prefix, roiIndex):
    return self.name + '.' + prefix + '.' + str(roiIndex)
  
  def sumInROI(self, roi, data):
    sum = self.allocateData()
    if len(roi) > 1:
      for i in range(roi[0], roi[2] + 1):
        for j in range(roi[1], roi[3] + 1):
          sum = sum + data[i][j]
      return sum
    else:
      return data

  def standardDeviationInROI(self, roi, data, mean, numPoints):
    sumSquaredDifferences = self.allocateData()
    for i in range(roi[0], roi[2]):
      for j in range(roi[1], roi[3]):
        difference = data[i][j] - mean
        sumSquaredDifferences = sumSquaredDifferences + difference * difference
    return math.sqrt(sumSquaredDifferences / (numPoints - 1))


# TODO execute user specified worker computation here? do we need it?
  def computation(self, data, roi, roiIndex):
    result = {}
    if self.sum or self.mean or self.standardDeviation:
      sum = self.sumInROI(roi, data)
      if self.sum:
        result[self.resultName('sum', roiIndex)] = sum
      numPoints = 1
      if len(roi) > 1:
        numPoints = ((roi[2] - roi[0] + 1) * (roi[3] - roi[1] + 1))
        mean = sum / numPoints
      else:
        mean = sum
      if self.mean:
        result[self.resultName('mean', roiIndex)] = mean
      if self.standardDeviation:
        result[self.resultName('standardDeviation', roiIndex)] = self.standardDeviationInROI(roi, data, mean, numPoints)
    else:
      result = { self.name : data }
    return result


  def executeComputation(self, telemetryFrame):
    data = telemetryFrame[self.name]
    if self.filter is not None:
      if self.filter(data) is False:
        return {}
    result = {}
    index = 0
    for roi in self.ROI:
      result.update(self.computation(data, roi, index))
      index = index + 1
    if len(self.ROI) > 0:
      return result
    return self.computation(data, self.defaultROI(), 0)

    

  def finalizeComputation(self):
    pass




class Tensor(GraphElement):
  
  def __init__(self, *args, **kwargs):
    super(Tensor, self).__init__(args[0], kwargs)

class Tensor0D(Tensor):
  
  def __init__(self, *args, **kwargs):
    super(Tensor0D, self).__init__(args[0], kwargs)

class Point(Tensor0D):
  
  def __init__(self, *args, **kwargs):
    super(Point, self).__init__(args[0], kwargs)

class Tensor1D(Tensor):
  
  def __init__(self, *args, **kwargs):
    super(Tensor1D, self).__init__(args[0], kwargs)

  def shape(self):
    return (self.dimensions[0])

class Vector(Tensor1D):
  
  def __init__(self, *args, **kwargs):
    super(Vector, self).__init__(args[0], kwargs)

class Tensor2D(Tensor):
  
  def __init__(self, *args, **kwargs):
    super(Tensor2D, self).__init__(args[0], kwargs)
  
  def shape(self):
    return (self.dimensions[0], self.dimensions[1])

class VectorField1D(Tensor1D):
  
  def __init__(self, *args, **kwargs):
    super(VectorField1D, self).__init__(args[0], kwargs)
    self.dataTypeIs(VectorDataPoint())

class VectorField2D(Tensor2D):
  
  def __init__(self, *args, **kwargs):
    super(VectorField2D, self).__init__(args[0], kwargs)
    self.dataTypeIs(VectorDataPoint())


###
### sensors
###

class Sensor(object):

  def __init__(self, *args, **kwargs):
    pass


class Image(Tensor2D):
  
  def __init__(self, *args, **kwargs):
    super(Image, self).__init__(args[0], kwargs)

class CSPAD(Image, Sensor):
  
  def __init__(self, *args, **kwargs):
    Image.__init__(self, args[0], kwargs)
    Sensor.__init__(self, args[0], kwargs)
```

