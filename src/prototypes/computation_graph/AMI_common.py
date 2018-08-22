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

def printGraph(graph):
  for node in graph._nodes:
    arguments = node._arguments()
    args = ''
    if '_args' in dir(node): args = node._args
    print( node._name, '\t', node, '\t', arguments, args)
    for argument in arguments:
      print( '\t\t', argument, '\t', eval('node.' + argument))


class FunctionObject:

  def __init__(self):
    pass


class Graph(object):
  
  def __init__(self, name):
    self._name = name
    self._nodes = []
    self.importMaps()
  
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
  
  def importMaps(self):
    self.mapFunctions = FunctionObject()
    for functionName in dir(mapFunctions):
      if not functionName.startswith('_'):
        root = 'self.mapFunctions.' + functionName
        statement = root + ' = types.MethodType( mapFunctions.' + functionName + ', self.mapFunctions)'
        exec(statement)

  def If(self, lambdaExpression, *args, **kwargs):
    self._nodes.append(If(lambdaExpression, *args, **kwargs))
  
  def Elseif(self, lambdaExpression, *args, **kwargs):
    self._nodes.append(Elseif(lambdaExpression, *args, **kwargs))
  
  def Else(self, lambdaExpression, *args, **kwargs):
    self._nodes.append(Else(lambdaExpression, *args, **kwargs))
  
  def Endif(self, *args, **kwargs):
    self._nodes.append(Endif(*args, **kwargs))



###
### graph elements
###


class GraphElement(object):
  
  def __init__(self, *args, **kwargs):
    self._name = args[0]
    print('GraphElement name =', self._name)
    self._maps = []
    self._reductions = []
    self.shape = [1]
    if kwargs is not None:
      for key, value in kwargs.items():
        exec('self._' + str(key) + ' = ' + str(value))
  
  def _domap(self, telemetryFrame):
    result = {}
    for f in _maps:
      mapResult = eval('self.' + f)
      result.update(mapResult)
    return result

  def _doreduce(self):
    result = {}
    for f in _reductions:
      reduceResult = eval('self.' + f)
      result.update(reduceResult)
    return result

  def _arguments(self):
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
    print('verify', argument, argument.__class__)
    if issubclass(argument.__class__, GraphElement):
      return True
    baseTypes = [ 'int', 'str', 'float', 'complex' ]
    if argument.__class__.__name__ in baseTypes:
      return True
    aggregateTypes = [ 'dict', 'list', 'tuple' ]
    if argument.__class__.__name__ in aggregateTypes:
      return self._verifyAggregateArgumentType(self, argument)
    return False

  def _verifyArguments(self, functionName, arguments):
    for arg in arguments:
      if not self._verifySimpleArgumentType(arg):
        badcall = self._name + '.' + functionName + ' passes invalid argument ' + str(arg)
        raise ValueError( badcall )

  def _map(self, *args):
    functionName = args[0]
    arguments = args[1:]
    self._verifyArguments(functionName, arguments)
    call = 'self.mapFunctions.' + functionName + '('
    for arg in arguments:
      call = call + str(arg) + ','
    call = call + ')'
    self._maps.append(call)
    return MappedGraphElement(self)


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




