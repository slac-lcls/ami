import psana
from .detector import BldMeta, DdlHelperMeta, DdlHelper, Detector
from .utils import export


__all__ = []


class DdlEBeam(DdlHelper,
               metaclass=DdlHelperMeta,
               methods=psana.Bld.BldDataEBeam):
    pass


@export
class EBeam(Detector,
            metaclass=BldMeta,
            detcls=DdlEBeam,
            sources=['EBeam'],
            annotations=psana.Bld.BldDataEBeam):
    pass


class DdlFEEGasDet(DdlHelper,
                   metaclass=DdlHelperMeta,
                   methods=[psana.Bld.BldDataFEEGasDetEnergyV1]):
    pass


@export
class FEEGasDet(Detector,
                metaclass=BldMeta,
                detcls=DdlFEEGasDet,
                sources=['FEEGasDetEnergy'],
                annotations=[psana.Bld.BldDataFEEGasDetEnergyV1]):
    pass
