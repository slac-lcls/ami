#
# worker1a.py
#

import AMI_server as AMI

print('read work graph')
graph = AMI.workerGraph()

result = graph._doWorker()
result = graph._doWorker()
print('worker 1a result is', result)

graph._transmitWorkerData('worker1a.dat')
