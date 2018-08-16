# proposal
# - user clicks, selects function and inputs (from store and raw data)
#   produces python code of function calls and if-statements with no
#   indenting. code is exec'd by worker/collector.

# worker code
# import ...
# tmp_dict = function1(input1, ...)
# store.update(tmp_dict)
# if (las_on) exec('first_if_file.py',store)
# tmp_dict = function2(input2, ...)
# store.update(tmp_dict)
# send_to_redis(store)

# to do: example of "if"/"reduce"

def user_click(exec_file,input,alg):
    exec_file.write('tmp='+alg+'("'+input+'",store)'+'\n')
    exec_file.write('store.update(tmp)'+'\n')

# list of values in worker.py store. client needs to dynamically query this
dets = ['cspad','cspad_roi','cspad_roi_valsum']
# list of algs in package.py
algs = ['roi','valsum']

exec_file = open('exec_file.py','w')
user_click(exec_file,dets[0],algs[0]) # cspad roi
user_click(exec_file,dets[1],algs[1]) # cspad_roi valsum
user_click(exec_file,dets[2],algs[0]) # cspad_roi_valsum roi

exec_file.write('import pprint; pp=pprint.PrettyPrinter(); pp.pprint(store)')
exec_file.close()

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

#def filter(exec_file,input,exec_file_branch):
#    exec_file.write('if '+input+': '+'exec(open(exec_file_branch).read())'+'\n')
#    exec_file.write('store.update(tmp)'+'\n')

#exec_file = open('exec_file_lason.py','w')
#exec_file = open('exec_file_lasoff.py','w')
#filter(exec_file,'not '+dets[1])
