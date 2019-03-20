import pytest
import zmq
import numpy as np

from ami.data import MsgTypes, Datagram, CollectorMessage
from ami.comm import Store, ResultStore


@pytest.fixture(scope='function')
def store(request, ipc_dir):
    store = None

    if request.param:
        addr = "ipc://%s/resultstore" % ipc_dir
        store = (ResultStore(addr), addr)
    else:
        store = Store()

    # return the created store
    yield store

    # if it uses zmq then clean it up
    if hasattr(store, 'ctx'):
        store.ctx.destroy()


@pytest.mark.parametrize('store', [None], indirect=True)
def test_store_clear(store):
    # test that the store is empty
    assert not store
    assert not store.names
    assert not store.namespace

    # add something to the store
    store.put("test", "value")

    # test that the store is non-empty
    assert store
    assert store.names
    assert store.namespace

    # clear the store
    store.clear()

    # test that the store is empty
    assert not store
    assert not store.names
    assert not store.namespace

    # call clear on an empty store
    store.clear()

    # test that the store is empty
    assert not store
    assert not store.names
    assert not store.namespace


@pytest.mark.parametrize('obj, expected, store',
                         [
                            (('test', int), ('test', 5, False), None),
                            (('test', int), ('test', None, False), None),
                            (('test', None), ('test', 5, False), None),
                            (('test', None), ('test', 5, None), None),
                            (('test', str), ('test', "cat", False), None),
                            (('test', int), ('test', "cat", True), None),
                         ],
                         indirect=['store'])
def test_store_create(obj, expected, store):
    key, value, fail = expected

    store.create(*obj)

    # try creating the same thing again
    try:
        store.create(*obj)
        # an exception should be thrown so we don't get here
        assert False
    except ValueError:
        pass

    # check that put raises ValueError at the correct times
    try:
        store.put(key, value)
        # if fail is True we shouldn't get here
        assert not fail
    except TypeError:
        # if fail is False we shouldn't get here
        assert fail


@pytest.mark.parametrize('obj, expected, store',
                         [
                            (('test', 5), ('test', False), None),
                            (('test', None), ('test', True), None),
                            (('test', 'cat'), ('fail', True), None),
                         ],
                         indirect=['store'])
def test_store_get(obj, expected, store):
    key, fail = expected

    store.put(*obj)

    # check that get raises KeyError at the correct times
    try:
        store.get(key)
        # if fail is True we shouldn't get here
        assert not fail
    except KeyError:
        # if fail is False we shouldn't get here
        assert fail


@pytest.mark.parametrize('obj, expected, store',
                         [
                            (('test', 5), ('test', int, False), None),
                            (('test', None), ('test', None, True), None),
                            (('test', 'cat'), ('fail', str, True), None),
                         ],
                         indirect=['store'])
def test_store_getdgram(obj, expected, store):
    key, expected_type, fail = expected

    store.put(*obj)

    # check that get raises KeyError at the correct times
    try:
        dgram = store.get_dgram(key)
        # if fail is True we shouldn't get here
        assert not fail
        # check the dgram has the correct type
        assert isinstance(dgram, Datagram)
        assert dgram.name == key
        assert dgram.dtype == expected_type
        assert isinstance(dgram.data, expected_type)
    except KeyError:
        # if fail is False we shouldn't get here
        assert fail


@pytest.mark.parametrize('obj, expected',
                         [
                            (6, int),
                            ("apple", str),
                            ({"test": 4}, dict),
                            (np.zeros(5), (np.ndarray, 1)),
                            (np.zeros((5, 5)), (np.ndarray, 2)),
                         ])
def test_store_gettype(obj, expected):
    # check that get_type static method returns the expected type
    assert Store.get_type(obj) == expected


@pytest.mark.parametrize('obj, expected, store',
                         [
                            (6, int, None),
                            ('fake', str, None),
                            (None, None, None),
                            (np.zeros(5), (np.ndarray, 1), None),
                            (np.zeros((5, 5)), (np.ndarray, 2), None),
                         ],
                         indirect=['store'])
def test_store_put(obj, expected, store):

    store.put('test', obj)

    if obj is not None:
        if isinstance(expected, tuple):
            # check that the store has the obj and it is marked as the right type plus dimension
            assert 'test' in store.namespace
            assert np.array_equal(store.get('test'), obj)
            assert 'test' in store.names
            assert 'test' in store.types
            assert store.types['test'] == expected
        else:
            # check that the store has the obj and it is marked as the right type
            assert 'test' in store.namespace
            assert store.get('test') == obj
            assert 'test' in store.names
            assert 'test' in store.types
            assert store.types['test'] == expected
    else:
        # check that None doesn't get put into the store
        assert 'test' not in store.namespace
        assert 'test' not in store.names
        assert 'test' not in store.types


@pytest.mark.parametrize('obj, expected, store',
                         [
                            ({}, {}, None),
                            ({"test": 5}, {"test": int}, None),
                            ({"test": 5, "test2": "apple"}, {"test": int, "test2": str}, None),
                            ({"test": np.zeros(5)}, {"test": (np.ndarray, 1)}, None),
                         ],
                         indirect=['store'])
def test_store_update(obj, expected, store):

    store.update(obj)

    # if the expected dict is empty or not check that store is the same
    if expected:
        assert store.namespace
    else:
        assert not store.namespace

    # check that all the expected data is in the store
    assert set(store.namespace) == set(expected)
    # check that the data in the store is 'correct'
    for name, obj_type in expected.items():
        assert name in store.namespace
        if isinstance(obj_type, tuple):
            obj_type, ndims = obj_type
            assert np.array_equal(store.get(name), obj[name])
            assert isinstance(store.get(name), obj_type)
            assert name in store.names
            assert name in store.types
            assert store.types[name] == (obj_type, ndims)
        else:
            assert store.get(name) == obj[name]
            assert isinstance(store.get(name), obj_type)
            assert name in store.names
            assert name in store.types
            assert store.types[name] == obj_type


@pytest.mark.parametrize('obj, expected, store',
                         [
                            ({}, {}, True),
                            ({"t1": 1, "t2": "bad"}, {"t1": 1, "t2": "bad"}, True),
                            ({"t1": 1, "t2": "bad"}, {"t1": 1, "t2": "bad"}, True),
                         ],
                         indirect=['store'])
def test_store_collect(obj, expected, store):
    store, addr = store

    # create the fake collector
    collector = store.ctx.socket(zmq.PULL)
    collector.bind(addr)

    store.update(obj)

    # call collect several times changing the version and heartbeat
    for i in range(5):
        store.version = i // 2
        store.collect(0, i)

        msg = collector.recv_pyobj()
        # check that we get a collector message
        assert isinstance(msg, CollectorMessage)
        assert msg.mtype == MsgTypes.Datagram
        # check the version is correct
        assert msg.version == i // 2
        # check the heartbeat is correct
        assert msg.heartbeat == i
        # check the id is correct
        assert msg.identity == 0
        # check that the payload is correct
        assert msg.payload == expected

    collector.close()
