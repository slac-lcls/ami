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

def getDataObject(node):
  if not isinstance(node, MappedDataElement):
    return node
  return getDataObject(node.predecessor)


def printArgument(node, argument, indent):
  indentation = ' ' * indent
  if isinstance(eval('node.' + argument), DataElement):
    print(indentation + argument, '\t', eval('node.' + argument), '\t', eval('node.' + argument)._localFields())
    if argument == 'predecessor' and 'predecessor' in dir(eval('node.' + argument)):
      print(indentation + '\tpoints to ' + str(eval('node.' + argument).predecessor))
  else:
    print(indentation + argument, '\t', eval('node.' + argument))
  if isinstance(eval('node.' + argument), MappedDataElement):
    if(eval('node.' + argument)._mapArguments is not None):
      print(indentation + '_mapArguments', eval('node.' + argument)._mapArguments)
    if eval('node.' + argument)._mapFunctionName is not None:
      print(indentation + '_mapFunctionName', eval('node.' + argument)._mapFunctionName)
    printGraphNode(eval('node.' + argument + '.predecessor'), indent + 4)


def printGraphNode(node, indent):
  indentation = ' ' * indent
  arguments = node._localFields()
  args = ''
  if '_args' in dir(node): args = node._args
  print(indentation + node._name, '\t', node, '\t', arguments, args)
  if node._mapArguments is not None:
    print(indentation + '_mapArguments', node._mapArguments)
  if node._mapFunctionName is not None:
    print(indentation + '_mapFunctionName', node._mapFunctionName)
  for argument in arguments:
    printArgument(node, argument, indent + 16)


def printGraph(graph):
  for node in graph._nodes:
    printGraphNode(node, 0)
    



class Graph(object):
  
  def __init__(self, name):
    self._name = name
    self._nodes = []

  def serialize(self):
    filename = "controlStore_" + self.__class__.__name__ + ".dat"
    print('writing to', filename)
    self._removeDynamicMethodsAndLambdas()
    pickle.dump(self, open(filename, "wb"))
  
  def _removeDynamicMethodsAndLambdas(self):
    for node in self._nodes:
      node._removeDynamicMethodsAndLambdas()

  def deserialize(self):
    filename = "controlStore_" + self.__class__.__name__ + ".dat"
    print('reading from', filename)
    result = pickle.load(open(filename, "rb"))
    self._restoreDynamicMethodsAndLambdas(result)
    return result

  def _restoreDynamicMethodsAndLambdas(self, graph):
    for node in graph._nodes:
      node._restoreDynamicMethodsAndLambdas()

  def export(self, element):
    self._nodes.append(element)
  
  def import_(self, name):
    result = Import(name)
    self._nodes.append(result)
    return result
  
  def broadcast(self):
    self.serialize()
  
  def _doMap(self):
    result = {}
    for node in self._nodes:
      if isinstance(node, DataElement):
        returnValue = node._doMap()
        if returnValue is not None:
          result.update(returnValue)
      elif isinstance(node, GraphControlFlow):
        pass # TODO
    return result

  def If(self, lambdaExpression, *args, **kwargs):
    self._nodes.append(If(lambdaExpression, *args, **kwargs))
  
  def Elseif(self, lambdaExpression, *args, **kwargs):
    self._nodes.append(Elseif(lambdaExpression, *args, **kwargs))
  
  def Else(self, lambdaExpression, *args, **kwargs):
    self._nodes.append(Else(lambdaExpression, *args, **kwargs))
  
  def Endif(self, *args, **kwargs):
    self._nodes.append(Endif(*args, **kwargs))





###
### data elements
###


