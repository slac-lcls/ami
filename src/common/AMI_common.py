#
# AMI_common.py
#

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




