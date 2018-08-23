#
# AMI_common.py
#

import numpy
import pickle
import math
import types

import mapFunctions

###
### graphs
###

def printArgument(node, argument, indent):
  indentation = ' ' * indent
  if isinstance(eval('node.' + argument), GraphElement):
    print(indentation + argument, '\t', eval('node.' + argument), '\t', eval('node.' + argument)._localFields())
    if argument == 'predecessor' and 'predecessor' in dir(eval('node.' + argument)):
      print(indentation + '\tpoints to ' + str(eval('node.' + argument).predecessor))
  else:
    print(indentation + argument, '\t', eval('node.' + argument))
  if eval('node.' + argument + '.__class__.__name__').endswith('MappedGraphElement'):
    if(eval('node.' + argument)._maps is not None):
      print(indentation + '_maps', eval('node.' + argument)._maps)
      print(indentation + '_mapFunctions', eval('node.' + argument)._importedMaps())
    printGraphNode(eval('node.' + argument + '.predecessor'), indent + 4)


def printGraphNode(node, indent):
  indentation = ' ' * indent
  arguments = node._localFields()
  args = ''
  if '_args' in dir(node): args = node._args
  print(indentation + node._name, '\t', node, '\t', arguments, args)
  if node._maps is not None:
    print(indentation + '_maps', node._maps)
    print(indentation + '_mapFunctions', node._importedMaps())
  for argument in arguments:
    printArgument(node, argument, indent + 16)


def printGraph(graph):
  for node in graph._nodes:
    printGraphNode(node, 0)
    


class FunctionObject:

  def __init__(self):
    pass


class Graph(object):
  
  def __init__(self, name):
    self._name = name
    self._nodes = []

  def serialize(self):
    filename = "controlStore_" + self.__class__.__name__ + ".dat"
    print('writing to', filename)
    self._removeDynamicMethods()
    pickle.dump(self, open(filename, "wb"))
  
  def _removeDynamicMethods(self):
    for node in self._nodes:
      node._removeDynamicMethods()

  def deserialize(self):
    filename = "controlStore_" + self.__class__.__name__ + ".dat"
    print('reading from', filename)
    result = pickle.load(open(filename, "rb"))
    self._restoreDynamicMethods(result)
    return result

  def _restoreDynamicMethods(self, graph):
    for node in graph._nodes:
      node._restoreDynamicMethods()

  def export(self, element):
    self._nodes.append(element)
  
  def import_(self, name):
    result = Import(name)
    self._nodes.append(result)
    return result
  
  def broadcast(self):
    self.serialize()
  
  def _domap(self, telemetryFrame):
    result = {}
    for node in self._nodes:
      returnValue = node._domap(telemetryFrame)
      if returnValue is not None:
        result.update(returnValue)
    return result

  def _If(self, lambdaExpression, *args, **kwargs):
    self._nodes.append(If(lambdaExpression, *args, **kwargs))
  
  def _Elseif(self, lambdaExpression, *args, **kwargs):
    self._nodes.append(Elseif(lambdaExpression, *args, **kwargs))
  
  def _Else(self, lambdaExpression, *args, **kwargs):
    self._nodes.append(Else(lambdaExpression, *args, **kwargs))
  
  def _Endif(self, *args, **kwargs):
    self._nodes.append(Endif(*args, **kwargs))

###
### top level functions for use by map and reduce functions
###


def getDataObject(node):
  print('getDataObject', node)
  printGraphNode(node, 0)
  if not isinstance(node, MappedGraphElement):
    return node
  return getDataObject(node.predecessor)


###
### graph elements
###


