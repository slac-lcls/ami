import typing
import psana
import amitypes
from Detector import DetectorTypes
from .detector import *
from .utils import export


__all__ = []


@export
class AreaDetector(Detector,
                   metaclass=DetectorMeta,
                   detcls=DetectorTypes.AreaDetector,
                   annotations={'raw': amitypes.Array3d, 'calib': amitypes.Array3d, 'image': amitypes.Array2d}):
    pass


@export
class EvrDetector(Detector,
                  metaclass=DetectorMeta,
                  detcls=DetectorTypes.EvrDetector,
                  annotations={'eventCodes': typing.List[int]}):
    pass


@export
class IpimbDetector(Detector,
                    metaclass=DetectorMeta,
                    detcls=None,
                    annotations=None,
                    fexcls=DetectorTypes.IpimbDetector,
                    fexannotations={'channel': amitypes.Array1d, 'xpos': float, 'ypos': float, 'sum': float}):
    pass


class RawUsdUsbDetector(DdlHelper,
                        metaclass=DdlHelperMeta,
                        methods=['encoder_count']):
    pass


@export
class UsdUsbDetector(Detector,
                     metaclass=DetectorMeta,
                     detcls=RawUsdUsbDetector,
                     annotations={'encoder_count': amitypes.Array1d},
                     fexcls=DetectorTypes.UsdUsbDetector,
                     fexannotations={'values': amitypes.Array1d}):
    def __init__(self, src, env):
        super().__init__(src, env)
        self.descriptions = self.fex.descriptions


@export
class OceanDetector(Detector,
                    metaclass=DetectorMeta,
                    detcls=DetectorTypes.OceanDetector,
                    annotations={'intensity': amitypes.Array1d, 'wavelength': amitypes.Array1d}):
    pass


@export
class TDCDetector(Detector,
                  metaclass=DetectorMeta,
                  detcls=DetectorTypes.TDCDetector,
                  annotations={'times': typing.List[amitypes.Array1d], 'overflows': typing.List[amitypes.Array1d]}):
    pass


@export
class WFDetector(Detector,
                 metaclass=DetectorMeta,
                 detcls=DetectorTypes.WFDetector,
                 annotations={'wftime': amitypes.AcqirisTimes, 'waveform': amitypes.AcqirisWaveforms},
                 config=[psana.Acqiris, psana.Imp]):
    def __init__(self, src, env):
        super().__init__(src, env)

    @property
    def nchannels(self):
        return self.config.nbrChannels()


@export
class GenericWFDetector(Detector,
                        metaclass=DetectorMeta,
                        detcls=DetectorTypes.GenericWFDetector,
                        annotations={'wftime': amitypes.GenericWfTimes, 'raw': amitypes.GenericWfWaveforms},
                        config=[psana.Generic1D]):
    def __init__(self, src, env):
        super().__init__(src, env)

    @property
    def nchannels(self):
        return self.config.NChannels()

