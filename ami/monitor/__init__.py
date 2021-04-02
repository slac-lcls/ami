import sys
import logging
import argparse
import asyncio
import tornado.ioloop
from ami import LogConfig, Defaults
from ami.comm import Ports
from ami.monitor import monitor


logger = logging.getLogger(__name__)


def run_monitor(graph, export_addr, view_addr):
    logger.info('Starting monitor')

    loop = tornado.ioloop.IOLoop.current()
    with monitor.Monitor(graph, export_addr, view_addr) as mon:
        asyncio.ensure_future(mon.run(loop))
        loop.start()


def main():
    parser = argparse.ArgumentParser(description='AMII GUI Client')

    parser.add_argument(
        '-H',
        '--host',
        default=Defaults.Host,
        help='hostname of the AMII Manager (default: %s)' % Defaults.Host
    )

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        nargs=2,
        default=(Ports.Export, Ports.View),
        help='port for manager (GUI) communication and view (default: %d, %d)' %
             (Ports.Export, Ports.View)
    )

    parser.add_argument(
        '-g',
        '--graph-name',
        default=Defaults.GraphName,
        help='the name of the graph used (default: %s)' % Defaults.GraphName
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

    args = parser.parse_args()
    graph = args.graph_name
    export, view = args.port
    export_addr = "tcp://%s:%d" % (args.host, export)
    view_addr = "tcp://%s:%d" % (args.host, view)

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    try:
        return run_monitor(graph, export_addr, view_addr)
    except KeyboardInterrupt:
        logger.info("Monitor killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