class GraphElement(object):
  
  def __init__(self, *args, **kwargs):
    self._name = args[0]
    self._maps = None
    self._mapFunctions = FunctionObject()
    self._reductions = None
    self.shape = [1]
    self.origin = [0]
    if kwargs is not None:
      for key, value in kwargs.items():
        exec('self._' + str(key) + ' = ' + str(value))

  def _mapSequence(self, node):
    if node.__class__.__name__.endswith('MappedGraphElement'):
      return self._mapSequence(node.predecessor) + [ (node, node._maps) ]
    if node._maps is not None:
      return [ (node, node._maps) ]
    return [ (node, None) ]

  def _doMapSequence(self, sequence):
    (baseObject, dummy) = sequence[0]
    print('baseObject', baseObject, baseObject._importedMaps())
    xIndex = 0
    for (node, map) in sequence[1:]:
      print('node', node, 'map', map)
      printGraphNode(node, 2)
      xIndex = xIndex + 1
      statement = 'x' + str(xIndex) + ' = ' + map
      print(statement)
      exec(statement)
    return eval('x' + str(xIndex))

  def _transferTelemetry(self, telemetryFrame):
    value = telemetryFrame[self._name]
    if value is not None and self._ingestTelemetry is not None:
      self._ingestTelemetry(value)

  def _domap(self, telemetryFrame):
    if self._maps is None:
      return {}
    if not self.__class__.__name__.endswith('MappedGraphElement'):
      self._transferTelemetry(telemetryFrame)
    mapSequence = self._mapSequence(self)
    print('mapSequence', mapSequence)
    result = { self._name : self._doMapSequence(mapSequence) }
    return result

  def _doreduce(self):
    pass

  def _localFields(self):
    result = []
    for arg in dir(self):
      if arg[0] != '_': result.append(arg)
    return result
  
  def _verifyAggregateArgumentType(self, argument):
    if argument.__class__.__name__ == 'dict':
      for key in argument.items():
        if not self._verifySimpleArgumentType(argument[key]):
          return False
      return True
    else:
      for a in argument:
        if not self._verifySimpleArgumentType(a):
          return False
      return True

  def _verifySimpleArgumentType(self, argument):
    if issubclass(argument.__class__, GraphElement):
      return True
    baseTypes = [ 'int', 'str', 'float', 'complex' ]
    if argument.__class__.__name__ in baseTypes:
      return True
    aggregateTypes = [ 'dict', 'list', 'tuple' ]
    if argument.__class__.__name__ in aggregateTypes:
      return self._verifyAggregateArgumentType(argument)
    return False

  def _verifyArguments(self, functionName, arguments):
    for arg in arguments:
      if not self._verifySimpleArgumentType(arg):
        badcall = self._name + '.' + functionName + ' passes invalid argument ' + str(arg)
        raise ValueError( badcall )

  def _addDynamicMethod(self, functionName):
    root = 'self._mapFunctions.' + functionName
    statement = root + ' = types.MethodType(mapFunctions.' + functionName + ', self._mapFunctions)'
    exec(statement)
    self._mapFunctions._baseObject = self
  
  def _restoreDynamicMethods(self):
    self._mapFunctions = FunctionObject()
    for functionName in self._mapFunctionNames:
      self._addDynamicMethod(functionName)
    if self.__class__.__name__.endswith('MappedGraphElement'):
      self.predecessor._restoreDynamicMethods()

  def _removeDynamicMethods(self):
    self._mapFunctionNames = self._importedMaps()
    self._mapFunctions = None
    if self.__class__.__name__.endswith('MappedGraphElement'):
      self.predecessor._removeDynamicMethods()

  def _importedMaps(self):
    result = [ arg for arg in dir(self._mapFunctions) if arg[0] != '_' ]
    return result

  def _map(self, *args):
    functionName = args[0]
    arguments = args[1:]
    self._verifyArguments(functionName, arguments)
    result = MappedGraphElement(self)
    call = 'node._mapFunctions.' + functionName + '(' + ','.join([str(arg) for arg in arguments]) + ')[' + "'" + functionName + "'" + ']'
    result._maps = call
    result._addDynamicMethod(functionName)
    return result


class MappedGraphElement(GraphElement):

  def __init__(self, predecessor, *args, **kwargs):
    super(MappedGraphElement, self).__init__(predecessor._name, *args, **kwargs)
    self.predecessor = predecessor



class If(GraphElement):
  
  def __init__(self, lambdaExpression, *args, **kwargs):
    super(If, self).__init__('iff ' + lambdaExpression, *args, **kwargs)
    self._lambdaExpression = lambdaExpression
    if args is not None: self._args = args
    if kwargs is not None:
      for key, value in kwargs.iteritems():
        exec('self.' + str(key) + ' = ' + str(value))


class Else(GraphElement):
  
  def __init__(self, *args, **kwargs):
    super(Endif, self).__init__('else', *args, **kwargs)
    if args is not None: self._args = args
    if kwargs is not None:
      for key, value in kwargs.iteritems():
        exec('self.' + str(key) + ' = ' + str(value))


class Elseif(GraphElement):
  
  def __init__(self, lambdaExpression, *args, **kwargs):
    super(Endif, self).__init__('elseif ' + lambdaExpression, *args, **kwargs)
    if args is not None: self._args = args
    if kwargs is not None:
      for key, value in kwargs.iteritems():
        exec('self.' + str(key) + ' = ' + str(value))


class Endif(GraphElement):
  
  def __init__(self, *args, **kwargs):
    super(Endif, self).__init__('endif', *args, **kwargs)
    if args is not None: self._args = args
    if kwargs is not None:
      for key, value in kwargs.iteritems():
        exec('self.' + str(key) + ' = ' + str(value))



class Import(GraphElement):

  def __init__(self, name, *args, **kwargs):
    super(Import, self).__init__('import ' + name, *args, **kwargs)

  def _get(self, name):
    return None



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


class Vector(Tensor1D):
  
  def __init__(self, *args, **kwargs):
    super(Vector, self).__init__(args[0], **kwargs)

class Tensor2D(Tensor):
  
  def __init__(self, *args, **kwargs):
    super(Tensor2D, self).__init__(args[0], **kwargs)

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
    self.shape = [ 1024, 1024 ] # todo get from XTC schema
    self.origin = [ 0, 0 ]
    self._allocateData()

  def _ingestTelemetry(self, value):
    self.data = value.data

  def _allocateData(self):
    self.data = numpy.zeros(self.shape)


