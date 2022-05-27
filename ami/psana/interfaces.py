import typing
import psana
import amitypes
from Detector import DetectorTypes
from .detector import Detector, DdlHelper, DetectorMeta, DdlHelperMeta, \
        MultiPanelHelper
from .utils import export


__all__ = []


@export
class MultiPanelDetector(Detector,
                         metaclass=DetectorMeta,
                         detcls=MultiPanelHelper,
                         annotations={'raw': amitypes.Array3d, 'calib': amitypes.Array3d, 'image': amitypes.Array2d},
                         configs={'config': [psana.CsPad.Config,
                                             psana.CsPad2x2.Config,
                                             psana.Epix.Config10ka2M,
                                             psana.Epix.Config10kaQuad,
                                             psana.Jungfrau.Config,
                                             psana.Uxi.Config]}):
    pass


@export
class AreaDetector(Detector,
                   metaclass=DetectorMeta,
                   detcls=DetectorTypes.AreaDetector,
                   annotations={'raw': amitypes.Array2d, 'calib': amitypes.Array2d, 'image': amitypes.Array2d},
                   configs={'config': [psana.Opal1k.Config,
                                       psana.Archon.Config,
                                       psana.Andor.Config,
                                       psana.Epix.Config100a,
                                       psana.Epix.Config10ka,
                                       psana.FCCD.FccdConfig,
                                       psana.Fli.Config,
                                       psana.PNCCD.Config,
                                       psana.Orca.Config,
                                       psana.Pimax.Config,
                                       psana.Pixis.Config,
                                       psana.Princeton.Config,
                                       psana.Pulnix.TM6740Config,
                                       psana.Quartz.Config,
                                       psana.Rayonix.Config,
                                       psana.Timepix.Config,
                                       psana.Vimba.AlviumConfig,
                                       psana.iStar.Config,
                                       psana.Zyla.Config]}):
    pass


@export
class EvrDetector(Detector,
                  metaclass=DetectorMeta,
                  detcls=DetectorTypes.EvrDetector,
                  annotations={'eventCodes': typing.List[int]},
                  configs={'config': [psana.EvrData.Config]}):
    pass


@export
class IpimbDetector(Detector,
                    metaclass=DetectorMeta,
                    detcls=None,
                    annotations=None,
                    fexcls=DetectorTypes.IpimbDetector,
                    fexannotations={'channel': amitypes.MultiChannelFloat, 'xpos': float, 'ypos': float, 'sum': float},
                    configs={'config': [psana.Ipimb.Config], 'fexconfig': [psana.Lusi.IpmFexConfig]}):
    def __init__(self, src, env):
        super().__init__(src, env)

    @property
    def nchannels(self):
        return self.fexconfig.NCHANNELS


class RawUsdUsbDetector(DdlHelper,
                        metaclass=DdlHelperMeta,
                        methods=psana.UsdUsb.Data):
    pass


@export
class UsdUsbDetector(Detector,
                     metaclass=DetectorMeta,
                     detcls=RawUsdUsbDetector,
                     annotations=psana.UsdUsb.Data,
                     overrides={'encoder_count': amitypes.MultiChannelInt,
                                'analog_in': amitypes.MultiChannelInt,
                                'status': amitypes.MultiChannelInt},
                     fexcls=DetectorTypes.UsdUsbDetector,
                     fexannotations={'values': amitypes.MultiChannelFloat},
                     configs={'config': [psana.UsdUsb.Config], 'fexconfig': [psana.UsdUsb.FexConfig]}):
    def __init__(self, src, env):
        super().__init__(src, env)

    @property
    def calibconst(self):
        return {'descriptions': self.fex.descriptions()}

    @property
    def nchannels(self):
        return self.config.NCHANNELS


@export
class OceanDetector(Detector,
                    metaclass=DetectorMeta,
                    detcls=DetectorTypes.OceanDetector,
                    annotations={'intensity': amitypes.Array1d, 'wavelength': amitypes.Array1d},
                    configs={'config': [psana.OceanOptics.Config]}):
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
