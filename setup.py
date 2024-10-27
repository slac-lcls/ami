import sys
from setuptools import setup, find_packages


def get_version(pkg):
    version = '2.0.0'
    for arg in sys.argv:
        if arg.startswith('--version'):
            version = arg.split('=')[1]
            sys.argv.remove(arg)

    return version


setup(
    name='ami',
    version=get_version('ami'),
    description='LCLS analysis monitoring',
    long_description='The package used at LCLS-II for online analysis monitoring',
    author='Daniel Damiani',
    author_email='ddamiani@slac.stanford.edu',
    url='https://confluence.slac.stanford.edu/display/PSDMInternal/AMI+Replacement',
    packages=find_packages(),
    setup_requires=[
        'pytest-runner'
    ],
    install_requires=[
        'dill',
        'pyzmq',
        'numpy',
        'pyqtgraph',
        'networkfox',
        'ipython',
        'qtpy',
        'asyncqt>=0.8.0',
        'amityping>=1.1.2',
        'mypy',
        'setproctitle',
        'prometheus_client',
        'qtconsole',
#        'lark'
    ],
    tests_require=[
        'pytest',
        'pytest-asyncio',
        'pytest-qt'
    ],
    extras_require={
        'pva': ['p4p'],
        'hdf5': ['h5py'],
        'arrow': ['pyarrow>=0.17'],
        'lcls': ['psana', 'h5py', 'p4p'],
    },
    entry_points={
        'console_scripts': [
            'ami-worker = ami.worker:main',
            'ami-manager = ami.manager:main',
            'ami-node = ami.collector:node_main',
            'ami-global = ami.collector:global_main',
            'ami-client = ami.client:main',
            'ami-console = ami.console:main',
            'ami-local = ami.local:main',
            'ami-remote = ami.remote:main',
            'ami-export = ami.export:main',
            'ami-syncer = ami.sync:main',
            'ami-monitor = ami.monitor:main'
        ]
    },
    scripts=['ami/ami-mpi'],
    classifiers=[
        'Development Status :: 1 - Planning'
        'Environment :: Other Environment',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Scientific/Engineering :: Visualization',
        'Topic :: Utilities',
    ],
)
