#
# mapFunctions.py
#


def sum(self, x):
  if self.sum is None:
    self.sum = x
  else:
    self.sum = np.add(self.sum, x)
  return { 'sum' : self.sum }


def roi(self, value):
  return self.data[value]

def std(self, x):
  return { 'std' : np.std(x) }


def mean(self, x):
  s = self.sum(x)
  return { 'mean' : s / x.size() }


def calibrate(self, image):
  result = image # call calibration code here
  return { 'calibrate' : result }

def peakfind(self, image):
  result = [ 0, 0 ] # call peakfinder here
  return { 'peakfind' : result }

