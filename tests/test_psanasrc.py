import pytest

from ami.data import Source


def test_psana_source(xtcwriter):
    if xtcwriter is None:
        return
    psana_source_cls = Source.find_source('psana')
    assert psana_source_cls is not None
    idnum = 0
    num_workers = 1
    src_cfg = {}
    src_cfg['interval'] = 0
    src_cfg['init_time'] = 1
    src_cfg['config'] = {'filename': xtcwriter}
    psana_source = psana_src_cls(idnum, num_workers, src_cfg)
    evtgen = psana_source.events()
    next(evtgen)  # first event is the config
    psana_source.requested_names = psana_source.xtcdata_names
    evt = next(evtgen)
    assert(len(evt.payload['xppcspad:raw:raw']) == 18)
