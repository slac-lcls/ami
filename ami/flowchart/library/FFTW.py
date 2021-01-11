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

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions,
                      inputs=inputs, outputs=outputs,
                      func=FFTProc(pyfftw.builders.fft),
                      parent=self.name())

        return node


class IFFT(Node):

    """pyfftw.builders.ifft"""

    nodeName = "IFFT"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Out': {'io': 'out', 'ttype': Array1d}})

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions,
                      inputs=inputs, outputs=outputs,
                      func=FFTProc(pyfftw.builders.ifft),
                      parent=self.name())

        return node


class FFT2(Node):

    """pyfftw.builders.fft2"""

    nodeName = "FFT2"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array2d},
                                          'Out': {'io': 'out', 'ttype': Array2d}})

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions,
                      inputs=inputs, outputs=outputs,
                      func=FFTProc(pyfftw.builders.fft2),
                      parent=self.name())

        return node


class IFFT2(Node):

    """pyfftw.builders.ifft2"""

    nodeName = "IFFT2"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array2d},
                                          'Out': {'io': 'out', 'ttype': Array2d}})

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions,
                      inputs=inputs, outputs=outputs,
                      func=FFTProc(pyfftw.builders.ifft2),
                      parent=self.name())

        return node


class RFFT(Node):

    """pyfftw.builders.rfft"""

    nodeName = "RFFT"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Out': {'io': 'out', 'ttype': Array1d}})

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions,
                      inputs=inputs, outputs=outputs,
                      func=FFTProc(pyfftw.builders.rfft),
                      parent=self.name())

        return node


class IRFFT(Node):

    """pyfftw.builders.irfft"""

    nodeName = "IRFFT"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Out': {'io': 'out', 'ttype': Array1d}})

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions,
                      inputs=inputs, outputs=outputs,
                      func=FFTProc(pyfftw.builders.irfft),
                      parent=self.name())

        return node


class RFFT2(Node):

    """pyfftw.builders.rfft2"""

    nodeName = "RFFT2"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array2d},
                                          'Out': {'io': 'out', 'ttype': Array2d}})

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions,
                      inputs=inputs, outputs=outputs,
                      func=FFTProc(pyfftw.builders.rfft2),
                      parent=self.name())

        return node


class IRFFT2(Node):

    """pyfftw.builders.irfft2"""

    nodeName = "IRFFT2"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array2d},
                                          'Out': {'io': 'out', 'ttype': Array2d}})

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions,
                      inputs=inputs, outputs=outputs,
                      func=FFTProc(pyfftw.builders.irfft2),
                      parent=self.name())

        return node
