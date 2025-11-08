def noop(*args, **kwargs):
    return None


def echo(*args, **kwargs):
    return {"args": args, "kwargs": kwargs}
