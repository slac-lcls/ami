#
# worker2.py
#

import AMI_server as AMI

print('read work graph')
graph = AMI.workerGraph()

result = graph._doWorker()
result = graph._doWorker()
result = graph._doWorker()
print('worker 2 result is', result)

graph._transmitWorkerData('worker2.dat')

