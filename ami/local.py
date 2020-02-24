import os
import re
import sys
import shutil
import signal
import logging
import tempfile
import argparse
import functools
import multiprocessing as mp

from ami import LogConfig, Defaults, check_mp_start_method
from ami.comm import Ports, GraphCommHandler
from ami.manager import run_manager
from ami.worker import run_worker
from ami.collector import run_node_collector, run_global_collector
from ami.client import run_client
from ami.console import run_console
try:
    from ami.export import run_export
except ImportError:
    run_export = None


logger = logging.getLogger(__name__)


def build_parser():
    parser = argparse.ArgumentParser(description='AMII Single Node App')

    parser.add_argument(
        '-n',
        '--num-workers',
        type=int,
        default=1,
        help='number of worker processes (default: 1)'
    )

    parser.add_argument(
        '-l',
        '--load',
        help='saved AMII configuration to load'
    )

    parser.add_argument(
        '-e',
        '--export',
        help='the base name to use for data export (e.g. the base of all the PV names)'
    )

    parser.add_argument(
        '-a',
        '--aggregate',
        action='store_true',
        help='aggregates graph and store related variables into structured data when exporting'
    )

    comm_group = parser.add_mutually_exclusive_group()

    comm_group.add_argument(
        '-t',
        '--tcp',
        action='store_true',
        help='use tcp instead of ipc for communication'
    )

    comm_group.add_argument(
        '-i',
        '--ipc',
        help='ipc dir to use for communication'
    )

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=Ports.Comm,
        help='starting port when using tcp for communication (default: %d)' % Ports.Comm
    )

    parser.add_argument(
        '-b',
        '--heartbeat',
        type=int,
        default=10,
        help='the heartbeat period (default: 10)'
    )

    parser.add_argument(
        '-c',
        '--console',
        action='store_true',
        help='run in a console mode (no GUI)'
    )

    parser.add_argument(
        '-f',
        '--flags',
        nargs='*',
        default=[],
        help='extra flags as key=value pairs that are passed to the data source of the worker'
    )

    parser.add_argument(
        '-g',
        '--graph-name',
        default=Defaults.GraphName,
        help='the name of the graph used (default: %s)' % Defaults.GraphName
    )

    parser.add_argument(
        '--headless',
        action='store_true',
        help='run in a headless mode (no GUI) can only interact over zmq'
    )

    guimode_parser = parser.add_mutually_exclusive_group()

    guimode_parser.add_argument(
        '--legacy-gui',
        dest='gui_mode',
        action='store_true',
        help="use the traditional AMI1-style GUI"
    )

    guimode_parser.add_argument(
        '--flowchart-gui',
        dest='gui_mode',
        action='store_false',
        help="use the new AMI2-style flowchart GUI"
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


def run_ami(args, queue=None):

    xtcdir = None
    ipcdir = None
    owns_ipcdir = True
    flags = {}
    if queue is None:
        queue = mp.Queue()
    if args.tcp:
        host = "127.0.0.1"
        comm_addr = "tcp://%s:%d" % (host, args.port)
        graph_addr = "tcp://%s:%d" % (host, args.port+1)
        collector_addr = "tcp://%s:%d" % (host, args.port+2)
        globalcol_addr = "tcp://%s:%d" % (host, args.port+3)
        results_addr = "tcp://%s:%d" % (host, args.port+4)
        export_addr = "tcp://%s:%d" % (host, args.port+5)
        msg_addr = "tcp://%s:%d" % (host, args.port+6)
        info_addr = "tcp://%s:%d" % (host, args.port+7)
        view_addr = "tcp://%s:%d" % (host, args.port+8)
        profile_addr = "tcp://%s:%d" % (host, args.port+9)
    else:
        if args.ipc:
            ipcdir = args.ipc
            owns_ipcdir = False
        else:
            ipcdir = tempfile.mkdtemp()
            owns_ipcdir = True
        collector_addr = "ipc://%s/node_collector" % ipcdir
        globalcol_addr = "ipc://%s/collector" % ipcdir
        graph_addr = "ipc://%s/graph" % ipcdir
        comm_addr = "ipc://%s/comm" % ipcdir
        results_addr = "ipc://%s/results" % ipcdir
        export_addr = "ipc://%s/export" % ipcdir
        msg_addr = "ipc://%s/message" % ipcdir
        info_addr = "ipc://%s/info" % ipcdir
        view_addr = "ipc://%s/view" % ipcdir
        profile_addr = "ipc://%s/profile" % ipcdir

    procs = []
    client_proc = None

    log_handlers = [logging.StreamHandler()]
    if args.headless or args.console:
        console_fmt = logging.Formatter(LogConfig.BasicFormat)
        log_handlers[0].setFormatter(console_fmt)
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

        for i in range(args.num_workers):
            proc = mp.Process(
                name='worker%03d-n0' % i,
                target=functools.partial(_sys_exit, run_worker),
                args=(i, args.num_workers, args.heartbeat, src_cfg,
                      collector_addr, graph_addr, msg_addr, export_addr, flags)
            )
            proc.daemon = True
            proc.start()
            procs.append(proc)

        collector_proc = mp.Process(
            name='nodecol-n0',
            target=functools.partial(_sys_exit, run_node_collector),
            args=(0, args.num_workers, collector_addr, globalcol_addr, graph_addr, msg_addr)
        )
        collector_proc.daemon = True
        collector_proc.start()
        procs.append(collector_proc)

        globalcol_proc = mp.Process(
            name='globalcol',
            target=functools.partial(_sys_exit, run_global_collector),
            args=(0, 1, globalcol_addr, results_addr, graph_addr, msg_addr)
        )
        globalcol_proc.daemon = True
        globalcol_proc.start()
        procs.append(globalcol_proc)

        manager_proc = mp.Process(
            name='manager',
            target=functools.partial(_sys_exit, run_manager),
            args=(args.num_workers, 1, results_addr, graph_addr, comm_addr, msg_addr, info_addr, export_addr, view_addr,
                  profile_addr)
        )
        manager_proc.daemon = True
        manager_proc.start()
        procs.append(manager_proc)

        if args.export:
            if run_export is None:
                logger.critical("Export module is not available: p4p needs to be installed to use the export feature!")
                return 1
            export_proc = mp.Process(
                name='export',
                target=functools.partial(_sys_exit, run_export),
                args=(args.export, comm_addr, export_addr, args.aggregate)
            )
            export_proc.daemon = True
            export_proc.start()
            procs.append(export_proc)

        if not (args.console or args.headless):
            client_proc = mp.Process(
                name='client',
                target=run_client,
                args=(args.graph_name, comm_addr, info_addr, view_addr, args.load, args.gui_mode)
            )
            client_proc.daemon = False
            client_proc.start()
            procs.append(client_proc)

        # register a signal handler for cleanup on sigterm
        signal.signal(signal.SIGTERM, functools.partial(_sig_handler, procs))

        if args.console:
            run_console(args.graph_name, comm_addr, args.load)
        elif args.headless:
            if args.load:
                comm_handler = GraphCommHandler(args.graph_name, comm_addr)
                comm_handler.load(args.load)
            while queue.empty():
                pass
        else:
            client_proc.join()

    except KeyboardInterrupt:
        logger.info("Worker killed by user...")
    finally:
        failed_proc = cleanup(procs)
        # cleanup ipc directories
        if owns_ipcdir and ipcdir is not None and os.path.exists(ipcdir):
            shutil.rmtree(ipcdir)
        if xtcdir is not None and os.path.exists(xtcdir):
            shutil.rmtree(xtcdir)
        # return a non-zero status code if any workerss died
        if client_proc is not None and client_proc.exitcode != 0:
            return client_proc.exitcode
        elif failed_proc:
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
