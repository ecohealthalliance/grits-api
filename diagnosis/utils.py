def group_by(group_fun, collection):
    out = {}
    if isinstance(group_fun, basestring):
        prop = group_fun
        group_fun = lambda k: k[prop]
    for item in collection:
        group_key = group_fun(item)
        out[group_key] = out.get(group_key, []) + [item]
    return out
    
def flatten(li, depth=-1):
    for subli in li:
        if isinstance(subli, (list, set, tuple)) and depth != 0:
            for it in flatten(subli, depth - 1):
                yield it
        else:
            yield subli
