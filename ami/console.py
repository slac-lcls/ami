import sys
import glob
import logging
import IPython
import pathlib
import tempfile
import argparse
import datetime

from traitlets.config.loader import Config
from ami import LogConfig, Defaults
from ami.comm import Ports, PlatformAction


logger = logging.getLogger(__name__)


def run_console(name, addr, load):
    banners = {
        'banner1': 'AMII Interactive Shell Client',
        'banner2': " - using manager at %s\n - use 'amicli?' for help\n" % addr,
    }
    exec_lines = [
        'import sys',
        'from ami.comm import GraphCommHandler',
        'amicli = GraphCommHandler("%s", "%s")' % (name, addr),
        'sys.path.extend(amicli.paths)'
    ]
    if load is not None:
        exec_lines.append('amicli.load("%s")' % load)

    IPython.start_ipython(argv=[], config=Config(TerminalInteractiveShell=banners,
                                                 InteractiveShellApp={'exec_lines': exec_lines}))


def main():
    parser = argparse.ArgumentParser(description='AMII Shell Client')

    parser.add_argument(
        '-H',
        '--host',
        default=Defaults.Host,
        help='hostname of the AMII Manager (default: %s)' % Defaults.Host
    )

    addr_group = parser.add_mutually_exclusive_group()

    addr_group.add_argument(
        '-p',
        '--port',
        type=int,
        default=Ports.BasePort,
        help='base port for manager/client (SHELL) communication (default: %d)' % Ports.BasePort
    )

    addr_group.add_argument(
        '-i',
        '--ipc-dir',
        help='directory containing the ipc file descriptor for manager/client (SHELL) communication'
    )

    addr_group.add_argument(
        '--ipc',
        action='store_true',
        help='attempt to search for ipc file descriptors for manager/client (SHELL) communication'
    )

    parser.add_argument(
        '-g',
        '--graph-name',
        default=Defaults.GraphName,
        help='the name of the graph used for manager/client (SHELL) communication (default: %s)' % Defaults.GraphName
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

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        file_fmt = logging.Formatter(LogConfig.Format)
        file_handler = logging.FileHandler(args.log_file)
        file_handler.setFormatter(file_fmt)
        log_handlers.append(file_handler)
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.BasicFormat, level=log_level, handlers=log_handlers)

    if args.ipc:
        ipc_list = glob.glob(tempfile.gettempdir() + '/*/comm')
        if ipc_list:
            if len(ipc_list) == 1:
                addr = "ipc://%s" % ipc_list[0]
            else:
                prompt = "Found %d ipc file descriptors:\n" % len(ipc_list)
                for i, ipc_name in enumerate(ipc_list):
                    path = pathlib.Path(ipc_name)
                    cdate = datetime.datetime.fromtimestamp(path.stat().st_ctime).strftime('%Y-%m-%d %H:%M:%S')
                    prompt += " %d - addr: %s, user: %s, date: %s\n" % (i, ipc_name, path.owner(), cdate)
                prompt += " %d - Quit\n\nPlease choose one: " % len(ipc_list)
                choice = input(prompt)
                try:
                    addr = "ipc://%s" % ipc_list[int(choice)]
                except ValueError:
                    logger.critical("Invalid option '%s' chosen!", choice)
                    return 1
                except IndexError:
                    logger.debug("Option chosen is outside range of ipc list - assume quit!")
                    return 0
        else:
            logger.critical("No manager ipc file descriptors found!")
            return 1
    elif args.ipc_dir is not None:
        addr = "ipc://%s/comm" % args.ipc_dir
    else:
        addr = "tcp://%s:%d" % (args.host, args.port + Ports.Comm)

    try:
        return run_console(args.graph_name, addr, args.load)
    except KeyboardInterrupt:
        logger.info("Client killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
