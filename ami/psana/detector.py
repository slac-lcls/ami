import psana
from Detector import DetectorTypes, PyDetector
from .utils import export, parse_cls, parse_methods, parse_annotations, \
        make_method, make_config, Extender


__all__ = []


RAW_INTERFACES = {}
FEX_INTERFACES = {}
BLD_INTERFACES = {}
MULTI_PANEL_DETS = {'CsPad2x2', 'CsPad', 'Jungfrau', 'Epix10ka2M', 'Epix10kaQuad', 'Uxi'}
PSANA_DETS = (DetectorTypes.DdlDetector, DetectorTypes.WFDetector, DetectorTypes.AreaDetector)


@export
class MultiPanelHelper(Extender):
    def __init__(self, src, env):
        super().__init__(psana.Detector(src))
        self.src = src
        self.env = env

    def raw(self, evt):
        return self._base.raw(evt)

    def calib(self, evt, **kwargs):
        return self._base.calib(evt, **kwargs)

    def image(self, evt, **kwargs):
        return self._base.image(evt, **kwargs)


@export
class DdlHelperMeta(type):
    def __new__(cls, clsname, bases, attrs, methods):
        func = None
        for base in bases:
            if hasattr(base, 'get'):
                func = getattr(base, 'get')
                break
        if func is not None:
            for name in parse_methods(methods):
                attrs[name] = make_method(name, func)
        return super().__new__(cls, clsname, bases, attrs)

    def __init__(cls, clsname, bases, attrs, methods):
        super().__init__(clsname, bases, attrs)


@export
class DdlHelper:
    def __init__(self, src, env):
        self.src = src
        self.env = env
        self.det = psana.Detector(src)

    def get(self, attr, evt):
        data = self.det.get(evt)
        if data is not None:
            try:
                return getattr(data, attr)()
            except AttributeError:
                pass


@export
class BldMeta(type):
    def __new__(cls,
                clsname,
                bases,
                attrs,
                detcls,
                sources,
                annotations=None,
                overrides=None,
                configs=None):
        attrs['detcls'] = parse_cls(detcls)
        attrs['fexcls'] = None
        attrs['_dettype'] = clsname
        attrs['_detinfo'] = {}
        if configs is not None:
            for name, cfgmods in configs.items():
                attrs[name] = make_config(cfgmods)

        return super().__new__(cls, clsname, bases, attrs)

    def __init__(cls,
                 clsname,
                 bases,
                 attrs,
                 detcls,
                 sources,
                 annotations=None,
                 overrides=None,
                 configs=None):
        super().__init__(clsname, bases, attrs)
        cls._detinfo['raw'] = []
        for name, rtype in parse_annotations(annotations,
                                             overrides).items():
            cls._detinfo['raw'].append(name)
            func = getattr(cls.detcls, name)
            func.__annotations__ = {'return': rtype}
        for src in sources:
            BLD_INTERFACES[src] = cls


@export
class DetectorMeta(type):
    def __new__(cls,
                clsname,
                bases,
                attrs,
                detcls,
                annotations=None,
                overrides=None,
                configs=None,
                fexcls=None,
                fexannotations=None,
                fexoverrides=None):
        attrs['detcls'] = parse_cls(detcls)
        attrs['fexcls'] = parse_cls(fexcls)
        attrs['_dettype'] = clsname
        attrs['_detinfo'] = {}
        if configs is not None:
            for name, cfgmods in configs.items():
                attrs[name] = make_config(cfgmods)

        return super().__new__(cls, clsname, bases, attrs)

    def __init__(cls,
                 clsname,
                 bases,
                 attrs,
                 detcls,
                 annotations,
                 overrides=None,
                 configs=None,
                 fexcls=None,
                 fexannotations=None,
                 fexoverrides=None):
        super().__init__(clsname, bases, attrs)
        if cls.detcls is not None:
            cls._detinfo['raw'] = []
            for name, rtype in parse_annotations(annotations,
                                                 overrides).items():
                cls._detinfo['raw'].append(name)
                func = getattr(cls.detcls, name)
                func.__annotations__ = {'return': rtype}
            RAW_INTERFACES[cls.detcls] = cls
        if cls.fexcls is not None:
            cls._detinfo['fex'] = []
            for name, rtype in parse_annotations(fexannotations,
                                                 fexoverrides).items():
                cls._detinfo['fex'].append(name)
                func = getattr(cls.fexcls, name)
                func.__annotations__ = {'return': rtype}
            FEX_INTERFACES[cls.fexcls] = cls


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
    def detinfo(self):
        return self._named_detinfo(self.src)


def is_multi_panel(src):
    return PyDetector.DetInfo(src).dev in MULTI_PANEL_DETS


def lookup_dettype(src, env, *args, **kwargs):
    src = PyDetector.map_alias_to_source(src, env)
    dettype = PyDetector.dettype(src, env, *args, **kwargs)
    if dettype is DetectorTypes.AreaDetector and is_multi_panel(src):
        dettype = MultiPanelHelper
    return dettype


def encode(src):
    return src.replace(":", "|")


def decode(name):
    return name.replace("|", ":")


@export
def detector_factory(name, env, *args, **kwargs):
    src = decode(name)
    dettype = lookup_dettype(src, env, *args, **kwargs)
    if dettype is DetectorTypes.DdlDetector and src in BLD_INTERFACES:
        return BLD_INTERFACES[src](src, env)
    elif dettype in RAW_INTERFACES:
        return RAW_INTERFACES[dettype](src, env)
    elif dettype in FEX_INTERFACES:
        return FEX_INTERFACES[dettype](src, env)


@export
def detnames_to_detinfo(detnames, env):
    detinfo = {}
    for info, alias, _ in detnames:
        src = alias if alias else info
        name = encode(src)
        dettype = lookup_dettype(src, env, accept_missing=True)
        if dettype is DetectorTypes.DdlDetector and src in BLD_INTERFACES:
            detinfo.update(BLD_INTERFACES[src]._named_detinfo(name))
        elif dettype in RAW_INTERFACES:
            detinfo.update(RAW_INTERFACES[dettype]._named_detinfo(name))
        elif dettype in FEX_INTERFACES:
            detinfo.update(FEX_INTERFACES[dettype]._named_detinfo(name))

    return detinfo
