__version__ = '2.0.0'


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
