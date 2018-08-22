#
# AMI_common.py
#

import numpy
import pickle
import math


###
### graphs
###

def printGraph(graph):
  for node in graph._nodes:
    arguments = node._arguments()
    args = ''
    if '_args' in dir(node): args = node._args
    print node._name, '\t', node, '\t', arguments, args
    for argument in arguments:
      print '\t\t', argument, '\t', eval('node.' + argument)


class Graph(object):
  
  def __init__(self, name):
    self._name = name
    self._nodes = []
  
  def serialize(self):
    filename = "controlStore_" + self.__class__.__name__ + ".dat"
    print('writing to', filename)
    pickle.dump(self, open(filename, "wb"))
  
  def deserialize(self):
    filename = "controlStore_" + self.__class__.__name__ + ".dat"
    print('reading from', filename)
    return pickle.load(open(filename, "rb"))
  
  def export(self, element):
    self._nodes.append(element)
  
  def import_(self, name):
    result = Import(name)
    self._nodes.append(result)
    return result
  
  def broadcast(self):
    self.serialize()

  def iff(self, lambdaExpression, *args, **kwargs):
    self._nodes.append(If(lambdaExpression, *args, **kwargs))

  def endif(self, *args, **kwargs):
    self._nodes.append(Endif(*args, **kwargs))







###
### graph elements
###

class GraphElement(object):
  
  def __init__(self, *args, **kwargs):
    self._name = args[0]
    print 'GraphElement name =', self._name
    self._dimensions = []
    #
    self._ROI = []
    self._filter = None
    self._mean = False
    self._sum = False
    self._standardDeviation = False
    self._channel = None
    #
    if kwargs is not None:
      for key, value in kwargs.iteritems():
        exec('self._' + str(key) + ' = ' + str(value))
    self._data = self._allocateData()
        
  def _arguments(self):
    result = []
    for arg in dir(self):
      if arg[0] != '_': result.append(arg)
    return result

  def _allocateData(self):
    return numpy.zeros(self._shape())
  
  def _getData(self):
    pass#TODO
  
  def _defaultROI(self):
    return [0]
  
  def _shape(self):
    return [1]

  def _setROI(self, roi):
    self._ROI.append(roi)
    return self

  def _setFilter(self, filter):
    self._filter = filter

  def _setMean(self):
    self._mean = True

  def _setSum(self):
    self._sum = True

  def _setStandardDeviation(self):
    self._standardDeviation = True
    self._sumSquaredDifferences = self._allocateData()

  def _setChannel(self, channel):
    self._channel = channel

  def _resultName(self, prefix, roiIndex):
    return self._name + '.' + prefix + '.a' + str(roiIndex)
  
  def _sumInROI(self, roi, data):
    sum = self._allocateData()
    if len(roi) == 2:
      sum = numpy.cumsum(self._data[int(roi[0]) : int(roi[1])])
      return sum
    if len(roi) == 4:
      sum = numpy.cumsum(self._data[int(roi[0]) : int(roi[1]), int(roi[2]) : int(roi[3])])
      return sum
    else:
      return data

  def _standardDeviationInROI(self, roi, data, mean, numPoints):
    sumSquaredDifferences = self._allocateData()
    for i in range(roi[0], roi[2]):
      for j in range(roi[1], roi[3]):
        difference = data[i][j] - mean
        sumSquaredDifferences = sumSquaredDifferences + difference * difference
    return math.sqrt(sumSquaredDifferences / (numPoints - 1))


  def _doMap(self, data, roi, roiIndex):
    result = {}
    if self._sum or self._mean or self._standardDeviation:
      sum = self._sumInROI(roi, data)
      if self._sum:
        result[self._resultName('sum', roiIndex)] = sum
      numPoints = 1
      if len(roi) == 2:
        numPoints = roi[1] - roi[0] + 1
        mean = sum / numPoints
      if len(roi) == 4:
        numPoints = ((roi[2] - roi[0] + 1) * (roi[3] - roi[1] + 1))
        mean = sum / numPoints
      else:
        mean = sum
      if self._mean:
        result[self._resultName('mean', roiIndex)] = mean
      if self._standardDeviation:
        result[self._resultName('standardDeviation', roiIndex)] = self._standardDeviationInROI(roi, data, mean, numPoints)
    else:
      result = { self._name : data }
    return result


  def _map(self, telemetryFrame):
    data = telemetryFrame[self._name]
    if self._filter is not None:
      if self._filter(data) is False:
        return {}
    result = {}
    index = 0
    for roi in self._ROI:
      result.update(self._doMap(data, roi, index))
      index = index + 1
    if len(self._ROI) > 0:
      return result
    return self._doMap(data, self._defaultROI(), 0)

    
  def _initializeMap(self):
    self._data = self._allocateData()

  def _terminateMap(self):
    pass

  def _reduce(self):
    pass # tbd



