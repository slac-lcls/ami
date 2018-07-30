#
# client
#
# Env data source, plot mean v time, normalize by, weight by
#

import AMI_client as AMI

def normalizedWeighted(x, normalize, weight):
  return float(x) / float(normalize) * float(weight)


if(True):
  data = AMI.displayResult() # get the current frame of subscribed data
  print data
  x = data['timestamp']
  y = normalizedWeighted(data['field0.mean.a0'], data['normalizeField'], data['weightField'])
  print x, y
  userObject = data['userObject0']
  userObject2 = data['userObject2']
  print userObject, userObject2
  image = data['cspad0.mean.a0']
  print image
