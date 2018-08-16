# user clicks, selects function and inputs (from store and raw data)
# generates python code of function calls and if-statements with no
# indenting.  generated python is exec'd by worker/collector.
# functions return dicts that are added to the store.  namespacing in
# the store is important: this example uses function/store names.

# to do: example of "reduce"

def user_click(exec_file,input,alg):
    exec_file.write('tmp='+alg+'("'+input+'",store)'+'\n')
    exec_file.write('store.update(tmp)'+'\n')

def user_click_if(exec_file,condition,exec_file_if):
    fname = exec_file_if.name
    exec_file.write('if '+condition+': '+'exec(open("'+exec_file_if.name+'").read())'+'\n')

# list of values in worker.py store. client needs to dynamically query this
dets = ['cspad','cspad_roi','cspad_roi_valsum','store["lason"]']
# list of algs in package.py
algs = ['roi','valsum']

exec_file_names = ['exec_file.py','exec_file_if.py']
exec_file = [open(name,'w') for name in exec_file_names]
for f in exec_file: f.write('from ami_algs import *'+'\n')

user_click(exec_file[0],dets[0],algs[0]) # cspad roi
user_click(exec_file[0],dets[1],algs[1]) # cspad_roi valsum
user_click_if(exec_file[0],dets[3],exec_file[1])
user_click(exec_file[1],dets[2],algs[0]) # cspad_roi_valsum roi, if lason

exec_file[0].write('import pprint; pp=pprint.PrettyPrinter(); pp.pprint(store)')
for f in exec_file: f.close()

# notes

# need to add topological sort of operation dependencies, like
# https://www.geeksforgeeks.org/topological-sorting/
# trickiness:  the topological sorting can split "if" statements

# topological sorting would also help deal with changes to the graph,
# e.g. remove all values in store that depend on this line

# legion tracks data dependencies, so they must be expert at topological sort

# changes to the graph are complex with downstream global store ("redis")

# specifying the reduce operation?  (pickn, sum, gather, none)
# - each operation specifies collection strategy and exec-code for collector
#   - worker would send sum
#   - collector would see this as a collection strategy
#   - exec'd code would give a chance for calculations to be done on collector
