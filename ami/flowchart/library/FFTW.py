from amitypes import Array1d, Array2d
from ami.flowchart.Node import Node
import ami.graph_nodes as gn
import pyfftw


class FFTProc():

    def __init__(self, builder):
        self.builder = builder
        self.input_ = None
        self.fft = None

    def __call__(self, arr):
        if self.fft is None:
            self.input_ = pyfftw.empty_aligned(arr.shape, dtype=arr.dtype)
            self.fft = self.builder(self.input_)

        self.input_[:] = arr
        return self.fft()


class FFT(Node):

    """pyfftw.builders.fft"""

    nodeName = "FFT"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Out': {'io': 'out', 'ttype': Array1d}})

    def to_operation(self, **kwargs):
        return gn.Map(name=self.name()+"_operation", **kwargs, func=FFTProc(pyfftw.builders.fft))


class IFFT(Node):

    """pyfftw.builders.ifft"""

    nodeName = "IFFT"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Out': {'io': 'out', 'ttype': Array1d}})

    def to_operation(self, **kwargs):
        return gn.Map(name=self.name()+"_operation", **kwargs, func=FFTProc(pyfftw.builders.ifft))


class FFT2(Node):

    """pyfftw.builders.fft2"""

    nodeName = "FFT2"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array2d},
                                          'Out': {'io': 'out', 'ttype': Array2d}})

    def to_operation(self, **kwargs):
        return gn.Map(name=self.name()+"_operation", **kwargs, func=FFTProc(pyfftw.builders.fft2))


class IFFT2(Node):

    """pyfftw.builders.ifft2"""

    nodeName = "IFFT2"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array2d},
                                          'Out': {'io': 'out', 'ttype': Array2d}})

    def to_operation(self, **kwargs):
        return gn.Map(name=self.name()+"_operation", **kwargs, func=FFTProc(pyfftw.builders.ifft2))


class RFFT(Node):

    """pyfftw.builders.rfft"""

    nodeName = "RFFT"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Out': {'io': 'out', 'ttype': Array1d}})

    def to_operation(self, **kwargs):
        return gn.Map(name=self.name()+"_operation", **kwargs, func=FFTProc(pyfftw.builders.rfft))


class IRFFT(Node):

    """pyfftw.builders.irfft"""

    nodeName = "IRFFT"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Out': {'io': 'out', 'ttype': Array1d}})

    def to_operation(self, **kwargs):
        return gn.Map(name=self.name()+"_operation", **kwargs, func=FFTProc(pyfftw.builders.irfft))


class RFFT2(Node):

    """pyfftw.builders.rfft2"""

    nodeName = "RFFT2"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array2d},
                                          'Out': {'io': 'out', 'ttype': Array2d}})

    def to_operation(self, **kwargs):
        return gn.Map(name=self.name()+"_operation", **kwargs, func=FFTProc(pyfftw.builders.rfft2))


class IRFFT2(Node):

    """pyfftw.builders.irfft2"""

    nodeName = "IRFFT2"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array2d},
                                          'Out': {'io': 'out', 'ttype': Array2d}})

    def to_operation(self, **kwargs):
        return gn.Map(name=self.name()+"_operation", **kwargs, func=FFTProc(pyfftw.builders.irfft2))
