#
# globalCollector3.py
#

import AMI_server as AMI

print('read work graph')
graph = AMI.workerGraph()
graph._receiveLocalCollectorData('localCollector3.dat')

result = graph._doGlobalCollector()
print('globalCollector3 result is', result)

graph._transmitGlobalCollectorData('globalCollector3.dat')


