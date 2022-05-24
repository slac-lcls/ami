import psana
import amitypes
from .detector import BldMeta, DdlHelperMeta, DdlHelper, Detector
from .utils import export


__all__ = []


def _get_bld_names():
    names = []
    try:
        for i in range(256):
            names.append(psana.BldInfo(i).typeName())
    except ValueError:
        pass

    return names


BLD_NAMES = _get_bld_names()
AIN_BLD_NAMES = [name for name in BLD_NAMES if "-AIN-" in name]
BEAMMON_BLD_NAMES = [name for name in BLD_NAMES if "BMMON" in name or "BEAMMON" in name or name.endswith("-DIO")]
SPEC_BLD_NAMES = [name for name in BLD_NAMES if "SPEC" in name]


class DdlEBeam(DdlHelper,
               metaclass=DdlHelperMeta,
               methods=psana.Bld.BldDataEBeam):
    pass


@export
class EBeamDetector(Detector,
                    metaclass=BldMeta,
                    detcls=DdlEBeam,
                    sources=['EBeam'],
                    annotations=psana.Bld.BldDataEBeam):
    pass


class DdlFEEGasDet(DdlHelper,
                   metaclass=DdlHelperMeta,
                   methods=psana.Bld.BldDataFEEGasDetEnergyV1):
    pass


@export
class FEEGasDetDetector(Detector,
                        metaclass=BldMeta,
                        detcls=DdlFEEGasDet,
                        sources=['FEEGasDetEnergy'],
                        annotations=psana.Bld.BldDataFEEGasDetEnergyV1):
    pass


class DdlPhaseCavity(DdlHelper,
                     metaclass=DdlHelperMeta,
                     methods=psana.Bld.BldDataPhaseCavityV1):
    pass


@export
class PhaseCavityDetector(Detector,
                          metaclass=BldMeta,
                          detcls=DdlPhaseCavity,
                          sources=['PhaseCavity'],
                          annotations=psana.Bld.BldDataPhaseCavityV1):
    pass



class DdlGmd(DdlHelper,
             metaclass=DdlHelperMeta,
             methods=psana.Bld.BldDataGMD):
    pass


@export
class GmdDetector(Detector,
                  metaclass=BldMeta,
                  detcls=DdlGmd,
                  sources=['GMD'],
                  annotations=psana.Bld.BldDataGMD):
    pass


class DdlEOrbits(DdlHelper,
                 metaclass=DdlHelperMeta,
                 methods=psana.Bld.BldDataEOrbits):
    pass


@export
class EOrbitsDetector(Detector,
                      metaclass=BldMeta,
                      detcls=DdlEOrbits,
                      sources=[''],
                      annotations=psana.Bld.BldDataEOrbits):
    pass


class DdlAnalogInput(DdlHelper,
                     metaclass=DdlHelperMeta,
                     methods=psana.Bld.BldDataAnalogInput):
    pass


@export
class AnalogInputDetector(Detector,
                          metaclass=BldMeta,
                          detcls=DdlAnalogInput,
                          sources=AIN_BLD_NAMES,
                          annotations=psana.Bld.BldDataAnalogInput,
                          overrides={'channelVoltages': amitypes.MultiChannelFloat}):
    def __init__(self, src, env):
        super().__init__(src, env)

    @property
    def nchannels(self):
        return 16


class DdlBeamMonitor(DdlHelper,
                     metaclass=DdlHelperMeta,
                     methods=psana.Bld.BldDataBeamMonitor):
    pass


@export
class BeamMonitorDetector(Detector,
                          metaclass=BldMeta,
                          detcls=DdlBeamMonitor,
                          sources=BEAMMON_BLD_NAMES,
                          annotations=psana.Bld.BldDataBeamMonitor,
                          overrides={'peakA': amitypes.MultiChannelFloat,
                                     'peakT': amitypes.MultiChannelInt}):
    def __init__(self, src, env):
        super().__init__(src, env)

    @property
    def nchannels(self):
        return 16


class DdlSpectrometer(DdlHelper,
                      metaclass=DdlHelperMeta,
                      methods=psana.Bld.BldDataSpectrometer):
    pass


@export
class SpectrometerDetector(Detector,
                           metaclass=BldMeta,
                           detcls=DdlSpectrometer,
                           sources=SPEC_BLD_NAMES,
                           annotations=psana.Bld.BldDataSpectrometer):
    pass
