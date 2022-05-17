import psana
from .detector import detector_factory, detnames_to_detinfo
from .utils import export, Extender


__all__ = []


@export
class DataSource(Extender):
    def __init__(self, *args, **kwargs):
        args = []
        opts = []

        # extra options that can be tagged on the end
        if 'dir' in kwargs:
            opts.append('dir=%s' % kwargs['dir'])
            del kwargs['dir']
        if 'live' in kwargs and kwargs['live']:
            opts.append('live')
            del kwargs['live']
        if 'smd' in kwargs and kwargs['smd']:
            opts.append('smd')
            del kwargs['smd']

        # convert args to lcls1 psana format
        if 'files' in kwargs:
            for f in kwargs['files']:
                args.append(f)
            del kwargs['files']
        elif 'shmem' in kwargs:
            arg = 'shmem=%s:stop=no' % kwargs['shmem']
            args.append(":".join([arg]+opts))
            del kwargs['shmem']
        elif 'exp' in kwargs and 'run' in kwargs:
            arg = 'exp=%s:run=%d' % (kwargs['exp'], kwargs['run'])
            args.append(":".join([arg]+opts))
            del kwargs['exp']
            del kwargs['run']

        # check for special calibdir kwarg
        if 'calibdir' in kwargs:
            psana.setOption('psana.calib-dir', kwargs['calibdir'])
            del kwargs['calibdir']

        # create the underlying datasource
        ds = psana.DataSource(*args, **kwargs)

        super().__init__(ds)

    def steps(self):
        yield from map(lambda x: Step(x), self._base.steps())

    def runs(self):
        yield from map(lambda x: Run(x), self._base.runs())

    def events(self):
        yield from map(lambda x: Event(x), self._base.events())


@export
class Run(Extender):
    def __init__(self, run):
        super().__init__(run)
        self.__detinfo = None
        self.__epicsinfo = None
        self.__scaninfo = None

    def steps(self):
        yield from map(lambda x: Step(x), self._base.steps())

    def events(self):
        yield from map(lambda x: Event(x), self._base.events())

    @property
    def detinfo(self):
        if self.__detinfo is None:
            self.__detinfo = detnames_to_detinfo(psana.DetNames(), self.env())
        return self.__detinfo

    @property
    def epicsinfo(self):
        if self.__epicsinfo is None:
            self.__epicsinfo = {}
        return self.__epicsinfo

    @property
    def scaninfo(self):
        if self.__scaninfo is None:
            self.__scaninfo = {}
        return self.__scaninfo

    def Detector(self, src):
        return detector_factory(src, self.env())


@export
class Step(Extender):
    def __init__(self, step):
        super().__init__(step)

    def events(self):
        yield from map(lambda x: Event(x), self._base.events())


@export
class Event(Extender):
    def __init__(self, event):
        super().__init__(event)

    @property
    def timestamp(self):
        sec, nsec = self._base.get(psana.EventId).time()
        return (sec << 32) | nsec
