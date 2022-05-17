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
