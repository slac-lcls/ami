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
                        methods=psana.UsdUsb.Data):
    pass


@export
class UsdUsbDetector(Detector,
                     metaclass=DetectorMeta,
                     detcls=RawUsdUsbDetector,
                     annotations=psana.UsdUsb.Data,
                     fexcls=DetectorTypes.UsdUsbDetector,
                     fexannotations={'values': amitypes.MultiChannelFloat},
                     configs={'config': [psana.UsdUsb.Config], 'fexconfig': [psana.UsdUsb.FexConfig]}):
    def __init__(self, src, env):
        super().__init__(src, env)
        self.descriptions = self.fex.descriptions

    @property
    def nchannels(self):
        return self.config.NCHANNELS


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
                  annotations={'times': typing.List[amitypes.Array1d], 'overflows': typing.List[amitypes.Array1d]},
                  configs={'config': [psana.Acqiris.TdcConfig]}):
    def __init__(self, src, env):
        super().__init__(src, env)

    @property
    def nchannels(self):
        nchan = 0
        for chan in self.config.channels():
            if chan.channel() > 0:
                nchan += 1
        return nchan


@export
class WFDetector(Detector,
                 metaclass=DetectorMeta,
                 detcls=DetectorTypes.WFDetector,
                 annotations={'wftime': amitypes.AcqirisTimes, 'waveform': amitypes.AcqirisWaveforms},
                 configs={'config': [psana.Acqiris.Config, psana.Imp.Config]}):
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
                        configs={'config': [psana.Generic1D.Config]}):
    def __init__(self, src, env):
        super().__init__(src, env)

    @property
    def nchannels(self):
        return self.config.NChannels()

