#
# AMI_common.py
#

import numpy
import pickle
import math
import types
import dill

import workerFunctions
import localCollectorFunctions
import globalCollectorFunctions

###
### graphs
###

_DATA_ORDER = 0
_WORKER_ORDER = 1
_LOCAL_COLLECTOR_ORDER = 2
_GLOBAL_COLLECTOR_ORDER = 3


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
        node._removeDynamicMethods()

  def deserialize(self):
    filename = "controlStore_" + self.__class__.__name__ + ".dat"
    print('reading from', filename)
    result = dill.load(open(filename, "rb"))
    self._restoreDynamicMethods(result)
    return result

  def _restoreDynamicMethods(self, graph):
    for node in graph._nodes:
      if isinstance(node, ComputedDataElement):
        node._restoreDynamicMethods()

  def addNode(self, element):
    self._nodes.append(element)
  
  def import_(self, name):
    result = Import(name)
    self._nodes.append(result)
    return result
  
  def broadcast(self):
    self.serialize()
  
  def _doComputationNode(self, node, computeOrder):
    if computeOrder == _WORKER_ORDER:
      return node._doComputation(_DATA_ORDER, _WORKER_ORDER)
    elif computeOrder == _LOCAL_COLLECTOR_ORDER:
      return node._doComputation(_LOCAL_COLLECTOR_ORDER, _LOCAL_COLLECTOR_ORDER)
    elif computeOrder == _GLOBAL_COLLECTOR_ORDER:
      return node._doComputation(_GLOBAL_COLLECTOR_ORDER, _GLOBAL_COLLECTOR_ORDER)

  def _doControlNode(self, node):
    return None
  
  def _doComputation(self, computeOrder):
    result = []
    for node in self._nodes:
      node._clearComputation()
    for node in self._nodes:
      if computeOrder == _DATA_ORDER:
        returnValue = node._doReset()
      elif isinstance(node, ComputedDataElement):
        returnValue = self._doComputationNode(node, computeOrder)
      elif isinstance(node, GraphControlFlow):
        returnValue = self._doControlNode(node)
      if returnValue is not None:
        result.append(returnValue)
    return result
  
  def _doReset(self):
    return self._doComputation(_DATA_ORDER)
        
  def _doWorker(self):
    return self._doComputation(_WORKER_ORDER)

  def _doLocalCollector(self):
    return self._doComputation(_LOCAL_COLLECTOR_ORDER)
  
  def _doGlobalCollector(self):
    return self._doComputation(_GLOBAL_COLLECTOR_ORDER)
  
  def If(self, lambdaExpression, *args, **kwargs):
    self._nodes.append(If(lambdaExpression, *args, **kwargs))
  
  def Elseif(self, lambdaExpression, *args, **kwargs):
    self._nodes.append(Elseif(lambdaExpression, *args, **kwargs))
  
  def Else(self, lambdaExpression, *args, **kwargs):
    self._nodes.append(Else(lambdaExpression, *args, **kwargs))
  
  def Endif(self, *args, **kwargs):
    self._nodes.append(Endif(*args, **kwargs))


  def _transmitData(self, networkPath, computeOrder):
    outfile = open(networkPath, 'wb')
    offset = 0
    for node in self._nodes:
      if isinstance(node, ComputedDataElement):
        node._transmitData(outfile, computeOrder)
    outfile.close()

  def _receiveData(self, networkPath, computeOrder):
    infile = open(networkPath, 'rb')
    buffer = infile.read()
    infile.close()
    offset = 0
    for node in self._nodes:
      if isinstance(node, ComputedDataElement):
        offset = node._receiveData(buffer, offset, computeOrder)

  def _transmitWorkerData(self, networkPath):
    self._transmitData(networkPath, _WORKER_ORDER)

  def _transmitLocalCollectorData(self, networkPath):
    self._transmitData(networkPath, _LOCAL_COLLECTOR_ORDER)

  def _transmitGlobalCollectorData(self, networkPath):
    self._transmitData(networkPath, _GLOBAL_COLLECTOR_ORDER)

  def _receiveWorkerData(self, networkPath):
    self._receiveData(networkPath, _WORKER_ORDER)
  
  def _receiveLocalCollectorData(self, networkPath):
    self._receiveData(networkPath, _LOCAL_COLLECTOR_ORDER)
  
  def _receiveGlobalCollectorData(self, networkPath):
    self._receiveData(networkPath, _GLOBAL_COLLECTOR_ORDER)


###
### data elements
###


