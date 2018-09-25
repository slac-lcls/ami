#
# client1
#

import graphkit
import numpy
import dill
import operators as o

workerGraph = graphkit.compose(name='workerGraph1')(
    graphkit.operation(name='roi_op', needs=['xppcspad', 'roiLambda'], provides=['reducedImage'])(o.roi),
    graphkit.operation(name='roi_op2', needs=['imageSumIn', 'roiLambda'], provides=['reducedImageSumIn'])(o.roi),
    graphkit.operation(name='sum_op', needs=['reducedImage', 'reducedImageSumIn'], provides=['reducedImageSumOut'])(o.sum),
    graphkit.operation(name='counter_op', needs=['counterIn'], provides=['counterOut'])(o.increment),
    graphkit.operation(name='timestamp_passthrough', needs=['timestampIn'], provides=['timestampOut'])(o.identity)
)

dill.dump(workerGraph, open('workerGraph1.dat', 'wb'))



localCollectorGraph = graphkit.compose(name='localCollectorGraph1')(
    graphkit.operation(name='sum_op', needs=['imageSumsIn'], provides=['imageSumsSumOut'])(o.sumMultiple),
    graphkit.operation(name='timestamp_passthrough', needs=['timestampIn'], provides=['timestampOut'])(o.identity)
)

dill.dump(localCollectorGraph, open('localCollectorGraph1.dat', 'wb'))


globalCollectorGraph = graphkit.compose(name='globalCollectorGraph1')(
    graphkit.operation(name='sum_op', needs=['imageSumsIn'], provides=['imageSumsSumOut'])(o.sumMultiple),
    graphkit.operation(name='timestamp_passthrough', needs=['timestampIn'], provides=['timestampOut'])(o.identity)
)

dill.dump(globalCollectorGraph, open('globalCollectorGraph1.dat', 'wb'))
