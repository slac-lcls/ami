#
# worker1c.py
#

import AMI_server as AMI

print('read work graph')
graph = AMI.workerGraph()

result = graph._doWorker()
if result is not None:
  print('worker 3a result is', result)

graph._transmitWorkerData('worker1c.dat')


