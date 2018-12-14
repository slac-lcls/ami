import sys
import dill
import IPython
import argparse

from ami.comm import Ports, GraphCommHandler


def run_console(addr, load):
    amicli = GraphCommHandler(addr)

    if load is not None:
        try:
            with open(load, 'rb') as cnf:
                amicli.update(dill.load(cnf))
        except OSError as os_exp:
                print(
                    "ami-console: problem opening saved graph configuration file:",
                    os_exp)
        except dill.UnpicklingError as dill_exp:
                print(
                    "ami-console: problem parsing saved graph configuration file (%s):" %
                    load, dill_exp)

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

    args = parser.parse_args()
    addr = "tcp://%s:%d" % (args.host, args.port)

    try:
        return run_console(addr, args.load)
    except KeyboardInterrupt:
        print("Client killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