class DataElement(object):
  
  def __init__(self, *args, **kwargs):
    self._name = args[0]
    self._computedFunctionName = None
    self._computedArguments = None
    self.data = None
    self._computeOrder = _DATA_ORDER
    self._computed = False
    if kwargs is not None:
      for key, value in kwargs.items():
        exec('self.' + str(key) + ' = ' + str(value))

  def _dataIs(self, data):
    self.data = data

  def _doReset(self):
    sequence = self._invertSequence()
    for node in sequence:
      if node._computedFunctionName is not None:
        functionName = node._computedFunctionName
        functionName = functionName + '_'
        if hasattr(node, functionName) and callable(eval('node.' + functionName)):
          call = 'node.' + functionName + '(' + ','.join([self._argumentString(arg) for arg in self._computedArguments]) + ')'
          exec(call)
      if hasattr(node, 'predecessor'):
        node = node.predecessor
      else:
        node = None
        
  def _invertSequence(self):
    if isinstance(self, ComputedDataElement):
      return self.predecessor._invertSequence() + [ self ]
    return [ self ]

  def _clearComputation(self):
    self._computed = False
    if hasattr(self, 'predecessor') and self.predecessor is not None:
      self.predecessor._clearComputation()

  def _compute(self, lastElement, computeOrderMin, computeOrderMax, called):
    self._computed = True
    called = self._inRange(computeOrderMin, computeOrderMax)
    return self, called

  def _transmitData(self, outfile, computeOrder):
    pass

  def _receiveData(self, buffer, offset, computeOrder):
    return offset

  def _inRange(self, computeOrderMin, computeOrderMax):
    return self._computeOrder >= computeOrderMin and self._computeOrder <= computeOrderMax

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
  
  def _restoreDynamicMethodsOfOneType(self, functionImport, clazz):
    if isinstance(self, clazz):
      for functionName in eval('dir(' + functionImport + ')'):
        if functionName[0] != '_' and callable(eval(functionImport + '.' + functionName)):
          self._addDynamicMethod(functionName, functionImport)
    if isinstance(self, ComputedDataElement):        self.predecessor._restoreDynamicMethodsOfOneType(functionImport, clazz)

  def _removeDynamicMethodsOfOneType(self, functionImport, clazz):
    if isinstance(self, clazz):
      for functionName in eval('dir(' + functionImport + ')'):
        if functionName[0] != '_' and callable(eval(functionImport + '.' + functionName)):
          exec('self.' + functionName + ' = None')
    if isinstance(self, ComputedDataElement):        self.predecessor._removeDynamicMethodsOfOneType(functionImport, clazz)


  def _argumentString(self, arg):
    if arg.__class__.__name__ == 'function':
      return str(arg(self))
    else:
      return str(arg)

  def _operation(self, result, args, functionImport):
    functionName = args[0]
    arguments = args[1:]
    self._verifyArguments(functionName, arguments)
    result._computedArguments = arguments
    result._addDynamicMethod(functionName, functionImport)
    result._computedFunctionName = functionName
    return result

  def _worker(self, *args):
    result = self._operation(WorkerOperation(self), args, 'workerFunctions')
    return result

  def _localCollector(self, *args):
    result = self._operation(LocalCollectorOperation(self), args, 'localCollectorFunctions')
    return result

  def _globalCollector(self, *args):
    result = self._operation(GlobalCollectorOperation(self), args, 'globalCollectorFunctions')
    return result




