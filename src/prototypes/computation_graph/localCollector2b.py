#
# localCollector2b.py
#

import AMI_server as AMI

print('read work graph')
graph = AMI.workerGraph()
graph._receiveWorkerData('worker3.dat')


result = graph._doLocalCollector()
print('localCollector 2b result is', result)

graph._transmitLocalCollectorData('localCollector2b.dat')



