# wrapper to support dot-notation
# (see https://stackoverflow.com/questions/2352181/how-to-use-a-dot-to-access-members-of-dictionary)
class dotdict(dict):
    """Allows using 'dot.notation' to access dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__