import pytest
import typing
import numpy as np
import amitypes as at
try:
    import h5py
except ImportError:
    h5py = None

from ami import psana
from conftest import psanatest, psana1test, hdf5test
from ami.data import MsgTypes, Source, Transition, Transitions


@pytest.fixture(scope='function')
def sim_src_cfg():
    return {
        'interval': 0,
        'init_time': 0,
        'bound': 5,
        'config': {
            "delta_t": {"dtype": "Scalar", "range": [0, 10], "integer": True},
            "cspad": {"dtype": "Image", "pedestal": 5, "width": 1, "shape": [512, 512]},
            "acq": {"dtype": "Waveform", "pedestal": 5, "width": 1, "shape": 512},
            "laser": {"dtype": "Scalar", "range": [0, 2], "integer": True},
        },
    }


def test_find_source():
    src_cls = Source.find_source('static')
    assert src_cls is not None

    src_cls = Source.find_source('random')
    assert src_cls is not None

    src_cls = Source.find_source('notreal')
    assert src_cls is None


@hdf5test
def test_hdf5_source(hdf5writer):
    src_cls = Source.find_source('hdf5')
    assert src_cls is not None
    idnum = 0
    num_workers = 1
    heartbeat_period = 5
    src_cfg = {
        'type': 'hdf5',
        'interval':  0,
        'init_time':  0,
        'files': [str(hdf5writer)],
    }
    expected_cfg = {
        'gasdet': float,
        'ec': int,
        'camera': at.Group,
        'camera:image': at.Array2d,
        'camera:raw': at.Array3d,
        'eventid': int,
        'timestamp': float,
        'heartbeat': int,
        'source': at.DataSource,
    }
    expected_grps = {
        'camera': {
            'image': at.Array2d,
            'raw': at.Array3d,
        }
    }

    source = src_cls(idnum, num_workers, heartbeat_period, src_cfg)

    assert source.src_type == 'hdf5'

    # request all the sources
    source.request(set(expected_cfg))

    # loop over all the events
    count = 0
    for evt in source.events():
        if evt.mtype == MsgTypes.Transition:
            assert evt.identity == idnum
            assert isinstance(evt.payload, Transition)
            if evt.payload.ttype == Transitions.Configure:
                sources = {k: at.loads(v) for k, v in evt.payload.payload.items()}
                assert sources == expected_cfg
        elif evt.mtype == MsgTypes.Datagram:
            assert set(evt.payload) == set(expected_cfg)
            for name, data in evt.payload.items():
                if type(data) in at.NumPyTypeDict:
                    assert at.NumPyTypeDict[type(data)] == expected_cfg[name]
                else:
                    assert isinstance(data, expected_cfg[name])

                if isinstance(data, at.DataSource):
                    assert data.cfg == src_cfg
                    assert data.key == 1
                    assert isinstance(data.run, h5py.File)
                    assert data.evt == (count, data.run)
                elif isinstance(data, at.Group):
                    assert data.src == source.src_type
                    assert data.type == 'Group'
                    assert data.name == name
                    assert name in expected_grps
                    assert set(data) == set(expected_grps[name])
                    # check the types of the group
                    for k, v in expected_grps[name].items():
                        assert isinstance(data[k], v)

            count += 1
        elif evt.mtype == MsgTypes.Heartbeat:
            assert count == heartbeat_period * (evt.payload.identity + 1)

    # check that the last evt was an unconfigure
    assert evt.mtype == MsgTypes.Transition and evt.payload.ttype == Transitions.Unconfigure


@psana1test
@pytest.mark.parametrize('psana1_xtc',
                         [('test_031_xpptut15', 'e665-r0540-s01-c00.xtc')],
                         indirect=['psana1_xtc'])
