
import numpy

def roi(image, roiLambda):
    _roi = roiLambda(image)
    string = str(_roi[0]) + ':' + str(_roi[1]) + ',' + str(_roi[2]) + ':' + str(_roi[3])
    expression = 'image[' + string + '].copy()'
    return eval(expression)

def sum(x, y):
    return x + y

def sumMultiple(x):
    accumulator = x[0]
    for x_ in x[1:]: accumulator = accumulator + x_
    return accumulator

def increment(x):
    return x + 1

def divide(x, y):
    return x / y

def identity(x):
    return x
