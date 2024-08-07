def get_version():
    try:
        # python > 3.7
        import importlib.metadata as importlib_metadata
    except ImportError:
        # backport to python 3.7
        import importlib_metadata
    try:
        return importlib_metadata.version(__name__)
    except importlib_metadata.PackageNotFoundError:
        # package is not installed
        pass


def psana_available():
    try:
        import psana  # noqa: F401
        return True
    except ImportError:
        return False


def psana_uses_epics_epoch():
    try:
        import psana  # noqa: F401
        return not hasattr(psana, '_psana')
    except ImportError:
        return False


def p4p_available():
    try:
        import p4p  # noqa: F401
        return True
    except (ImportError, RuntimeError):
        return False


def p4p_get_version():
    try:
        # python > 3.7
        import importlib.metadata as importlib_metadata
    except ImportError:
        # backport to python 3.7
        import importlib_metadata
    try:
        return importlib_metadata.version('p4p')
    except importlib_metadata.PackageNotFoundError:
        # package is not installed
        pass


class p4pConfig:
    Version = p4p_get_version()
    SupportsTimestamps = p4p_get_version() >= '4.0.0' if p4p_available() else False


class LogConfig:
    BasicFormat = '%(message)s'
    Format = '[ %(asctime)s | %(levelname)-8s] %(message)s'
    FullFormat = '[ %(asctime)s | %(name)-13s | %(levelname)-8s] %(message)s'
    Level = 'INFO'

    @staticmethod
    def get_package_name(name):
        return '.'.join(name.split('.')[:-1])


class Defaults:
    Host = 'localhost'
    GraphName = 'graph'
    SourceType = 'psana' if psana_available() else 'random'
    SourceConfig = {
        "interval": 0.0,
        "init_time": 0.5,
        "bound": 12,
        "repeat": True,
        "files": "data.xtc2",
        "nevents": 500,
        "config": {
            "delta_t": {"dtype": "Scalar", "range": [0, 10], "integer": True},
            "cspad": {"dtype": "Image", "pedestal": 5, "width": 1, "shape": [512, 512]},
            "laser": {"dtype": "Scalar", "range": [0, 2], "integer": True},
        },
    }


__version__ = get_version()
