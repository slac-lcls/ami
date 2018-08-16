def roi(name,store):
    return {name+'_'+roi.__name__:store[name][:2,:2]}

def valsum(name,store):
    sumname = name+'_'+valsum.__name__
    if sumname not in store:
        return {sumname:store[name]}
    else:
        return {sumname:store[sumname]+store[name]}
