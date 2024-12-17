import os
import re
import sys
import signal
import logging
import argparse
import functools
from mpi4py import MPI

from ami import LogConfig
from ami.multiproc import check_mp_start_method
from ami.comm import Ports, PlatformAction
from ami.worker import run_worker
from ami.collector import run_node_collector


logger = logging.getLogger(__name__)


def build_parser():
    parser = argparse.ArgumentParser(description='AMII Single Node App')

    parser.add_argument(
        '-H',
        '--host',
        type=str,
        help='ami manager host')

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=Ports.BasePort,
        action=PlatformAction,
        help='base port for ami (default: %d) reserves next %d consecutive ports' % (Ports.BasePort, Ports.NumPorts)
    )

    parser.add_argument(
        '-b',
        '--heartbeat',
        type=int,
        default=10,
        help='the heartbeat period in ms (default: 10)'
    )

    parser.add_argument(
        '-d',
        '--eb-depth',
        type=int,
        default=10,
        help='the depth of contribution builder buffer in units of heartbeats (default: 10)'
    )

    parser.add_argument(
        '-f',
        '--flags',
        action='append',
        default=[],
        help='extra flags as key=value pairs that are passed to the data source of the worker'
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
        'source',
        nargs='?',
        metavar='SOURCE',
        help='data source configuration (exampes: static://test.json, psana://exp=xcsdaq13:run=14)'
    )

    parser.add_argument(
        '--prometheus-port',
        type=int,
        default=Ports.Prometheus,
        help='port for prometheus'
    )

    parser.add_argument(
        '--prometheus-dir',
        help='directory for prometheus configuration',
        default=None
    )

    parser.add_argument(
        '--hutch',
        help='hutch for prometheus label',
        default=None
    )

    return parser


def _sig_handler(procs, signum, frame):
    logger.debug('Caught signal %d', signum)
    sys.exit(cleanup(procs))


def _sys_exit(func, *args, **kwargs):
    sys.exit(func(*args, **kwargs))


def cleanup(procs):
    failed_proc = False

    for proc in procs:
        proc.terminate()

    for proc in procs:
        proc.join(1)
        if proc.is_alive():
            proc.kill()
            proc.join()

        if proc.exitcode == 0 or proc.exitcode == -signal.SIGTERM:
            logger.info('%s exited successfully', proc.name)
        else:
            failed_proc = True
            logger.error('%s exited with non-zero status code: %d', proc.name, proc.exitcode)

    return failed_proc


def run_ami(args):
    flags = {}

    host = args.host
    graph_addr = "tcp://%s:%d" % (host, args.port + Ports.Graph)
    # collector_addr = "tcp://127.0.0.1:%d" % (args.port + Ports.NodeCollector)
    collector_addr = "tcp://%s:%d" % (host, args.port + Ports.NodeCollector)
    globalcol_addr = "tcp://%s:%d" % (host, args.port + Ports.FinalCollector)
    export_addr = "tcp://%s:%d" % (host, args.port + Ports.Export)
    msg_addr = "tcp://%s:%d" % (host, args.port + Ports.Message)

    procs = []

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.FullFormat, level=log_level, handlers=log_handlers)

    try:
        for flag in args.flags:
            try:
                key, value = flag.split('=')
                flags[key] = value
            except ValueError:
                logger.exception("Problem parsing data source flag %s", flag)

        if args.source is not None:
            src_url_match = re.match('(?P<prot>.*)://(?P<body>.*)', args.source)
            if src_url_match:
                src_cfg = src_url_match.groups()
            else:
                logger.critical("Invalid data source config string: %s", args.source)
                return 1
        else:
            src_cfg = None

        comm = MPI.COMM_WORLD
        global_rank_size = comm.Get_size()
        global_rank = comm.Get_rank()
        local_comm = comm.Split_type(MPI.COMM_TYPE_SHARED, global_rank, MPI.INFO_NULL)
        local_rank_size = local_comm.Get_size()
        local_rank = local_comm.Get_rank()
        node_rank = global_rank // local_rank_size
        num_nodes = global_rank_size // local_rank_size

        # if local_rank == 0:
        #     typ = "localCollector"
        #     id_num = -1
        # else:
        #     typ = "worker"
        #     id_num = (node_rank*local_rank_size)+local_rank-(node_rank+1)

        # name = MPI.Get_processor_name()
        # print(f"NODE RANK: {node_rank} LOCAL RANK: {local_rank} GLOBAL_RANK: {global_rank} NAME: {name} {id_num} {typ}")

        # if local_rank == 0:
        #     run_node_collector(node_rank, local_rank_size-1, args.eb_depth, collector_addr, globalcol_addr,
        #                        graph_addr, msg_addr, args.prometheus_dir, args.prometheus_port, args.hutch)

        # run_worker(id_num, local_rank_size-1, args.heartbeat, src_cfg,
        #            collector_addr, graph_addr, msg_addr, export_addr,
        #            flags, args.prometheus_dir, args.prometheus_port, args.hutch)

        run_worker(local_rank, local_rank_size, args.heartbeat, src_cfg,
                   collector_addr, graph_addr, msg_addr, export_addr,
                   flags, args.prometheus_dir, args.prometheus_port, args.hutch)

        # register a signal handler for cleanup on sigterm
        signal.signal(signal.SIGTERM, functools.partial(_sig_handler, procs))

        while True:
            pass

    except KeyboardInterrupt:
        logger.info("Worker killed by user...")
    finally:
        failed_proc = cleanup(procs)
        # return a non-zero status code if any workerss died
        if failed_proc:
            return 1


def main():
    # Check the mp start method and fix for platforms that need it
    check_mp_start_method()

    # start the ami processes
    parser = build_parser()
    args = parser.parse_args()
    return run_ami(args)


if __name__ == '__main__':
    sys.exit(main())
