import numpy as np
# need a store for raw and computed values for "posted" values
store = {}

# store gets the input data from the start (not namespaced)
store['cspad']=np.random.rand(4,4)
store['lason']= True

# simulate analysis of 2 events
exec(open('./exec_file.py').read())
exec(open('./exec_file.py').read())
