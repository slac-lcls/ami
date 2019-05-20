import os
import sys
import glob
import logging
import argparse
import tempfile
import collections
from ami import LogConfig, Defaults
from ami.comm import Ports
from ami.client import flowchart, legacy


logger = logging.getLogger(__name__)


GraphAddress = collections.namedtuple('GraphAddress', ['name', 'uri'])


def run_client(graph_name, comm_addr, info_addr, load, use_legacy=True):
    graph_addr = GraphAddress(graph_name, comm_addr)
    if use_legacy:
        return legacy.run_client(graph_addr, info_addr, load)
    else:
        return flowchart.run_client(graph_addr, info_addr, load)


def main():
    parser = argparse.ArgumentParser(description='AMII GUI Client')

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
        nargs=2,
        default=(Ports.Comm, Ports.Info),
        help='port for manager/client (GUI) communication and status info (default: %d, %d)' % (Ports.Comm, Ports.Info)
    )

    addr_group.add_argument(
        '-i',
        '--ipc-dir',
        help='directory containing the ipc file descriptor for manager/client (GUI) communication'
    )

    addr_group.add_argument(
        '--ipc',
        action='store_true',
        help='attempt to search for ipc file descriptors for manager/client (GUI) communication'
    )

    parser.add_argument(
        '-g',
        '--graph-name',
        default=Defaults.GraphName,
        help='the name of the graph used (default: %s)' % Defaults.GraphName
    )

    parser.add_argument(
        '-l',
        '--load',
        help='saved AMII configuration to load'
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

    args = parser.parse_args()

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    if args.ipc:
        ipc_comm_set = {os.path.dirname(ipc) for ipc in glob.glob(tempfile.gettempdir() + '/*/comm')}
        ipc_info_set = {os.path.dirname(ipc) for ipc in glob.glob(tempfile.gettempdir() + '/*/info')}
        ipc_list = list(ipc_comm_set.intersection(ipc_info_set))
        if ipc_list and ipc_list:
            if len(ipc_list) == 1:
                comm_addr = "ipc://%s/comm" % ipc_list[0]
                info_addr = "ipc://%s/info" % ipc_list[0]
            else:
                prompt = "Found %d ipc file descriptors:\n" % len(ipc_list)
                for i, ipc_name in enumerate(ipc_list):
                    prompt += " %d - %s\n" % (i, ipc_name)
                prompt += " %d - Quit\n\nPlease choose one: " % len(ipc_list)
                choice = input(prompt)
                try:
                    comm_addr = "ipc://%s/comm" % ipc_list[int(choice)]
                    info_addr = "ipc://%s/info" % ipc_list[int(choice)]
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
        comm_addr = "ipc://%s/comm" % args.ipc_dir
        info_addr = "ipc://%s/info" % args.ipc_dir
    else:
        comm, info = args.port
        comm_addr = "tcp://%s:%d" % (args.host, comm)
        info_addr = "tcp://%s:%d" % (args.host, info)

    try:
        return run_client(args.graph_name, comm_addr, info_addr, args.load, args.gui_mode)
    except KeyboardInterrupt:
        logger.info("Client killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
