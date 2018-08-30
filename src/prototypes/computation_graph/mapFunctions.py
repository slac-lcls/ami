#
# mapFunctions.py
#

## these functions cannot call each other


import AMI_common as AMI
import numpy

def sum(self):
  print('in sum()')
  dataObject = AMI.getDataObject(self)
  if self.data is None:
    self.data = dataObject.data
  else:
    self.data = numpy.add(self.data, dataObject.data)
  return { 'sum' : self.data }


def roi(self, value):
  print('in roi(' + str(value) + ')')
  string = str(value[0]) + ':' + str(value[1]) + ',' + str(value[2]) + ':' + str(value[3])
  dataObject = AMI.getDataObject(self)
  print('getDataObject returned', dataObject)
  AMI.printGraphNode(dataObject, 1)
  if dataObject.data is not None:
    self.data = eval('dataObject.data[' + string + '].copy')
  return { 'roi' : self }


def std(self):
  dataObject = AMI.getDataObject(self)
  return { 'std' : np.std(dataObject.data) }


# mean map is the same as sum
# mean reduce is the division

def mean(self):
  print('in mean()')
  dataObject = AMI.getDataObject(self)
  if self.data is None:
    self.data = dataObject.data
  else:
    self.data = numpy.add(self.data, dataObject.data)
  return { 'mean' : self.data }


def calibrate(self, image):
  result = image # call calibration code here
  return { 'calibrate' : result }


def peakfind(self, image):
  result = [ [0, 0] ] # call peakfinder here
  return { 'peakfind' : result }

