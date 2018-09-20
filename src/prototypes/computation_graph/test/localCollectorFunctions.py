#
# localCollectorFunctions.py
#

import AMI_common as AMI
import numpy


def mean(self):
  print('in mean localCollector', self.data, self.operands)
  (data, samples) = self.data
  for operand in self.operands:
    (data1, samples1) = operand
    if data is None:
      data = data1
      samples = samples1
    else:
      data = data + data1
      samples = samples + samples1
  self.data = (data, samples)
  print(self.data)
  return self

def mean_(self):
  print("in mean_ localCollector reset", self)
  self.data = ( None, 0 )
  return self
