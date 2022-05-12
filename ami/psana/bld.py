import typing
import psana
import amitypes
from .detector import *
from .utils import export


__all__ = []


class DdlEBeam(DdlHelper,
               metaclass=DdlHelperMeta,
               methods=['ebeamCharge',
                        'ebeamL3Energy',
                        'ebeamLTUPosX',
                        'ebeamLTUPosY',
                        'ebeamLTUAngX',
                        'ebeamLTUAngY',
                        'ebeamPkCurrBC2',
                        'ebeamEnergyBC2',
                        'ebeamPkCurrBC1',
                        'ebeamEnergyBC1',
                        'ebeamUndPosX',
                        'ebeamUndPosY',
                        'ebeamUndAngX',
                        'ebeamUndAngY',
                        'ebeamXTCAVAmpl',
                        'ebeamXTCAVPhase',
                        'ebeamDumpCharge',
                        'ebeamPhotonEnergy',
                        'ebeamLTU250',
                        'ebeamLTU450']):
    pass


@export
class EBeam(Detector,
            metaclass=BldMeta,
            detcls=DdlEBeam,
            sources=['EBeam']):
    '''annotations={'ebeamCharge': float,
                         'ebeamL3Energy': float,
                         'ebeamLTUPosX': float,
                         'ebeamLTUPosY': float,
                         'ebeamLTUAngX': float,
                         'ebeamLTUAngY': float,
                         'ebeamPkCurrBC2': float,
                         'ebeamEnergyBC2': float,
                         'ebeamPkCurrBC1': float,
                         'ebeamEnergyBC1': float,
                         'ebeamUndPosX': float,
                         'ebeamUndPosY': float,
                         'ebeamUndAngX': float,
                         'ebeamUndAngY': float,
                         'ebeamXTCAVAmpl': float,
                         'ebeamXTCAVPhase': float,
                         'ebeamDumpCharge': float,
                         'ebeamPhotonEnergy': float,
                         'ebeamLTU250': float,
                         'ebeamLTU450': float},'''
    pass
