#
# globalCollector2.py
#

import AMI_server as AMI

print('read work graph')
graph1 = AMI.workerGraph()
graph1._receiveLocalCollectorData('localCollector2a.dat')

graph2 = AMI.workerGraph()
graph2._receiveLocalCollectorData('localCollector2b.dat')

result = graph1._doGlobalCollector(graph2)
print('globalCollector result is', result)

graph1._transmitGlobalCollectorData('globalCollector2.dat')