def test_psana1_source(psana1_xtc):
    psana_src_cls = Source.find_source('psana')
    assert psana_src_cls is not None
    idnum = 0
    num_workers = 1
    heartbeat_period = 2
    src_cfg = {
        'type': 'psana',
        'interval':  0,
        'init_time':  0,
        'files': [str(psana1_xtc)],
    }
    # these are broken
    if psana1_xtc.name == 'e665-r0540-s01-c00.xtc':
        excludes = {'evr1:raw', 'evr1:raw:eventCodes'}
        expected_cfg = {
            'ControlData': at.Detector,
            'ControlData:raw': at.Group,
            'ControlData:raw:controls': at.ScanControls,
            'ControlData:raw:labels': at.ScanLabels,
            'ControlData:raw:monitors': at.ScanMonitors,
            'XCS:TIMETOOL:AMPL': float,
            'XCS:TIMETOOL:AMPLNXT': float,
            'XCS:TIMETOOL:FLTPOS': float,
            'XCS:TIMETOOL:FLTPOSFWHM': float,
            'XCS:TIMETOOL:FLTPOS_PS': float,
            'XCS:TIMETOOL:REFAMPL': float,
            'XPP_diamond_theta': float,
            'att_E': float,
            'att_T': float,
            'att_T3rd': float,
            'ccm_E': float,
            'ccm_x1': float,
            'ccm_x2': float,
            'ccm_y1': float,
            'ccm_y2': float,
            'ccm_y3': float,
            'chi_base_tc': float,
            'crl_Be_xpos': float,
            'crl_Be_ypos': float,
            'crl_Be_zpos': float,
            'det_z': float,
            'diff_chis': float,
            'diff_dety': float,
            'diff_phis': float,
            'diff_th': float,
            'diff_tth': float,
            'diff_x': float,
            'diff_xs': float,
            'diff_y': float,
            'diff_ys': float,
            'diff_zs': float,
            'eBeam_charge': float,
            'eBeam_energy': float,
            'eBeam_energy_loss_converted_to_photon_mJ': float,
            'eBeam_energy_loss_in_MeV': float,
            'eBeam_peak_current_after_second_bunch_compressor': float,
            'eBeam_pulse_length': float,
            'eBeam_pulse_length_xtcav': float,
            'eBeam_slottedFoil_BC2': float,
            'eBeam_slottedFoil_BC2_readback': float,
            'evr_usr1_delay': float,
            'evr_usr1_width': float,
            'evr_usr2_delay': float,
            'evr_usr2_width': float,
            'evr_usr3_delay': float,
            'evr_usr3_width': float,
            'evr_usr4_delay': float,
            'evr_usr4_width': float,
            'fee_GasAttenuator_actual_pressure': float,
            'fee_GasAttenuator_calculated_transmission': float,
            'fee_GasDetector_1_PMT_voltage_241': float,
            'fee_GasDetector_1_PMT_voltage_242': float,
            'fee_GasDetector_1_pressure': float,
            'fee_GasDetector_2_PMT_voltage_361': float,
            'fee_GasDetector_2_PMT_voltage_362': float,
            'fee_GasDetector_2_pressure': float,
            'fee_SolidAttenuator_1': int,
            'fee_SolidAttenuator_2': int,
            'fee_SolidAttenuator_3': int,
            'fee_SolidAttenuator_4': int,
            'fee_SolidAttenuator_E': float,
            'fee_SolidAttenuator_Transmission': float,
            'fee_SolidAttenuator_totalLength': float,
            'fee_homs_m1h_pitch': float,
            'fee_homs_m1h_xp': float,
            'fee_homs_m1h_xs': float,
            'fee_homs_m1h_yp': float,
            'fee_homs_m1h_ys': float,
            'fee_homs_m2h_pitch': float,
            'fee_homs_m2h_pitch-MIRR:XRT:M2H:RBV': float,
            'fee_homs_m2h_xp': float,
            'fee_homs_m2h_xp-XRT:M2H:X:P:RBV': float,
            'fee_homs_m2h_xs': float,
            'fee_homs_m2h_xs-XRT:M2H:X:S:RBV': float,
            'fee_homs_m2h_yp': float,
            'fee_homs_m2h_yp-XRT:M2H:Y:P:RBV': float,
            'fee_homs_m2h_ys': float,
            'fee_homs_m2h_ys-XRT:M2H:Y:S:RBV': float,
            'gon_phi_reflectivity': float,
            'ipm1_xd': float,
            'ipm1_yd': float,
            'ipm1_yt': float,
            'ipm2_xd': float,
            'ipm2_yd': float,
            'ipm2_yt': float,
            'ipm4_xd': float,
            'ipm4_yd': float,
            'ipm4_yt': float,
            'ipm5_xd': float,
            'ipm5_yd': float,
            'ipm5_yt': float,
            'ipmmono_xd': float,
            'ipmmono_yd': float,
            'ipmmono_yt': float,
            'ladm_theta': float,
            'lam_det_x': float,
            'lam_det_y': float,
            'lam_x1': float,
            'lam_x2': float,
            'lam_y1': float,
            'lam_y2': float,
            'lam_z': float,
            'las_compressor': float,
            'las_delayNew': float,
            'las_lensf': float,
            'las_lensh': float,
            'las_lensv': float,
            'las_opa_wp': float,
            'las_tt_delay': float,
            'lib_y': float,
            'lom_E': float,
            'lom_E1': float,
            'lom_E2': float,
            'lom_chi1': float,
            'lom_chi1_fine': float,
            'lom_chi1_val': float,
            'lom_chi2': float,
            'lom_chi2_fine': float,
            'lom_chi2_val': float,
            'lom_dia_h': float,
            'lom_dia_pips': float,
            'lom_dia_theta': float,
            'lom_dia_v': float,
            'lom_diode2': float,
            'lom_filters': float,
            'lom_h1n': float,
            'lom_h1p': float,
            'lom_h2n': float,
            'lom_theta1': float,
            'lom_theta1_fine': float,
            'lom_theta1_val': float,
            'lom_theta2': float,
            'lom_theta2_fine': float,
            'lom_x1': float,
            'lom_x2': float,
            'lom_y1': float,
            'lom_y2': float,
            'lom_z1': float,
            'lom_z2': float,
            'nav_focus': float,
            'nav_zoom': float,
            'photonBeam_Calculated_number_of_photons': float,
            'photonBeam_Rate': float,
            'photonBeam_Wavelength': float,
            'photonBeam_dumpAttenuators_ladder': float,
            'photonBeam_dumpAttenuators_ladder_rdb': float,
            'photonBeam_energy': float,
            'photonBeam_energy_corr': float,
            'photonBeam_pulse_length_xtcav': float,
            'photonBeam_timing_cable_compensation': float,
            'samx': float,
            'samy': float,
            'samz': float,
            'scan_Number_of_steps': int,
            'scan_Run_is_scan': int,
            'scan_current_step': int,
            'scan_motor_0': str,
            'scan_motor_0_position_max': float,
            'scan_motor_0_position_min': float,
            'scan_motor_1': str,
            'scan_motor_1_position_max': float,
            'scan_motor_1_position_min': float,
            'scan_motor_2': str,
            'scan_motor_2_position_max': float,
            'scan_motor_2_position_min': float,
            'scan_shots_per_step': int,
            'slit_botx': float,
            'slit_boty': float,
            'slit_s1_d': float,
            'slit_s1_n': float,
            'slit_s1_s': float,
            'slit_s1_u': float,
            'slit_s2_d': float,
            'slit_s2_n': float,
            'slit_s2_s': float,
            'slit_s2_u': float,
            'slit_s3_d': float,
            'slit_s3_n': float,
            'slit_s3_s': float,
            'slit_s3_u': float,
            'slit_s3m_d': float,
            'slit_s3m_n': float,
            'slit_s3m_s': float,
            'slit_s3m_u': float,
            'slit_s4_d': float,
            'slit_s4_n': float,
            'slit_s4_s': float,
            'slit_s4_u': float,
            'slit_s5_d': float,
            'slit_s5_n': float,
            'slit_s5_s': float,
            'slit_s5_u': float,
            'slit_s6_d': float,
            'slit_s6_n': float,
            'slit_s6_s': float,
            'slit_s6_u': float,
            'slit_sfee_d': float,
            'slit_sfee_ho': float,
            'slit_sfee_hw': float,
            'slit_sfee_n': float,
            'slit_sfee_s': float,
            'slit_sfee_u': float,
            'slit_sfee_vo': float,
            'slit_sfee_vw': float,
            'slit_topx': float,
            'slit_topy': float,
            'snd_DIA_dcc_Y': float,
            'snd_DIA_dcc_x': float,
            'snd_DIA_dci_x': float,
            'snd_DIA_dco_x': float,
            'snd_DIA_dd_Y': float,
            'snd_DIA_dd_x': float,
            'snd_DIA_di_x': float,
            'snd_DIA_do_x': float,
            'snd_t1_chi1': float,
            'snd_t1_chi2': float,
            'snd_t1_dh': float,
            'snd_t1_l': float,
            'snd_t1_th1': float,
            'snd_t1_th2': float,
            'snd_t1_tth': float,
            'snd_t1_x': float,
            'snd_t1_y1': float,
            'snd_t1_y2': float,
            'snd_t2_th': float,
            'snd_t2_x': float,
            'snd_t3_th': float,
            'snd_t3_x': float,
            'snd_t4_chi1': float,
            'snd_t4_chi2': float,
            'snd_t4_dh': float,
            'snd_t4_l': float,
            'snd_t4_th1': float,
            'snd_t4_th2': float,
            'snd_t4_tth': float,
            'snd_t4_x': float,
            'snd_t4_y1': float,
            'snd_t4_y2': float,
            'spring_tc': float,
            'undulator_1050': float,
            'undulator_1150': float,
            'undulator_1250': float,
            'undulator_1350': float,
            'undulator_1450': float,
            'undulator_150': float,
            'undulator_1550': float,
            'undulator_1650': float,
            'undulator_1750': float,
            'undulator_1850': float,
            'undulator_1950': float,
            'undulator_2050': float,
            'undulator_2150': float,
            'undulator_2250': float,
            'undulator_2350': float,
            'undulator_2450': float,
            'undulator_250': float,
            'undulator_2550': float,
            'undulator_2650': float,
            'undulator_2750': float,
            'undulator_2850': float,
            'undulator_2950': float,
            'undulator_3050': float,
            'undulator_3150': float,
            'undulator_3250': float,
            'undulator_3350': float,
            'undulator_350': float,
            'undulator_450': float,
            'undulator_550': float,
            'undulator_650': float,
            'undulator_750': float,
            'undulator_850': float,
            'undulator_950': float,
            'vernier': float,
            'xtal_holder_tc': float,
            'yag_yag1_y': float,
            'yag_yag1_zoom': float,
            'yag_yag2_y': float,
            'yag_yag2_zoom': float,
            'yag_yag3_y': float,
            'yag_yag3_zoom': float,
            'yag_yag3m_y': float,
            'yag_yag3m_zoom': float,
            'yag_yag4_y': float,
            'yag_yag4_zoom': float,
            'yag_yag5_y': float,
            'yag_yag5_zoom': float,
            'EBeam': at.Detector,
            'EBeam:raw': at.Group,
            'EBeam:raw:damageMask': int,
            'EBeam:raw:ebeamCharge': float,
            'EBeam:raw:ebeamDumpCharge': float,
            'EBeam:raw:ebeamEnergyBC1': float,
            'EBeam:raw:ebeamEnergyBC2': float,
            'EBeam:raw:ebeamL3Energy': float,
            'EBeam:raw:ebeamLTU250': float,
            'EBeam:raw:ebeamLTU450': float,
            'EBeam:raw:ebeamLTUAngX': float,
            'EBeam:raw:ebeamLTUAngY': float,
            'EBeam:raw:ebeamLTUPosX': float,
            'EBeam:raw:ebeamLTUPosY': float,
            'EBeam:raw:ebeamPhotonEnergy': float,
            'EBeam:raw:ebeamPkCurrBC1': float,
            'EBeam:raw:ebeamPkCurrBC2': float,
            'EBeam:raw:ebeamUndAngX': float,
            'EBeam:raw:ebeamUndAngY': float,
            'EBeam:raw:ebeamUndPosX': float,
            'EBeam:raw:ebeamUndPosY': float,
            'EBeam:raw:ebeamXTCAVAmpl': float,
            'EBeam:raw:ebeamXTCAVPhase': float,
            'FEEGasDetEnergy': at.Detector,
            'FEEGasDetEnergy:raw': at.Group,
            'FEEGasDetEnergy:raw:f_11_ENRC': float,
            'FEEGasDetEnergy:raw:f_12_ENRC': float,
            'FEEGasDetEnergy:raw:f_21_ENRC': float,
            'FEEGasDetEnergy:raw:f_22_ENRC': float,
            'FEEGasDetEnergy:raw:f_63_ENRC': float,
            'FEEGasDetEnergy:raw:f_64_ENRC': float,
            'PhaseCavity': at.Detector,
            'PhaseCavity:raw': at.Group,
            'PhaseCavity:raw:charge1': float,
            'PhaseCavity:raw:charge2': float,
            'PhaseCavity:raw:fitTime1': float,
            'PhaseCavity:raw:fitTime2': float,
            'XCS-AIN-01': at.Detector,
            'XCS-AIN-01:raw': at.Group,
            'XCS-AIN-01:raw:channelVoltages': at.MultiChannelFloat,
            'XCS-AIN-01:raw:channelVoltages:0': float,
            'XCS-AIN-01:raw:channelVoltages:1': float,
            'XCS-AIN-01:raw:channelVoltages:10': float,
            'XCS-AIN-01:raw:channelVoltages:11': float,
            'XCS-AIN-01:raw:channelVoltages:12': float,
            'XCS-AIN-01:raw:channelVoltages:13': float,
            'XCS-AIN-01:raw:channelVoltages:14': float,
            'XCS-AIN-01:raw:channelVoltages:15': float,
            'XCS-AIN-01:raw:channelVoltages:2': float,
            'XCS-AIN-01:raw:channelVoltages:3': float,
            'XCS-AIN-01:raw:channelVoltages:4': float,
            'XCS-AIN-01:raw:channelVoltages:5': float,
            'XCS-AIN-01:raw:channelVoltages:6': float,
            'XCS-AIN-01:raw:channelVoltages:7': float,
            'XCS-AIN-01:raw:channelVoltages:8': float,
            'XCS-AIN-01:raw:channelVoltages:9': float,
            'XCS-AIN-01:raw:numChannels': int,
            'XCS-IPM-gon': at.Detector,
            'XCS-IPM-gon:fex': at.Group,
            'XCS-IPM-gon:fex:channel': at.MultiChannelFloat,
            'XCS-IPM-gon:fex:channel:0': float,
            'XCS-IPM-gon:fex:channel:1': float,
            'XCS-IPM-gon:fex:channel:2': float,
            'XCS-IPM-gon:fex:channel:3': float,
            'XCS-IPM-gon:fex:sum': float,
            'XCS-IPM-gon:fex:xpos': float,
            'XCS-IPM-gon:fex:ypos': float,
            'XCS-SB1-BMMON': at.Detector,
            'XCS-SB1-BMMON:raw': at.Group,
            'XCS-SB1-BMMON:raw:TotalIntensity': float,
            'XCS-SB1-BMMON:raw:X_Position': float,
            'XCS-SB1-BMMON:raw:Y_Position': float,
            'XCS-SB1-BMMON:raw:peakA': at.MultiChannelFloat,
            'XCS-SB1-BMMON:raw:peakA:0': float,
            'XCS-SB1-BMMON:raw:peakA:1': float,
            'XCS-SB1-BMMON:raw:peakA:2': float,
            'XCS-SB1-BMMON:raw:peakA:3': float,
            'XCS-SB1-BMMON:raw:peakA:4': float,
            'XCS-SB1-BMMON:raw:peakA:5': float,
            'XCS-SB1-BMMON:raw:peakA:6': float,
            'XCS-SB1-BMMON:raw:peakA:7': float,
            'XCS-SB1-BMMON:raw:peakA:8': float,
            'XCS-SB1-BMMON:raw:peakA:9': float,
            'XCS-SB1-BMMON:raw:peakA:10': float,
            'XCS-SB1-BMMON:raw:peakA:11': float,
            'XCS-SB1-BMMON:raw:peakA:12': float,
            'XCS-SB1-BMMON:raw:peakA:13': float,
            'XCS-SB1-BMMON:raw:peakA:14': float,
            'XCS-SB1-BMMON:raw:peakA:15': float,
            'XCS-SB1-BMMON:raw:peakT': at.MultiChannelInt,
            'XCS-SB1-BMMON:raw:peakT:0': int,
            'XCS-SB1-BMMON:raw:peakT:1': int,
            'XCS-SB1-BMMON:raw:peakT:2': int,
            'XCS-SB1-BMMON:raw:peakT:3': int,
            'XCS-SB1-BMMON:raw:peakT:4': int,
            'XCS-SB1-BMMON:raw:peakT:5': int,
            'XCS-SB1-BMMON:raw:peakT:6': int,
            'XCS-SB1-BMMON:raw:peakT:7': int,
            'XCS-SB1-BMMON:raw:peakT:8': int,
            'XCS-SB1-BMMON:raw:peakT:9': int,
            'XCS-SB1-BMMON:raw:peakT:10': int,
            'XCS-SB1-BMMON:raw:peakT:11': int,
            'XCS-SB1-BMMON:raw:peakT:12': int,
            'XCS-SB1-BMMON:raw:peakT:13': int,
            'XCS-SB1-BMMON:raw:peakT:14': int,
            'XCS-SB1-BMMON:raw:peakT:15': int,
            'XCS-SB2-BMMON': at.Detector,
            'XCS-SB2-BMMON:raw': at.Group,
            'XCS-SB2-BMMON:raw:TotalIntensity': float,
            'XCS-SB2-BMMON:raw:X_Position': float,
            'XCS-SB2-BMMON:raw:Y_Position': float,
            'XCS-SB2-BMMON:raw:peakA': at.MultiChannelFloat,
            'XCS-SB2-BMMON:raw:peakA:0': float,
            'XCS-SB2-BMMON:raw:peakA:1': float,
            'XCS-SB2-BMMON:raw:peakA:2': float,
            'XCS-SB2-BMMON:raw:peakA:3': float,
            'XCS-SB2-BMMON:raw:peakA:4': float,
            'XCS-SB2-BMMON:raw:peakA:5': float,
            'XCS-SB2-BMMON:raw:peakA:6': float,
            'XCS-SB2-BMMON:raw:peakA:7': float,
            'XCS-SB2-BMMON:raw:peakA:8': float,
            'XCS-SB2-BMMON:raw:peakA:9': float,
            'XCS-SB2-BMMON:raw:peakA:10': float,
            'XCS-SB2-BMMON:raw:peakA:11': float,
            'XCS-SB2-BMMON:raw:peakA:12': float,
            'XCS-SB2-BMMON:raw:peakA:13': float,
            'XCS-SB2-BMMON:raw:peakA:14': float,
            'XCS-SB2-BMMON:raw:peakA:15': float,
            'XCS-SB2-BMMON:raw:peakT': at.MultiChannelInt,
            'XCS-SB2-BMMON:raw:peakT:0': int,
            'XCS-SB2-BMMON:raw:peakT:1': int,
            'XCS-SB2-BMMON:raw:peakT:2': int,
            'XCS-SB2-BMMON:raw:peakT:3': int,
            'XCS-SB2-BMMON:raw:peakT:4': int,
            'XCS-SB2-BMMON:raw:peakT:5': int,
            'XCS-SB2-BMMON:raw:peakT:6': int,
            'XCS-SB2-BMMON:raw:peakT:7': int,
            'XCS-SB2-BMMON:raw:peakT:8': int,
            'XCS-SB2-BMMON:raw:peakT:9': int,
            'XCS-SB2-BMMON:raw:peakT:10': int,
            'XCS-SB2-BMMON:raw:peakT:11': int,
            'XCS-SB2-BMMON:raw:peakT:12': int,
            'XCS-SB2-BMMON:raw:peakT:13': int,
            'XCS-SB2-BMMON:raw:peakT:14': int,
            'XCS-SB2-BMMON:raw:peakT:15': int,
            'XCS-USB-ENCODER-01': at.Detector,
            'XCS-USB-ENCODER-01:calibconst': dict,
            'XCS-USB-ENCODER-01:fex': at.Group,
            'XCS-USB-ENCODER-01:fex:values': at.MultiChannelFloat,
            'XCS-USB-ENCODER-01:fex:values:0': float,
            'XCS-USB-ENCODER-01:fex:values:1': float,
            'XCS-USB-ENCODER-01:fex:values:2': float,
            'XCS-USB-ENCODER-01:fex:values:3': float,
            'XCS-USB-ENCODER-01:raw': at.Group,
            'XCS-USB-ENCODER-01:raw:analog_in': at.MultiChannelInt,
            'XCS-USB-ENCODER-01:raw:analog_in:0': int,
            'XCS-USB-ENCODER-01:raw:analog_in:1': int,
            'XCS-USB-ENCODER-01:raw:analog_in:2': int,
            'XCS-USB-ENCODER-01:raw:analog_in:3': int,
            'XCS-USB-ENCODER-01:raw:digital_in': int,
            'XCS-USB-ENCODER-01:raw:encoder_count': at.MultiChannelInt,
            'XCS-USB-ENCODER-01:raw:encoder_count:0': int,
            'XCS-USB-ENCODER-01:raw:encoder_count:1': int,
            'XCS-USB-ENCODER-01:raw:encoder_count:2': int,
            'XCS-USB-ENCODER-01:raw:encoder_count:3': int,
            'XCS-USB-ENCODER-01:raw:status': at.MultiChannelInt,
            'XCS-USB-ENCODER-01:raw:status:0': int,
            'XCS-USB-ENCODER-01:raw:status:1': int,
            'XCS-USB-ENCODER-01:raw:status:2': int,
            'XCS-USB-ENCODER-01:raw:status:3': int,
            'XCS-USB-ENCODER-01:raw:timestamp': int,
            'epix10ka2m': at.Detector,
            'epix10ka2m:raw': at.Group,
            'epix10ka2m:raw:calib': at.Array3d,
            'epix10ka2m:raw:image': at.Array2d,
            'epix10ka2m:raw:raw': at.Array3d,
            'eventid': int,
            'evr0': at.Detector,
            'evr0:raw': at.Group,
            'evr0:raw:eventCodes': list[int],
            'evr1': at.Detector,
            'evr1:raw': at.Group,
            'evr1:raw:eventCodes': list[int],
            'heartbeat': int,
            'opal_1': at.Detector,
            'opal_1:raw': at.Group,
            'opal_1:raw:calib': at.Array2d,
            'opal_1:raw:image': at.Array2d,
            'opal_1:raw:raw': at.Array2d,
            'source': at.DataSource,
            'timestamp': float,
        }
        expected_grps = {
            'ControlData:raw': {
                'controls': at.ScanControls,
                'labels': at.ScanLabels,
                'monitors': at.ScanMonitors,
            },
            'EBeam:raw': {
                'damageMask': int,
                'ebeamCharge': float,
                'ebeamDumpCharge': float,
                'ebeamEnergyBC1': float,
                'ebeamEnergyBC2': float,
                'ebeamL3Energy': float,
                'ebeamLTU250': float,
                'ebeamLTU450': float,
                'ebeamLTUAngX': float,
                'ebeamLTUAngY': float,
                'ebeamLTUPosX': float,
                'ebeamLTUPosY': float,
                'ebeamPhotonEnergy': float,
                'ebeamPkCurrBC1': float,
                'ebeamPkCurrBC2': float,
                'ebeamUndAngX': float,
                'ebeamUndAngY': float,
                'ebeamUndPosX': float,
                'ebeamUndPosY': float,
                'ebeamXTCAVAmpl': float,
                'ebeamXTCAVPhase': float,
            },
            'FEEGasDetEnergy:raw': {
                'f_11_ENRC': float,
                'f_12_ENRC': float,
                'f_21_ENRC': float,
                'f_22_ENRC': float,
                'f_63_ENRC': float,
                'f_64_ENRC': float,
            },
            'PhaseCavity:raw': {
                'charge1': float,
                'charge2': float,
                'fitTime1': float,
                'fitTime2': float,
            },
            'XCS-AIN-01:raw': {
                'channelVoltages': at.MultiChannelFloat,
                'numChannels': int,
            },
            'XCS-IPM-gon:fex': {
                'channel': at.MultiChannelFloat,
                'sum': float,
                'xpos': float,
                'ypos': float,
            },
            'XCS-SB1-BMMON:raw': {
                'TotalIntensity': float,
                'X_Position': float,
                'Y_Position': float,
                'peakA': at.MultiChannelFloat,
                'peakT': at.MultiChannelInt,
            },
            'XCS-SB2-BMMON:raw': {
                'TotalIntensity': float,
                'X_Position': float,
                'Y_Position': float,
                'peakA': at.MultiChannelFloat,
                'peakT': at.MultiChannelInt,
            },
            'XCS-USB-ENCODER-01:fex': {
                'values': at.MultiChannelFloat,
            },
            'XCS-USB-ENCODER-01:raw': {
                'analog_in': at.MultiChannelInt,
                'digital_in': int,
                'encoder_count': at.MultiChannelInt,
                'status': at.MultiChannelInt,
                'timestamp': int,
            },
            'epix10ka2m:raw': {
                'raw': at.Array3d,
                'calib': at.Array3d,
                'image': at.Array2d,
            },
            'opal_1:raw': {
                'raw': at.Array2d,
                'calib': at.Array2d,
                'image': at.Array2d,
            },
            'evr0:raw': {
                'eventCodes': list,
            },
            'evr1:raw': {
                'eventCodes': list,
            },
        }
        expected_grp_types = {
            'ControlData:raw': 'ScanDetectorHelper',
            'EBeam:raw': 'DdlEBeam',
            'FEEGasDetEnergy:raw': 'DdlFEEGasDet',
            'PhaseCavity:raw': 'DdlPhaseCavity',
            'XCS-AIN-01:raw': 'DdlAnalogInput',
            'XCS-IPM-gon:fex': 'IpimbDetector',
            'XCS-SB1-BMMON:raw': 'DdlBeamMonitor',
            'XCS-SB2-BMMON:raw': 'DdlBeamMonitor',
            'XCS-USB-ENCODER-01:fex': 'UsdUsbDetector',
            'XCS-USB-ENCODER-01:raw': 'RawUsdUsbDetector',
            'epix10ka2m:raw': 'MultiPanelHelper',
            'opal_1:raw': 'AreaDetectorHelper',
            'evr0:raw': 'EvrDetector',
            'evr1:raw': 'EvrDetector',
        }
    else:
        excludes = set()
        expected_cfg = {}
        expected_grps = {}
        expected_grp_types = {}
    psana_source = psana_src_cls(idnum, num_workers, heartbeat_period, src_cfg)

    assert psana_source.src_type == 'psana'

    evtgen = psana_source.events()

    # check the returned configuration message
    config = next(evtgen)  # first event is the config
    assert config.mtype == MsgTypes.Transition
    assert config.identity == idnum
    assert isinstance(config.payload, Transition)
    assert config.payload.ttype == Transitions.Configure
    sources = {k: at.loads(v) for k, v in config.payload.payload.items()}
    assert sources == expected_cfg

    # check the returned step message
    step = next(evtgen)
    assert step.mtype == MsgTypes.Transition
    assert step.identity == idnum
    assert isinstance(step.payload, Transition)
    assert step.payload.ttype == Transitions.BeginStep
    assert step.payload.payload == 0

    # request all the sources
    psana_source.request(set(expected_cfg))

    # patch expected_cfg to remove typing._GenericAlias and convert to real type
    expected_types = {}
    for name, cls in expected_cfg.items():
        if isinstance(cls, typing._GenericAlias):
            cls = at.loads('typing.'+cls._name)
        elif isinstance(cls, typing.GenericAlias):
            cls = type(cls())
        expected_types[name] = cls

    # loop over all the events
    for count, msg in enumerate(evtgen):
        if msg.mtype == MsgTypes.Datagram:
            assert set(msg.payload) == set(expected_cfg)
            for name, data in msg.payload.items():
                if name in excludes:
                    continue

                if type(data) in at.NumPyTypeDict:
                    assert at.NumPyTypeDict[type(data)] == expected_types[name]
                else:
                    assert isinstance(data, expected_types[name])

                if isinstance(data, at.DataSource):
                    assert data.cfg == src_cfg
                    assert data.key == 1
                    assert isinstance(data.run, psana.datasource.Run)
                    assert isinstance(data.evt, psana.datasource.Event)
                elif isinstance(data, at.Group):
                    assert name in expected_grps and name in expected_grp_types
                    assert data.src == psana_source.src_type
                    assert data.type == expected_grp_types[name]
                    assert data.name == name
                    assert set(data) == set(expected_grps[name])
                    # check the types of the group
                    for k, v in expected_grps[name].items():
                        assert isinstance(data[k], v)
        elif msg.mtype == MsgTypes.Heartbeat:
            break

    # check the number of events we processed
    assert count == heartbeat_period


