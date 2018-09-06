#
# AMI_common.py
#

import numpy
import pickle
import math
import types
import dill

import mapFunctions
import reduceFunctions

###
### graphs
###




class Graph(object):
  
  def __init__(self, name):
    self._name = name
    self._nodes = []

  def serialize(self):
    filename = "controlStore_" + self.__class__.__name__ + ".dat"
    print('writing to', filename)
    self._removeDynamicMethods()
    dill.dump(self, open(filename, "wb"))
  
  def _removeDynamicMethods(self):
    for node in self._nodes:
      if isinstance(node, ComputedDataElement):
        if node._isMap:
          node._removeDynamicMethods('mapFunctions')
        else:
          node._removeDynamicMethods('reduceFunctions')

  def deserialize(self):
    filename = "controlStore_" + self.__class__.__name__ + ".dat"
    print('reading from', filename)
    result = dill.load(open(filename, "rb"))
    self._restoreDynamicMethods(result)
    return result

  def _restoreDynamicMethods(self, graph):
    for node in graph._nodes:
      if isinstance(node, ComputedDataElement):
        if node._isMap:
          node._restoreDynamicMethods('mapFunctions')
        else:
          node._restoreDynamicMethods('reduceFunctions')

  def addNode(self, element):
    self._nodes.append(element)
  
  def import_(self, name):
    result = Import(name)
    self._nodes.append(result)
    return result
  
  def broadcast(self):
    self.serialize()
  
  def _doComputation(self, reset=False, map=False, reduce=False):
    result = []
    for node in self._nodes:
      if isinstance(node, DataElement):
        returnValue = node._doComputation(reset, map, reduce)
        if returnValue is not None:
          result.append(returnValue)
      elif isinstance(node, GraphControlFlow):
        pass # TODO
    print('graph._doComputation returns', result)
    for node in result:
      if isinstance(node, DataElement):
        printGraphNode(node, 0)
    return result
  
  def _doReset(self):
    return self._doComputation(reset=True)
        
  def _doMap(self):
    return self._doComputation(map=True)

  def _doReduce(self):
    return self._doComputation(reduce=True)
  
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
    self._computedFunctionName = None
    self._computedArguments = None
    self.data = None
    if kwargs is not None:
      for key, value in kwargs.items():
        exec('self.' + str(key) + ' = ' + str(value))

  def _dataIs(self, data):
    self.data = data

  def _computedSequence(self, node):
    if isinstance(node, ComputedDataElement):
      (priorSequence, priorIsMap) = self._computedSequence(node.predecessor)
      return (priorSequence + [ (node, node._computedArguments) ], node._isMap and priorIsMap)
    if node._computedArguments is not None:
      return ([ (node, node._computedArguments) ], node._isMap and priorIsMap)
    return ([ (node, None) ], True)

  def _doResetSequence(self, sequence):
    for (node, arguments) in sequence[1:]:
      functionName = node._computedFunctionName
      functionName = functionName + '_'
      if hasattr(node, functionName) and callable(eval('node.' + functionName)):
        call = 'node.' + functionName + '(' + ','.join([self._argumentString(arg) for arg in arguments]) + ')'
        print(call)
        exec(call)

  def _doMapSequence(self, sequence):
    xIndex = 0
    x0 = sequence[0][0]
    lastElement = 'x0'
    for (node, arguments) in sequence[1:]:
      xIndex = xIndex + 1
      nextElement = 'x' + str(xIndex)
      if hasattr(eval(lastElement), 'result'):
        operand = lastElement + '.result'
      else:
        operand = lastElement + '.data'
      node._dataIs(eval(operand))
      functionName = node._computedFunctionName
      if functionName is not None:
        call = 'node.' + functionName + '(' + ','.join([self._argumentString(arg) for arg in arguments]) + ')'
        statement = nextElement + ' = ' + call
        print(statement)
        exec(statement)
        lastElement = nextElement
    return eval(nextElement)

  def _doReduceSequence(self, sequence):
    xIndex = 0
    x0 = sequence[0][0]
    lastElement = 'x0'
    for (node, arguments) in sequence[1:]:
      xIndex = xIndex + 1
      nextElement = 'x' + str(xIndex)
      if not node._isMap:
        if hasattr(eval(lastElement), 'result'):
          operand = lastElement + '.result'
        else:
          operand = lastElement + '.data'
        node._dataIs(eval(operand))
      functionName = node._computedFunctionName
      if functionName is not None:
        if not node._isMap:
          call = 'node.' + functionName + '(' + ','.join([self._argumentString(arg) for arg in arguments]) + ')'
        else:
          call = 'node'
        statement = nextElement + ' = ' + call
        print(statement)
        exec(statement)
        lastElement = nextElement
    return eval(nextElement)

  def _doComputation(self, reset, map, reduce):
    if self._computedArguments is None:
      return {}
    (sequence, isMap) = self._computedSequence(self)
    if reset:
      return self._doResetSequence(sequence)
    elif (map and isMap):
      return self._doMapSequence(sequence)
    elif not (map or isMap):
      return self._doReduceSequence(sequence)

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

  def _addDynamicMethod(self, functionName, functionImport):
    statement = 'self.' + functionName + ' = types.MethodType(' + functionImport + '.' + functionName + ', self)'
    exec(statement)
  
  def _restoreDynamicMethods(self, functionImport):
    if not isinstance(self, ComputedDataElement) or not hasattr(self, '_isMap'):
      return
    if self._isMap and functionImport != 'mapFunctions':
      return
    if not self._isMap and functionImport != 'reduceFunctions':
      return
    for functionName in eval('dir(' + functionImport + ')'):
      if functionName[0] != '_' and callable(eval(functionImport + '.' + functionName)):
        self._addDynamicMethod(functionName, functionImport)
    if isinstance(self, ComputedDataElement):
      self.predecessor._restoreDynamicMethods(functionImport)

  def _removeDynamicMethods(self, functionImport):
    for functionName in eval('dir(' + functionImport + ')'):
      if functionName[0] != '_' and callable(eval(functionImport + '.' + functionName)):
        exec('self.' + functionName + ' = None')
    if isinstance(self, ComputedDataElement):
      self.predecessor._removeDynamicMethods(functionImport)

  def _argumentString(self, arg):
    if arg.__class__.__name__ == 'function':
      return str(arg(self))
    else:
      return str(arg)

  def _compute(self, functionName, arguments, functionImport):
    self._verifyArguments(functionName, arguments)
    result = ComputedDataElement(self)
    result._computedArguments = arguments
    result._addDynamicMethod(functionName, functionImport)
    result._computedFunctionName = functionName
    return result

  def _map(self, *args):
    functionName = args[0]
    arguments = args[1:]
    result = self._compute(functionName, arguments, 'mapFunctions')
    result._isMap = True
    return result

  def _reduce(self, *args):
    functionName = args[0]
    arguments = args[1:]
    result = self._compute(functionName, arguments, 'reduceFunctions')
    result._isMap = False
    return result



