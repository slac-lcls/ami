import sys
import dill
import logging
import IPython
import argparse

from ami import LogConfig
from ami.comm import Ports, GraphCommHandler


logger = logging.getLogger(__name__)


def run_console(addr, load):
    amicli = GraphCommHandler(addr)

    if load is not None:
        try:
            with open(load, 'rb') as cnf:
                amicli.update(dill.load(cnf))
        except OSError as os_exp:
                logger.exception("ami-console: problem opening saved graph configuration file:")
        except dill.UnpicklingError as dill_exp:
                logger.exception("ami-console: problem parsing saved graph configuration file (%s):", load)

    IPython.embed(banner1='AMII Interactive Shell Client',
                  banner2=" - using manager at %s\n - use 'amicli?' for help\n" % addr)


def main():
    parser = argparse.ArgumentParser(description='AMII Shell Client')

    parser.add_argument(
        '-H',
        '--host',
        default='localhost',
        help='hostname of the AMII Manager (default: localhost)'
    )

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=Ports.Comm,
        help='port for manager/client (SHELL) communication (default: %d)' % Ports.Comm
    )

    parser.add_argument(
        '-l',
        '--load',
        help='saved AMII configuration to load'
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
    addr = "tcp://%s:%d" % (args.host, args.port)

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        file_fmt = logging.Formatter(LogConfig.Format)
        file_handler = logging.FileHandler(args.log_file)
        file_handler.setFormatter(file_fmt)
        log_handlers.append(file_handler)
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.BasicFormat, level=log_level, handlers=log_handlers)

    try:
        return run_console(addr, args.load)
    except KeyboardInterrupt:
        logger.info("Client killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
