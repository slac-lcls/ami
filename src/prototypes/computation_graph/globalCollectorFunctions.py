#
# globalCollectorFunctions
#

import AMI_common as AMI
import numpy

def mean(self, *args):
  print('in mean globalCollector', self.data, self.operand)
  (data, samples) = self.data
  if data is None:
    (data, samples) = self.operand
  for arg in args:
    (data1, samples1) = arg.data
    if data is None:
      data = data1
      samples = samples1
    else:
      data = data + data1
      samples = samples + samples1
  self.data = (data / samples, samples)
  print(self.data)
  return self

def mean_(self):
  print("in mean_ globalCollector reset", self)
  self.data = ( None, 0 )
  return self