class DataElement(object):
  
  def __init__(self, *args, **kwargs):
    self._name = args[0]
    self._mapFunctionName = None
    self._mapArguments = None
    self.data = numpy.zeros((1, 1))
    if kwargs is not None:
      for key, value in kwargs.items():
        exec('self.' + str(key) + ' = ' + str(value))

  def _dataIs(self, data):
    print('_dataIs', data)
    self.data = data
    print('self.data.shape', self.data.shape)

  def _mapSequence(self, node):
    if isinstance(node, MappedDataElement):
      return self._mapSequence(node.predecessor) + [ (node, node._mapArguments) ]
    if node._mapArguments is not None:
      return [ (node, node._mapArguments) ]
    return [ (node, None) ]

  def _doMapSequence(self, sequence):
    xIndex = 0
    for (node, mapArguments) in sequence[1:]:
      print(node, mapArguments)
      xIndex = xIndex + 1
      functionName = mapArguments[0]
      call = 'node.' + functionName + '(' + ','.join([self._argumentString(arg) for arg in mapArguments[1:]]) + ')[' + "'" + functionName + "'" + ']'
      statement = 'x' + str(xIndex) + ' = ' + call
      print(statement)
      exec(statement)
    return eval('x' + str(xIndex))

  def _doMap(self):
    if self._mapArguments is None:
      return {}
    mapSequence = self._mapSequence(self)
    print(mapSequence)
    return { self._name : self._doMapSequence(mapSequence) }

  def _doreduce(self):
    pass

  def _localFields(self):
    return [arg for arg in dir(self) if arg[0] != '_']

  def _verifyAggregateArgumentType(self, argument):
    if isinstance(argument, dict):
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
    if isinstance(argument, DataElement):
      return True
    baseTypes = [ 'int', 'str', 'float', 'complex', 'function' ]
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
    statement = 'self.' + functionName + ' = types.MethodType(mapFunctions.' + functionName + ', self)'
    print(statement)
    exec(statement)
    self._mapFunctionName = functionName
  
  def _restoreDynamicMethodsAndLambdas(self):
    if self._mapFunctionName is not None:
      self._addDynamicMethod(self._mapFunctionName)
    if isinstance(self, MappedDataElement):
      self.predecessor._restoreDynamicMethodsAndLambdas()
      newMapArguments = []
      for argument in self._mapArguments:
        if isinstance(argument, str) and argument.startswith('lambda'):
          print("the argument we are restoring:", argument)
          newMapArguments.append(eval(argument))
          print('restoring argument', argument)
        else:
          newMapArguments.append(argument)
      self._mapArguments = newMapArguments


  def _removeDynamicMethodsAndLambdas(self):
    if self._mapFunctionName is not None and eval('self.' + self._mapFunctionName) is not None:
      exec('self.' + self._mapFunctionName + ' = None')
    if isinstance(self, MappedDataElement):
      self.predecessor._removeDynamicMethodsAndLambdas()
      if self._mapArguments is not None:
        newMapArguments = []
        for argument in self._mapArguments:
          if isinstance(argument, types.FunctionType):
            newMapArguments.append(str(argument))
            print('saving lambda', str(argument))
          else:
            newMapArguments.append(argument)
        self._mapArguments = newMapArguments

  def _argumentString(self, arg):
    if arg.__class__.__name__ == 'function':
      return str(arg(self))
    else:
      return str(arg)
  
  def _map(self, *args):
    functionName = args[0]
    arguments = args[1:]
    self._verifyArguments(functionName, arguments)
    result = MappedDataElement(self)
    result._mapArguments = args
    result._addDynamicMethod(functionName)
    return result


class MappedDataElement(DataElement):

  def __init__(self, predecessor, *args, **kwargs):
    super(MappedDataElement, self).__init__(predecessor._name, *args, **kwargs)
    self.predecessor = predecessor


###
### control flow
###


class GraphControlFlow(object):

  def __init__(self):
    pass

class If(GraphControlFlow):
  
  def __init__(self, lambdaExpression, *args, **kwargs):
    super(If, self).__init__('iff ' + lambdaExpression, *args, **kwargs)
    self._lambdaExpression = lambdaExpression
    if args is not None: self._args = args
    if kwargs is not None:
      for key, value in kwargs.iteritems():
        exec('self.' + str(key) + ' = ' + str(value))


class Else(GraphControlFlow):
  
  def __init__(self, *args, **kwargs):
    super(Endif, self).__init__('else', *args, **kwargs)
    if args is not None: self._args = args
    if kwargs is not None:
      for key, value in kwargs.iteritems():
        exec('self.' + str(key) + ' = ' + str(value))


class Elseif(GraphControlFlow):
  
  def __init__(self, lambdaExpression, *args, **kwargs):
    super(Endif, self).__init__('elseif ' + lambdaExpression, *args, **kwargs)
    if args is not None: self._args = args
    if kwargs is not None:
      for key, value in kwargs.iteritems():
        exec('self.' + str(key) + ' = ' + str(value))


class Endif(GraphControlFlow):
  
  def __init__(self, *args, **kwargs):
    super(Endif, self).__init__('endif', *args, **kwargs)
    if args is not None: self._args = args
    if kwargs is not None:
      for key, value in kwargs.iteritems():
        exec('self.' + str(key) + ' = ' + str(value))


###
### data recirculation
###

class Import(object):

  def __init__(self, name, *args, **kwargs):
    pass
