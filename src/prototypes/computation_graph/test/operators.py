
import AMI_common as AMI
import numpy

def sum(self, *args, **kwargs):
  print('in sum', self, self.data)
  (data, samples) = self.data
  for operand in self.operands:
    if len(operand) == 2:
      (data1, samples1) = operand
    else:
      data1 = operand
      samples1 = 1
    if data is None:
      data = data1
      samples = samples1
    else:
      data = data + data1
      samples = samples + samples1
  self.data = (data, samples)
  print('sum result', self.data)
  if len(args) > 0:
    if self.data[1] >= args[0]:
      return self
  else:
    return self

def sum_(self, *args, **kwargs):
  print('in sum_ reset', self)
  self.data = ( None, 0 )
  return self


def divide(self, *args, **kwargs):
  print('in divide', self, self.data)
  (data, samples) = self.operands[0]
  data = data / samples
  self.data = (data, 1)
  print('divide result', self.data)
  return self


def roi(self, value, *args, **kwargs):
  print('in roi(' + str(value) + ')', self)
  string = str(value[0]) + ':' + str(value[1]) + ',' + str(value[2]) + ':' + str(value[3])
  expression = 'self.operands[0][' + string + '].copy()'
  self.data = eval(expression)
  print('roi result', self.data)
  return self
