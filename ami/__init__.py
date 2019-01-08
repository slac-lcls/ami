__version__ = '2.0.0'


class LogConfig:
    BasicFormat = '%(message)s'
    Format = '[ %(asctime)s | %(levelname)-8s] %(message)s'
    FullFormat = '[ %(asctime)s | %(name)-13s | %(levelname)-8s] %(message)s'
    Level = 'INFO'