@psanatest
def test_psana_source(xtcwriter):
    psana_src_cls = Source.find_source('psana')
    assert psana_src_cls is not None
    idnum = 0
    num_workers = 1
    heartbeat_period = 10
    src_cfg = {
        'type': 'psana',
        'interval':  0,
        'init_time':  0,
        'files': [str(xtcwriter)],
    }
    # these are broken in xtcwriter
    excludes = {'HX2:DVD:GCC:01:PMON', 'HX2:DVD:GPI:01:PMON', 'motor1', 'motor2'}
    expected_cfg = {
        'HX2:DVD:GCC:01:PMON': float,
        'HX2:DVD:GPI:01:PMON': str,
        'motor1': float,
        'motor2': float,
        'xpphsd': at.Detector,
        'xpphsd:calibconst': dict,
        'xpphsd:raw:calib': at.Array1d,
        'xpphsd:raw:config': dict,
        'xpphsd:raw': at.Group,
        'xpphsd:fex:calib': at.Array1d,
        'xpphsd:fex:config': dict,
        'xpphsd:fex': at.Group,
        'xppcspad': at.Detector,
        'xppcspad:calibconst': dict,
        'xppcspad:raw:calib': at.Array3d,
        'xppcspad:raw:image': at.Array2d,
        'xppcspad:raw:raw': at.Array3d,
        'xppcspad:raw:config': dict,
        'xppcspad:raw': at.Group,
        'epicsinfo': at.Detector,
        'epicsinfo:epicsinfo': at.Group,
        'epicsinfo:epicsinfo:config': dict,
        'epicsinfo:calibconst': dict,
        'eventid': int,
        'timestamp': float,
        'heartbeat': int,
        'keepraw': int,
        'source': at.DataSource,
    }
    expected_grps = {
        'xpphsd:raw': {
            'calib': at.Array1d,
            'config': dict,
        },
        'xpphsd:fex': {
            'calib': at.Array1d,
            'config': dict,
        },
        'xppcspad:raw': {
            'calib': at.Array3d,
            'image': at.Array2d,
            'raw': at.Array3d,
            'config': dict,
        },
        'epicsinfo:epicsinfo': {
            'config': dict,
        },
    }
    expected_grp_types = {
        'xpphsd:raw': 'hsd_raw_0_0_0',
        'xpphsd:fex': 'hsd_fex_4_5_6',
        'xppcspad:raw': 'cspad_raw_2_3_42',
        'epicsinfo:epicsinfo': 'epicsinfo_epicsinfo_1_0_0',
    }
    psana_source = psana_src_cls(idnum, num_workers, heartbeat_period, src_cfg)

    assert psana_source.src_type == 'psana'

    evtgen = psana_source.events()

    # check the returned configuration message
    config = next(evtgen)  # first event is the config
    assert config.mtype == MsgTypes.Transition
    assert config.identity == idnum
    assert isinstance(config.payload, Transition)
    assert config.payload.ttype == Transitions.Configure
    sources = {k: at.loads(v) for k, v in config.payload.payload.items()}
    assert sources == expected_cfg

    # check the returned step message
    step = next(evtgen)
    assert step.mtype == MsgTypes.Transition
    assert step.identity == idnum
    assert isinstance(step.payload, Transition)
    assert step.payload.ttype == Transitions.BeginStep
    assert step.payload.payload == 0

    # request all the sources
    psana_source.request(set(expected_cfg))

    # loop over all the events
    for count, msg in enumerate(evtgen):
        if msg.mtype == MsgTypes.Datagram:
            assert set(msg.payload) == set(expected_cfg)
            for name, data in msg.payload.items():
                if name in excludes:
                    continue

                assert isinstance(data, expected_cfg[name])

                if isinstance(data, at.DataSource):
                    assert data.cfg == src_cfg
                    assert data.key == 1
                    assert isinstance(data.run, psana.psexp.run.Run)
                    assert isinstance(data.evt, psana.event.Event)
                elif isinstance(data, at.Group):
                    assert name in expected_grps and name in expected_grp_types
                    assert data.src == psana_source.src_type
                    assert data.type == expected_grp_types[name]
                    assert data.name == name
                    assert set(data) == set(expected_grps[name])
                    # check the types of the group
                    for k, v in expected_grps[name].items():
                        assert isinstance(data[k], v)
        elif msg.mtype == MsgTypes.Heartbeat:
            break

    # check the number of events we processed
    assert count == heartbeat_period


