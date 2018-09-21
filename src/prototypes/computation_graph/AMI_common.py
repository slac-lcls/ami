#
# AMI_common.py
#

import numpy
import pickle
import math
import types
import dill

import operators


###
### graphs
###

_DATA_ORDER = 0
_WORKER_ORDER = 1
_LOCAL_COLLECTOR_ORDER = 2
_GLOBAL_COLLECTOR_ORDER = 3

_TRACE_COMPUTATION = False


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
  
  def _doComputationNode(self, node, computeOrder, i, args):
    if computeOrder == _WORKER_ORDER:
      return node._doComputation(_DATA_ORDER, _WORKER_ORDER, i, args)
    elif computeOrder == _LOCAL_COLLECTOR_ORDER:
      return node._doComputation(_LOCAL_COLLECTOR_ORDER, _LOCAL_COLLECTOR_ORDER, i, args)
    elif computeOrder == _GLOBAL_COLLECTOR_ORDER:
      return node._doComputation(_GLOBAL_COLLECTOR_ORDER, _GLOBAL_COLLECTOR_ORDER, i , args)

  def _doControlNode(self, node):
    return None
  
  def _doComputation(self, computeOrder, args):
    result = []
    for node in self._nodes:
      node._clearComputation()
    for i in range(len(self._nodes)):
      node = self._nodes[i]
      if computeOrder == _DATA_ORDER:
        returnValue = node._doReset()
      elif isinstance(node, ComputedDataElement):
        returnValue = self._doComputationNode(node, computeOrder, i, args)
      elif isinstance(node, GraphControlFlow):
        returnValue = self._doControlNode(node)
      if returnValue is not None:
        result.append(returnValue)
    return result
  
  def _doReset(self, *args):
    if _TRACE_COMPUTATION: print('graph._doReset', self._name)
    return self._doComputation(_DATA_ORDER, args)
        
  def _doWorker(self, *args):
    return self._doComputation(_WORKER_ORDER, args)

  def _doLocalCollector(self, *args):
    return self._doComputation(_LOCAL_COLLECTOR_ORDER, args)
  
  def _doGlobalCollector(self, *args):
    return self._doComputation(_GLOBAL_COLLECTOR_ORDER, args)
  
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
    self._processed = False
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
          if _TRACE_COMPUTATION: print(call)
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
    self._processed = False
    if hasattr(self, 'predecessor') and self.predecessor is not None:
      self.predecessor._clearComputation()

  def _compute(self, lastElement, computeOrderMin, computeOrderMax, called, peerSequences, index):
    self._processed = True
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

  def _verifyKeywordArguments(self, keywordArguments):
    arguments = ()
    for (lhs, rhs) in keywordArguments.items():
      if not self._verifySimpleArgumentType(rhs):
        badcall = self._name + '.' + functionName + ' passes invalid argument ' + str(rhs)
        raise ValueError( badcall )
      else:
        arguments = arguments + (str(lhs) + '=' + str(rhs), )
    return arguments

  def _addDynamicMethod(self, functionName):
    statement = 'self.' + functionName + ' = types.MethodType(operators.' + functionName + ', self)'
    exec(statement)

  def _restoreDynamicMethods(self):
    for functionName in dir(operators):
      if functionName[0] != '_' and callable(eval('operators.' + functionName)):
        self._addDynamicMethod(functionName)
    if isinstance(self, ComputedDataElement):        self.predecessor._restoreDynamicMethods()
  
  def _removeDynamicMethods(self):
    for functionName in dir(operators):
      if functionName[0] != '_' and callable(eval('operators.' + functionName)):
        exec('self.' + functionName + ' = None')
    if isinstance(self, ComputedDataElement):        self.predecessor._removeDynamicMethods()

  def _argumentString(self, arg):
    if arg.__class__.__name__ == 'function':
      return str(arg(self))
    else:
      return str(arg)

  def _operation(self, result, args, kwargs):
    functionName = args[0]
    arguments = args[1:]
    self._verifyArguments(functionName, arguments)
    keywordArguments = self._verifyKeywordArguments(kwargs)
    result._computedArguments = arguments + keywordArguments
    result._addDynamicMethod(functionName)
    result._computedFunctionName = functionName
    return result

  def _worker(self, *args, **kwargs):
    result = self._operation(WorkerOperation(self), args, kwargs)
    return result

  def _localCollector(self, *args, **kwargs):
    result = self._operation(LocalCollectorOperation(self), args, kwargs)
    return result

  def _globalCollector(self, *args, **kwargs):
    result = self._operation(GlobalCollectorOperation(self), args, kwargs)
    return result




class ComputedDataElement(DataElement):

  def __init__(self, predecessor, *args, **kwargs):
    super(ComputedDataElement, self).__init__(predecessor._name, *args, **kwargs)
    self.predecessor = predecessor
    self.data = None
    self._operands = None

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
    if _TRACE_COMPUTATION: print('_call', self)
    if self._computedFunctionName is not None and callable(eval('self.' + self._computedFunctionName)):
      call = 'self.' + self._computedFunctionName + '(' + ','.join([self._argumentString(arg) for arg in self._computedArguments]) + ')'
      if _TRACE_COMPUTATION: print(call)
      return eval(call), True
    return None, called

  def _marshallOperands(self, lastElement, peerSequences, index):
    result = []
    if lastElement is None:
      result.append(self.data)
    else:
      result.append(lastElement.data)
    for sequence in peerSequences:
      node = sequence[index]
      if hasattr(node, 'predecessor'):
        node = node.predecessor
      result.append(node.data)
    self.operands = result

  def _compute(self, lastElement, computeOrderMin, computeOrderMax, called, peerSequences, index):
    if _TRACE_COMPUTATION: print('_compute', self, lastElement)
    self._processed = True
    self._marshallOperands(lastElement, peerSequences, index)
    lastElement, called = self._call(called)
    return lastElement, called

  def _invertPeerSequences(self, nodeIndex, args):
    result = []
    for graph in args:
      node = graph._nodes[nodeIndex]
      result.append(node._invertSequence())
    return result

  def _doComputation(self, computeOrderMin, computeOrderMax, nodeIndex, args):
    sequence = self._invertSequence()
    if _TRACE_COMPUTATION: print('_doComputation, sequence', sequence)
    peerSequences = self._invertPeerSequences(nodeIndex, args)
    lastElement = None
    called = False
    for i in range(len(sequence)):
      node = sequence[i]
      if not node._processed and node._inRange(computeOrderMin, computeOrderMax) and isinstance(node, ComputedDataElement):
        lastElement, called = node._compute(lastElement, computeOrderMin, computeOrderMax, called, peerSequences, i)
      else:
        lastElement = node
    if called:
      return lastElement



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

