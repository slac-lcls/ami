#
# worker1b.py
#

import AMI_server as AMI

print('read work graph')
graph = AMI.workerGraph()

result = graph._doWorker()
result = graph._doWorker()
result = graph._doWorker()
print('worker 1b result is', result)

graph._transmitWorkerData('worker1b.dat')

