#
# worker1
#

import graphkit
import numpy
import dill

workerGraph = dill.load(open('workergraph.dat', 'rb'))

workerInput1 = {
    'xppcspad' : numpy.ones((1024, 1024)) * 3,
    'roiLambda' : lambda image : [ (int(image.shape[0] * .1)), (int(image.shape[0] * .9)), (int(image.shape[1] * .1)), (int(image.shape[1]* .9)) ],
    'imageSumIn' : numpy.zeros((1024, 1024)),
    'counterIn' : 0,
    'timestampIn' : 25
}

out1 = workerGraph(workerInput1, outputs=['reducedImageSumOut', 'counterOut', 'timestampOut'])
print(out1)
print('--------------------------------------')

workerInput2 = {}
workerInput2['xppcspad'] = numpy.ones((1024, 1024)) * 7
workerInput2['roiLambda'] = workerInput1['roiLambda']
workerInput2['reducedImageSumIn'] = out1['reducedImageSumOut']
workerInput2['counterIn'] = out1['counterOut']
workerInput2['timestampIn'] = out1['timestampOut'] + 1

out2 = workerGraph(workerInput2, outputs=['reducedImageSumOut', 'counterOut', 'timestampOut'])
print(out2)
print('--------------------------------------')