class ComputedDataElement(DataElement):

  def __init__(self, predecessor, *args, **kwargs):
    super(ComputedDataElement, self).__init__(predecessor._name, *args, **kwargs)
    self.predecessor = predecessor
    self._isMap = None
    self.data = predecessor.data


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


###
### print graph
###

def printArgument(node, argument, indent):
  indentation = ' ' * indent
  if isinstance(eval('node.' + argument), DataElement):
    print(indentation + argument, '\t', eval('node.' + argument), '\t', eval('node.' + argument)._localFields())
    if argument == 'predecessor' and 'predecessor' in dir(eval('node.' + argument)):
      print(indentation + '\tpoints to ' + str(eval('node.' + argument).predecessor))
  else:
    print(indentation + argument, '\t', eval('node.' + argument))
  if isinstance(eval('node.' + argument), ComputedDataElement):
    if(eval('node.' + argument)._computedArguments is not None):
      print(indentation + '_computedArguments', eval('node.' + argument)._computedArguments)
    if eval('node.' + argument)._computedFunctionName is not None:
      if eval('node.' + argument)._isMap:
        computationType = 'map'
      else:
        computationType = 'reduce'
      print(indentation + computationType, eval('node.' + argument)._computedFunctionName)
    printGraphNode(eval('node.' + argument + '.predecessor'), indent + 4)


def printGraphNode(node, indent):
  indentation = ' ' * indent
  arguments = node._localFields()
  args = ''
  if '_args' in dir(node): args = node._args
  print(indentation + node._name, '\t', node, '\t', arguments, args)
  if node._computedArguments is not None:
    print(indentation + '_computedArguments', node._computedArguments)
  if node._computedFunctionName is not None:
    if node._isMap:
      computationType = 'map'
    else:
      computationType = 'reduce'
    print(indentation + computationType, node._computedFunctionName)
  for argument in arguments:
    printArgument(node, argument, indent + 16)


def printGraph(graph):
  for node in graph._nodes:
    printGraphNode(node, 0)