def test_static_source(sim_src_cfg):
    src_cls = Source.find_source('static')
    assert src_cls is not None

    idnum = 0
    num_workers = 1
    heartbeat_period = 10

    source = src_cls(idnum, num_workers, heartbeat_period, sim_src_cfg)

    assert source.src_type == 'static'

    # check the names from the source are correct
    expected_names = {'eventid', 'timestamp', 'heartbeat', 'source'}
    expected_names.update(sim_src_cfg['config'].keys())
    assert source.names == expected_names
    # check the types from the source are correct
    expected_dtypes = {'eventid': int, 'timestamp': float, 'heartbeat': int, 'source': at.DataSource}
    for name, cfg in sim_src_cfg['config'].items():
        if cfg["dtype"] == "Scalar":
            if cfg.get("integer", False):
                expected_dtypes[name] = int
            else:
                expected_dtypes[name] = float
        elif cfg["dtype"] == "Waveform":
            expected_dtypes[name] = at.Array1d
        elif cfg["dtype"] == "Image":
            expected_dtypes[name] = at.Array2d
        else:
            expected_dtypes[name] = None
    assert source.types == expected_dtypes

    # check the returned configuration message
    config = source.configure()
    assert config.mtype == MsgTypes.Transition
    assert config.identity == idnum
    assert isinstance(config.payload, Transition)
    assert config.payload.ttype == Transitions.Configure
    assert set(config.payload.payload) == expected_names
    for name, dtype in config.payload.payload.items():
        assert at.loads(dtype) == expected_dtypes[name]

    # do a first loop over the data (events should be empty)
    count = 0
    for msg in source.events():
        if msg.mtype == MsgTypes.Datagram:
            assert not msg.payload
            count += 1
            assert msg.timestamp == num_workers * count + idnum

    # check that the static source returned the correct number of events
    assert count == sim_src_cfg['bound']

    # test the request feature of the source
    assert not source.requested_names
    source.request(expected_names)
    assert source.requested_names == expected_names

    # do a second loop over the data (events should be non-empty)
    count = 0
    for msg in source.events():
        if msg.mtype == MsgTypes.Datagram:
            for name, cfg in sim_src_cfg['config'].items():
                if cfg["dtype"] == "Scalar":
                    assert msg.payload[name] == 1
                elif (cfg["dtype"] == "Image") or (cfg["dtype"] == "Waveform"):
                    assert (msg.payload[name] == 1).all()
            count += 1
            expected_ts = num_workers * count + idnum + sim_src_cfg['bound']
            assert msg.timestamp == expected_ts
            assert msg.payload['eventid'] == expected_ts
            assert msg.payload['heartbeat'] == expected_ts // heartbeat_period

    # check that the static source returned the correct number of events
    assert count == sim_src_cfg['bound']


