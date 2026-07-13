from .. import config


def get():
    if config.IS_MAC:
        from . import mlx_backend as b
    else:
        from . import torch_backend as b
    return b
