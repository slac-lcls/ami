#!/usr/bin/env python
import sys
import zmq
import time
import logging
import argparse
import threading
import numpy as np
import collections
from ami import LogConfig
from ami.comm import Ports
from p4p import Type, Value
from p4p.nt import alarm, timeStamp, NTScalar, NTNDArray
from p4p.server import Server, StaticProvider
from p4p.server.thread import SharedPV


logger = logging.getLogger(__name__)


def _generate_schema():
    def btyes_to_np(value):
        return np.frombuffer(value, dtype=np.ubyte)
    fields = collections.OrderedDict([
        ('names', 'as'),
        ('version', 'l'),
        ('store', 'l'),
        ('dill', 'aB'),
    ])
    schema = [(k, v) for k, v in fields.items()]
    byte_fields = {'dill'}
    flat_names = {
        'names':    'graph:names',
        'version':  'graph:version',
        'store':    'store:version',
        'dill':     'graph:dill',
    }
    flat_schema = {
        k: (flat_names[k], NTScalar(v), btyes_to_np if k in byte_fields else None) for k, v in fields.items()
    }
    return schema, flat_schema, byte_fields


class NTGraph:
    schema, flat_schema, byte_fields = _generate_schema()

    @classmethod
    def buildType(klass, extra=[]):
        """Build type
        """
        return Type([
            ('value', ('S', None, klass.schema)),
            ('alarm', alarm),
            ('timeStamp', timeStamp),
        ], id='epics:nt/NTGraph:1.0')

    def __init__(self, **kws):
        self.type = self.buildType(**kws)

    def wrap(self, value):
        """Wrap dictionary as Value
        """
        S, NS = divmod(time.time(), 1.0)
        for field in self.byte_fields:
            value[field] = np.frombuffer(value[field], np.ubyte)
        return Value(self.type, {
            'value': value,
            'timeStamp': {
                'secondsPastEpoch': S,
                'nanoseconds': NS * 1e9,
            },
        })

    @classmethod
    def unwrap(klass, value):
        result = {}
        V = value.value
        for k in V:
            if k in klass.byte_fields:
                result[k] = V[k].tobytes()
            else:
                result[k] = V[k]
        return result


class PvaExportHandler:
    def __init__(self, name, comm_addr, export_addr, aggregate=False):
        self.name = name
        self.ctx = zmq.Context()
        self.export = self.ctx.socket(zmq.SUB)
        self.export.setsockopt_string(zmq.SUBSCRIBE, "")
        self.export.connect(export_addr)
        self.comm = self.ctx.socket(zmq.REQ)
        self.comm.connect(comm_addr)
        # pva server provider
        self.provider = StaticProvider(name)
        self.server_thread = threading.Thread(target=self.server, name='pvaserv')
        self.server_thread.daemon = True
        self.aggregate = aggregate
        self.pvs = {}
        self.ignored = set()

    def valid(self, name):
        return (name not in self.ignored) and (not name.startswith('_'))

    def unmangle(self, name):
        prefix = '_auto_'
        if name.startswith(prefix):
            return name[len(prefix):]
        else:
            return name

    def get_pv_type(self, data):
        if isinstance(data, np.ndarray):
            return NTNDArray()
        elif isinstance(data, int):
            return NTScalar('l')
        elif isinstance(data, float):
            return NTScalar('d')

    def update_graph(self, data):
        if self.aggregate:
            if 'graph' not in self.pvs:
                logger.debug("Creating pv for names in the graph")
                pv = SharedPV(nt=NTGraph(), initial=data)
                self.provider.add('%s:graph' % self.name, pv)
                self.pvs['graph'] = pv
            else:
                self.pvs['graph'].post(data)
        else:
            for k, v in data.items():
                if k in NTGraph.flat_schema:
                    name, nttype, func = NTGraph.flat_schema[k]
                    value = func(v) if func is not None else v
                    if name not in self.pvs:
                        pv = SharedPV(nt=nttype, initial=value)
                        self.provider.add('%s:%s' % (self.name, name), pv)
                        self.pvs[name] = pv
                    else:
                        self.pvs[name].post(value)

    def server(self):
        Server.forever(providers=[self.provider])

    def run(self):
        # start the pva server thread
        self.server_thread.start()
        logger.info("Starting PVA data export server")
        while True:
            topic = self.export.recv_string()
            exports = self.export.recv_pyobj()
            if topic == 'data':
                for raw, data in exports.items():
                    name = self.unmangle(raw)
                    # ignore names starting with '_' after unmangling - these are private
                    if self.valid(name):
                        if name not in self.pvs:
                            pv_type = self.get_pv_type(data)
                            if pv_type is not None:
                                logger.debug("Creating new pv named %s", name)
                                pv = SharedPV(nt=pv_type, initial=data)
                                self.provider.add('%s:%s' % (self.name, name), pv)
                                self.pvs[name] = pv
                            else:
                                logger.warn("Cannot map type of '%s' to PV: %s", name, type(data))
                                self.ignored.add(name)
                        else:
                            self.pvs[name].post(data)
            elif topic == 'graph':
                self.update_graph(exports)
            else:
                logger.warn("No handler for topic: %s", topic)


def run_export(name, comm_addr, export_addr, aggregate=False):
    export = PvaExportHandler(name, comm_addr, export_addr, aggregate)
    return export.run()


def main():
    parser = argparse.ArgumentParser(description='AMII DataExport App')

    parser.add_argument(
        '-H',
        '--host',
        default='localhost',
        help='hostname of the AMII Manager (default: localhost)'
    )

    parser.add_argument(
        '-e',
        '--export',
        type=int,
        default=Ports.Export,
        help='port for receiving data to export (default: %d)' % Ports.Export
    )

    parser.add_argument(
        '-c',
        '--comm',
        type=int,
        default=Ports.Comm,
        help='port for DataExport-Manager communication (default: %d)' % Ports.Comm
    )

    parser.add_argument(
        '-a',
        '--aggregate',
        action='store_true',
        help='aggregates graph and store related variables into structured data (not all clients support this)'
    )

    parser.add_argument(
        '--log-level',
        default=LogConfig.Level,
        help='the logging level of the application (default %s)' % LogConfig.Level
    )

    parser.add_argument(
        '--log-file',
        help='an optional file to write the log output to'
    )

    parser.add_argument(
        'name',
        help='the base name to use for data export (e.g. the base of all the PV names)'
    )

    args = parser.parse_args()

    export_addr = "tcp://%s:%d" % (args.host, args.export)
    comm_addr = "tcp://%s:%d" % (args.host, args.comm)

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    try:
        return run_export(args.name, comm_addr, export_addr, args.aggregate)
    except KeyboardInterrupt:
        logger.info("DataExport killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
