import psana
import typing
from Detector import PyDetector
from .detector import register_env_interface
from .utils import export, Extender


__all__ = []


EPICS_TO_PYTHON = {
    'DBR_STRING': str,
    'DBR_SHORT': int,
    'DBR_FLOAT': float,
    'DBR_ENUM': int,
    'DBR_CHAR': int,
    'DBR_LONG': int,
    'DBR_DOUBLE': float,
    'DBR_STS_STRING': str,
    'DBR_STS_SHORT': int,
    'DBR_STS_FLOAT': float,
    'DBR_STS_ENUM': int,
    'DBR_STS_CHAR': int,
    'DBR_STS_LONG': int,
    'DBR_STS_DOUBLE': float,
    'DBR_TIME_STRING': str,
    'DBR_TIME_INT': int,
    'DBR_TIME_SHORT': int,
    'DBR_TIME_FLOAT': float,
    'DBR_TIME_ENUM': int,
    'DBR_TIME_CHAR': int,
    'DBR_TIME_LONG': int,
    'DBR_TIME_DOUBLE': float,
    'DBR_GR_STRING': str,
    'DBR_GR_SHORT': int,
    'DBR_GR_FLOAT': float,
    'DBR_GR_ENUM': int,
    'DBR_GR_CHAR': int,
    'DBR_GR_LONG': int,
    'DBR_GR_DOUBLE': float,
    'DBR_CTRL_STRING': str,
    'DBR_CTRL_SHORT': int,
    'DBR_CTRL_FLOAT': float,
    'DBR_CTRL_ENUM': int,
    'DBR_CTRL_CHAR': int,
    'DBR_CTRL_LONG': int,
    'DBR_CTRL_DOUBLE': float,
}


def lookup_epicstype(src, env):
    epics_store = env.epicsStore()
    if epics_store is not None:
        info = epics_store.getPV(src)
        if info is not None:
            if info.numElements() > 1:
                return amitypes.Array1D
            else:
                return EPICS_TO_PYTHON.get(info.dbr().DBR_TYPE_ID.name)


@export
class EpicsDetector(Extender):
    def __init__(self, src, env):
        super().__init__(psana.Detector(src))
        self.src = src
        self.env = env
        self.dtype = lookup_epicstype(src, env)
        self._dettype = __class__.__name__

    def __call__(self, evt=None):
        return self._base(evt)


register_env_interface(PyDetector.EpicsDetector, EpicsDetector)
