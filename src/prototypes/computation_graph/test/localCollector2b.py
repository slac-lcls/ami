#
# localCollector2b.py
#

import AMI_server as AMI

print('read work graph')
graph = AMI.workerGraph()
graph._receiveWorkerData('worker1c.dat')


result = graph._doLocalCollector()
print('localCollector 2b result is', result)

graph._transmitLocalCollectorData('localCollector2b.dat')