def test_random_source(sim_src_cfg):
    src_cls = Source.find_source('random')
    assert src_cls is not None

    idnum = 0
    num_workers = 1
    heartbeat_period = 10

    source = src_cls(idnum, num_workers, heartbeat_period, sim_src_cfg)

    assert source.src_type == 'random'

    # check the names from the source are correct
    expected_names = {'eventid', 'timestamp', 'heartbeat', 'source'}
    expected_names.update(sim_src_cfg['config'].keys())
    assert source.names == expected_names
    # check the types from the source are correct
    expected_dtypes = {'eventid': int, 'timestamp': float, 'heartbeat': int, 'source': at.DataSource}
    for name, cfg in sim_src_cfg['config'].items():
        if cfg["dtype"] == "Scalar":
            if cfg.get("integer", False):
                expected_dtypes[name] = int
            else:
                expected_dtypes[name] = float
        elif cfg["dtype"] == "Waveform":
            expected_dtypes[name] = at.Array1d
        elif cfg["dtype"] == "Image":
            expected_dtypes[name] = at.Array2d
        else:
            expected_dtypes[name] = None
    assert source.types == expected_dtypes

    # check the returned configuration message
    config = source.configure()
    assert config.mtype == MsgTypes.Transition
    assert config.identity == idnum
    assert isinstance(config.payload, Transition)
    assert config.payload.ttype == Transitions.Configure
    assert set(config.payload.payload) == expected_names
    for name, dtype in config.payload.payload.items():
        assert at.loads(dtype) == expected_dtypes[name]

    # do a first loop over the data (events should be empty)
    for msg in source.events():
        if msg.mtype == MsgTypes.Datagram:
            assert not msg.payload
            break

    # test the request feature of the source
    assert not source.requested_names
    source.request(expected_names)
    assert source.requested_names == expected_names

    # do a second loop over the data (events should be non-empty)
    for msg in source.events():
        if msg.mtype == MsgTypes.Datagram:
            for name in expected_names:
                assert name in msg.payload
                if expected_dtypes[name] == at.Array1d:
                    assert type(msg.payload[name]) == np.ndarray
                    assert msg.payload[name].ndim == 1
                elif expected_dtypes[name] == at.Array2d:
                    assert type(msg.payload[name]) == np.ndarray
                    assert msg.payload[name].ndim == 2
                else:
                    assert type(msg.payload[name]) == expected_dtypes[name]
            break


