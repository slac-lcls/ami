#
# globalCollectorFunctions
#

import AMI_common as AMI
import numpy

def mean(self, *args):
  print('in mean globalCollector', self.data, self.operands)
  (data, samples) = self.data
  for operand in self.operands:
    (data1, samples1) = operand
    if data is None:
      data = data1
      samples = samples1
    else:
      data = data + data1
      samples = samples + samples1
  self.data = (data / samples, 1)
  print(self.data)
  if len(args) > 0:
    if self.data[1] >= args[0]:
      return self
  else:
    return self

def mean_(self, *args):
  print("in mean_ globalCollector reset", self)
  self.data = ( None, 0 )
  return self
