__version__ = '2.0.0'


def psana_available():
    try:
        import psana  # noqa: F401
        return True
    except ImportError:
        return False


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