class ComputedDataElement(DataElement):

  def __init__(self, predecessor, *args, **kwargs):
    super(ComputedDataElement, self).__init__(predecessor._name, *args, **kwargs)
    self.predecessor = predecessor
    self.data = None
    self._operand = None

  def _transmitData(self, outfile, computeOrder):
    if self._computeOrder == computeOrder:
      if self.data is not None:
        data = pickle.dumps(self.data)
        length = len(data)
        outfile.write(length.to_bytes(4, 'big'))
        outfile.write(data)
    if self.predecessor is not None:
      self.predecessor._transmitData(outfile, computeOrder)

  def _receiveData(self, buffer, offset, computeOrder):
    if self._computeOrder == computeOrder:
      length = int.from_bytes(buffer[offset : offset + 4], 'big')
      data = buffer[offset + 4 : offset + 4 + length]
      offset = offset + 4 + length
      self.data = pickle.loads(data)
    if self.predecessor is not None:
      offset = self.predecessor._receiveData(buffer, offset, computeOrder)
    return offset

  def _call(self, called):
    if self._computedFunctionName is not None and callable(eval('self.' + self._computedFunctionName)):
      call = 'self.' + self._computedFunctionName + '(' + ','.join([self._argumentString(arg) for arg in self._computedArguments]) + ')'
      return eval(call), True
    return None, called

  def _compute(self, lastElement, computeOrderMin, computeOrderMax, called):
    self._computed = True
    if self._inRange(computeOrderMin, computeOrderMax) and isinstance(self, ComputedDataElement):
      if lastElement is None:
        self.operand = self.data
      else:
        self.operand = lastElement.data
      lastElement, called = self._call(called)
    else:
      lastElement = self
    return lastElement, called


  def _doComputation(self, computeOrderMin, computeOrderMax):
    sequence = self._invertSequence()
    print(sequence)##########
    lastElement = None
    called = False
    for i in range(len(sequence)):
      node = sequence[i]
      if not node._computed:
        lastElement, called = node._compute(lastElement, computeOrderMin, computeOrderMax, called)
      else:
        lastElement = node
    if called:
      return lastElement

  def _removeDynamicMethods(self):
    self._removeDynamicMethodsOfOneType('workerFunctions', WorkerOperation)
    self._removeDynamicMethodsOfOneType('localCollectorFunctions', LocalCollectorOperation)
    self._removeDynamicMethodsOfOneType('globalCollectorFunctions', GlobalCollectorOperation)

  def _restoreDynamicMethods(self):
    self._restoreDynamicMethodsOfOneType('workerFunctions', WorkerOperation)
    self._restoreDynamicMethodsOfOneType('localCollectorFunctions', LocalCollectorOperation)
    self._restoreDynamicMethodsOfOneType('globalCollectorFunctions', GlobalCollectorOperation)


class WorkerOperation(ComputedDataElement):
  
  def __init__(self, predecessor, *args, **kwargs):
    super(WorkerOperation, self).__init__(predecessor, *args, **kwargs)
    self._computeOrder = _WORKER_ORDER


class LocalCollectorOperation(ComputedDataElement):
  
  def __init__(self, predecessor, *args, **kwargs):
    super(LocalCollectorOperation, self).__init__(predecessor, *args, **kwargs)
    self._computeOrder = _LOCAL_COLLECTOR_ORDER



class GlobalCollectorOperation(ComputedDataElement):
  
  def __init__(self, predecessor, *args, **kwargs):
    super(GlobalCollectorOperation, self).__init__(predecessor, *args, **kwargs)
    self._computeOrder = _GLOBAL_COLLECTOR_ORDER




###
### control flow
###


class GraphControlFlow(object):

  def __init__(self, name, *args, **kwargs):
    self._name = name
    if args is not None: self._args = args
    if kwargs is not None and len(kwargs) > 0:
      for key, value in kwargs.iteritems():
        exec('self.' + str(key) + ' = ' + str(value))

  def _clearComputation(self):
    pass

  def _doReset(self):
    pass

class If(GraphControlFlow):
  
  def __init__(self, lambdaExpression, *args, **kwargs):
    super(If, self).__init__('iff ' + lambdaExpression, *args, **kwargs)
    self._lambdaExpression = lambdaExpression


class Else(GraphControlFlow):
  
  def __init__(self, *args, **kwargs):
    super(Else, self).__init__('else', *args, **kwargs)


class Elif(GraphControlFlow):
  
  def __init__(self, lambdaExpression, *args, **kwargs):
    super(Elif, self).__init__('elif ' + lambdaExpression, *args, **kwargs)
    self._lambdaExpression = lambdaExpression


class Endif(GraphControlFlow):
  
  def __init__(self, *args, **kwargs):
    super(Endif, self).__init__('endif', *args, **kwargs)



###
### data recirculation
###

class Import(object):

  def __init__(self, name, *args, **kwargs):
    pass


###
### print graph
###


def printControlFlowNode(node, indent):
  indentation = ' ' * indent
  print(indentation + node.__class__.__name__, node._name)

def printComputationNode(node, indent):
  indentation = ' ' * indent
  arguments = node._localFields()
  args = ''
  if '_args' in dir(node): args = node._args
  print(indentation + node._name, '\t', node, '\t', arguments, args)
  if node._computedArguments is not None:
    print(indentation + '_computedArguments', node._computedArguments)
  if node._computedFunctionName is not None:
    computationType = node.__class__.__name__
    print(indentation + computationType, node._computedFunctionName)
  for argument in arguments:
    if argument == 'predecessor':
      printGraphNode(node.predecessor, indent + 4)

def printGraphNode(node, indent):
  indentation = ' ' * indent
  if isinstance(node, GraphControlFlow):
    printControlFlowNode(node, indent)
  else:
    printComputationNode(node, indent)


def printGraph(graph):
  print('-----------------------------------------------------')
  for node in graph._nodes:
    print('-----')
    printGraphNode(node, 0)
  print('-----------------------------------------------------')

