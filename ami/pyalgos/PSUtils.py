import psana

if hasattr(psana, '_psana'):
    from Detector.UtilsEpix10ka2M import *      # noqa ignore=F405
    def table_nxm_jungfrau_from_ndarr(nda):
        """returns table of jungfrau panels shaped as (nxn)
        generated from jungfrau array shaped as (N, 512, 1024) in data.
        """
        segsize = 512*1024
        a = np.array(nda) # make a copy

        if a.size == segsize:
            a.shape = (512,1024)
            return a

        elif a.size == 2*segsize:
            logger.warning('jungfrau1m panels are stacked as [1,0]')
            sh = a.shape = (2,512,1024)
            return np.vstack([a[q,:] for q in (1,0)])

        elif a.size == 8*segsize:
            logger.warning('jungfrau4m panels are stacked as [(7,3), (6,2), (5,1), (4,0)]')
            sh = a.shape = (8,512,1024)
            return np.hstack([np.vstack([a[q,:] for q in (7,6,5,4)]),\
                              np.vstack([a[q,:] for q in (3,2,1,0)])])
        else:
            from psana.pyalgos.generic.NDArrUtils import reshape_to_2d
            return reshape_to_2d(a)
else:
    from psana.pyalgos.generic.PSUtils import * # noqa ignore=F405
