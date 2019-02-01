from ami.graphkit_wrapper import Graph
import shutil
import os

class TestPsanaSource:

    def setup(self):
        try:
            import psana
            self.dotest = True
        except:
            self.dotest = False
            # silently pass if psana isn't available
            return
        os.system('xtcwriter') # generate the standard small xtc file
        fname = 'data.xtc2'
        shutil.move(fname,'/tmp/data.xtc2')

    def teardown(self):
        pass

    def test_psana_source(self):
        if not self.dotest: return
        from ami.data import PsanaSource
        idnum = 0
        num_workers = 1
        src_cfg = {}
        src_cfg['interval']=0
        src_cfg['init_time']=1
        src_cfg['config']={'filename':'/tmp/data.xtc2'}
        psana_source = PsanaSource(idnum, num_workers, src_cfg)
        evtgen = psana_source.events()
        config = next(evtgen) # first one is the config
        psana_source.requested_names = psana_source.xtcdata_names
        evt = next(evtgen)
        assert(len(evt.payload['xppcspad:raw:raw'])==18)
