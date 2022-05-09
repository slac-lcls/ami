import psana
import typing
import amitypes
from functools import partialmethod
from Detector import DetectorTypes, PyDetector
from .utils import export


__all__ = []


RAW_INTERFACES = {}
FEX_INTERFACES = {}
PSANA_DETS = (DetectorTypes.DdlDetector, DetectorTypes.WFDetector, DetectorTypes.AreaDetector)


@export
class DdlHelperMeta(type):
    def __new__(cls, clsname, bases, attrs, methods, config=None):
        func = None
        for base in bases:
            if hasattr(base, 'get'):
                func = getattr(base, 'get')
                break
        if func is not None:
            for name in methods:
                attrs[name] = partialmethod(getattr(base, 'get'), name)
        attrs['_config'] = config
        return super().__new__(cls, clsname, bases, attrs)

    def __init__(cls, clsname, bases, attrs, methods, config=None):
        super().__init__(clsname, bases, attrs)


@export
class DdlHelper:
    def __init__(self, src, env):
        self.src = src
        self.env = env
        self.det = psana.Detector(src)

    @property
    def config(self):
        if self._configs is not None:
            cfgst = self.env.configStore()
            for cfgmod in self._configs:
                for cfgcls in cfgmod.Config:
                    cfg = cfgst.get(cfgcls, psana.Source(self.src))
                    if cfg is not None:
                        return cfg

    def get(self, attr, evt):
        return  getattr(self.det.get(evt), attr)()


@export
class DetectorMeta(type):
    def __new__(cls, clsname, bases, attrs, detcls, annotations, config=None, fexcls=None, fexannotations=None):
        attrs['detcls'] = detcls
        attrs['fexcls'] = fexcls
        attrs['_configs'] = config
        attrs['_dettype'] = clsname
        attrs['_detinfo'] = {}
        newcls = super().__new__(cls, clsname, bases, attrs)
        RAW_INTERFACES[detcls] = newcls
        if fexcls is not None:
            FEX_INTERFACES[fexcls] = newcls
        return newcls

    def __init__(cls, clsname, bases, attrs, detcls, annotations, config=None, fexcls=None, fexannotations=None):
        super().__init__(clsname, bases, attrs)
        if detcls is not None:
            cls._detinfo['raw'] = []
            for name, rtype in annotations.items():
                cls._detinfo['raw'].append(name)
                func = getattr(detcls, name)
                func.__annotations__ = {'return': rtype}
        if fexcls is not None:
            cls._detinfo['fex'] = []
            for name, rtype in fexannotations.items():
                cls._detinfo['fex'].append(name)
                func = getattr(fexcls, name)
                func.__annotations__ = {'return': rtype}


@export
class Detector:
    def __init__(self, src, env):
        self.src = src
        self.env = env
        if self.detcls is not None:
            if issubclass(self.detcls, PSANA_DETS):
                self.raw = psana.Detector(src)
            else:
                self.raw = self.detcls(src, env)
        if self.fexcls is not None:
            if self.fexcls is self.detcls:
                self.fex = self.raw
            else:
                if issubclass(self.fexcls, PSANA_DETS):
                    self.fex = psana.Detector(src)
                else:
                    self.fex = self.fexcls(src, env)

    @classmethod
    def _named_detinfo(cls, name):
        return {(name, key): value for key, value in cls._detinfo.items()}

    @property
    def config(self):
        if self._configs is not None:
            cfgst = self.env.configStore()
            for cfgmod in self._configs:
                for cfgcls in cfgmod.Config:
                    cfg = cfgst.get(cfgcls, psana.Source(self.src))
                    if cfg is not None:
                        return cfg

    @property
    def detinfo(self):
        return self._named_detinfo(self.src)


def lookup_dettype(src, env, *args, **kwargs):
    src = PyDetector.map_alias_to_source(src, env)
    return PyDetector.dettype(src, env, *args, **kwargs)


def encode(src):
    return src.replace(":", "|")


def decode(name):
    return name.replace("|", ":")


@export
def detector_factory(name, env, *args, **kwargs):
    src = decode(name)
    dettype = lookup_dettype(src, env, *args, **kwargs)
    if dettype in RAW_INTERFACES:
        return RAW_INTERFACES[dettype](src, env)
    elif dettype in FEX_INTERFACES:
        return FEX_INTERFACES[dettype](src, env)


@export
def detnames_to_detinfo(detnames, env):
    detinfo = {}
    for info, alias, _ in detnames:
        src = alias if alias else info
        name = encode(src)
        dettype = lookup_dettype(src, env)
        if dettype in RAW_INTERFACES:
            detinfo.update(RAW_INTERFACES[dettype]._named_detinfo(name))
        elif dettype in FEX_INTERFACES:
            detinfo.update(FEX_INTERFACES[dettype]._named_detinfo(name))

    return detinfo
