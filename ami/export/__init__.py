import sys
import logging
import argparse

from ami import LogConfig, Defaults
from ami.comm import Ports
from ami.export import server


logger = logging.getLogger(__name__)


def run_export(name, comm_addr, export_addr, aggregate=False):
    export = server.PvaExportServer(name, comm_addr, export_addr, aggregate)
    return export.run()


def main():
    parser = argparse.ArgumentParser(description='AMII DataExport App')

    parser.add_argument(
        '-H',
        '--host',
        default=Defaults.Host,
        help='hostname of the AMII Manager (default: %s)' % Defaults.Host
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
