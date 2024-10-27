import psana
import amitypes
from Detector import PyDetector
from .detector import register_raw_interface
from .utils import get_methods, export, Extender


__all__ = []


class ScanDetectorHelper(Extender):
    def __init__(self, src):
        super().__init__(psana.Detector(src))

    @property
    def config(self):
        return self._base()

    @property
    def ncontrols(self) -> int:
        return self.config.npvControls()

    @property
    def control_names(self) -> list[str]:
        names = []
        for ctrl in self.controls():
            names.append(ctrl.name())
        return names

    def controls(self, evt=None) -> amitypes.ScanControls:
        return self.config.pvControls()

    @property
    def nmonitors(self) -> int:
        return self.config.npvMonitors()

    @property
    def monitor_names(self) -> list[str]:
        names = []
        for ctrl in self.monitors():
            names.append(ctrl.name())
        return names

    def monitors(self, evt=None) -> amitypes.ScanMonitors:
        return self.config.pvMonitors()

    @property
    def nlabels(self) -> int:
        return self.config.npvLabels()

    @property
    def label_names(self) -> list[str]:
        names = []
        for ctrl in self.labels():
            names.append(ctrl.name())
        return names

    def labels(self, evt=None) -> amitypes.ScanLabels:
        return self.config.pvLabels()


@export
class ScanDetector:
    def __init__(self, src, env):
        self.src = src
        self.env = env
        self.raw = ScanDetectorHelper(src)
        self._dettype = __class__.__name__
        self._detinfo = {'raw': [name for name, _ in get_methods(self.raw)]}

    @classmethod
    def _named_detinfo(cls, name):
        det = cls(name, None)
        return {(name, key): value for key, value in det._detinfo.items()}

    @property
    def detinfo(self):
        return self._named_detinfo(self.src)


register_raw_interface(PyDetector.ControlDataDetector, ScanDetector)