def test_source_heartbeat(sim_src_cfg):
    src_cls = Source.find_source('static')
    assert src_cls is not None

    sim_src_cfg['bound'] = 10

    idnum = 0
    num_workers = 1
    heartbeat_period = 3

    source = src_cls(idnum, num_workers, heartbeat_period, sim_src_cfg)

    # loop over the events testing that heartbeats appear when expected
    count = 0
    for msg in source.events():
        if msg.mtype == MsgTypes.Datagram:
            count += 1
        elif msg.mtype == MsgTypes.Heartbeat:
            # check that heart happened between the right events
            assert ((count + 1) % heartbeat_period) == 0
            # check that the number of the heartbeat is as expected
            assert msg.payload == ((count - 1) // heartbeat_period)


def test_source_request(sim_src_cfg):
    src_cls = Source.find_source('static')
    assert src_cls is not None

    sim_src_cfg['bound'] = 10

    idnum = 0
    num_workers = 1
    heartbeat_period = 3

    expected_names = [
        ['cspad'],
        [],
        ['cspad', 'delta_t'],
    ]

    source = src_cls(idnum, num_workers, heartbeat_period, sim_src_cfg)

    # loop over the events testing that data dict keys match the requested names
    for msg in source.events():
        if msg.mtype == MsgTypes.Datagram:
            assert set(msg.payload.keys()) == source.requested_names
        elif msg.mtype == MsgTypes.Heartbeat:
            source.request(expected_names[msg.payload.identity])


def test_source_badrequest(sim_src_cfg):
    src_cls = Source.find_source('static')
    assert src_cls is not None

    sim_src_cfg['bound'] = 10

    idnum = 0
    num_workers = 1
    heartbeat_period = 3

    requested_names = [
        ('cspad', True),
        ('notthere', False),
    ]

    source = src_cls(idnum, num_workers, heartbeat_period, sim_src_cfg)
    source.request(entry[0] for entry in requested_names)

    for name, present in requested_names:
        # check that the requested names are there
        assert name in source.requested_names
        # check that the bad names are not in requested_data
        assert (name in source.requested_data) is present