class Endif(GraphElement):
  
  def __init__(self, *args, **kwargs):
    super(Endif, self).__init__('endif', *args, **kwargs)
    if args is not None: self._args = args
    if kwargs is not None:
      for key, value in kwargs.iteritems():
        exec('self.' + str(key) + ' = ' + str(value))

  def _initializeMap(self):
    pass

  def _map(self, telemetryFrame):
    pass

  def _terminateMap(self):
    pass

  def _reduce(self):
    pass

class If(GraphElement):
  
  def __init__(self, lambdaExpression, *args, **kwargs):
    super(If, self).__init__('iff ' + lambdaExpression, *args, **kwargs)
    self._lambdaExpression = lambdaExpression
    if args is not None: self._args = args
    if kwargs is not None:
      for key, value in kwargs.iteritems():
        exec('self.' + str(key) + ' = ' + str(value))

  def _initializeMap(self):
    print self._lambdaExpression, self._args

  def _map(self, telemetryFrame):
    pass
  
  def _terminateMap(self):
    pass
  
  def _reduce(self):
    pass


class Import(GraphElement):

  def __init__(self, name, *args, **kwargs):
    super(Import, self).__init__('import ' + name, *args, **kwargs)

  def _get(self, name):
    return None

  def _initializeMap(self):
    print self._name
  
  def _map(self, telemetryFrame):
    pass
  
  def _terminateMap(self):
    pass
  
  def _reduce(self):
    pass


class Tensor(GraphElement):
  
  def __init__(self, *args, **kwargs):
    super(Tensor, self).__init__(args[0], **kwargs)

class Tensor0D(Tensor):
  
  def __init__(self, *args, **kwargs):
    super(Tensor0D, self).__init__(args[0], **kwargs)

class Point(Tensor0D):
  
  def __init__(self, *args, **kwargs):
    super(Point, self).__init__(args[0], **kwargs)

class Tensor1D(Tensor):
  
  def __init__(self, *args, **kwargs):
    super(Tensor1D, self).__init__(args[0], **kwargs)

  def _shape(self):
    return self._dimensions[0]

class Vector(Tensor1D):
  
  def __init__(self, *args, **kwargs):
    super(Vector, self).__init__(args[0], **kwargs)

class Tensor2D(Tensor):
  
  def __init__(self, *args, **kwargs):
    super(Tensor2D, self).__init__(args[0], **kwargs)
  
  def _shape(self):
    return self._dimensions

class VectorField1D(Tensor1D):
  
  def __init__(self, *args, **kwargs):
    super(VectorField1D, self).__init__(args[0], **kwargs)

class VectorField2D(Tensor2D):
  
  def __init__(self, *args, **kwargs):
    super(VectorField2D, self).__init__(args[0], **kwargs)


###
### sensors
###

class Sensor(object):

  def __init__(self, *args, **kwargs):
    pass


class Image(Tensor2D):
  
  def __init__(self, *args, **kwargs):
    super(Image, self).__init__(args[0], **kwargs)

class CSPAD(Image, Sensor):
  
  def __init__(self, *args, **kwargs):
    Image.__init__(self, args[0], **kwargs)
    Sensor.__init__(self, args[0], **kwargs)




