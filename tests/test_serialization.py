import pytest
import numpy as np
from conftest import pyarrowtest
from ami.data import MsgTypes, CollectorMessage, Serializer, Deserializer, pa


@pytest.fixture(scope='module')
def serializer(request):
    return Serializer(protocol=request.param), Deserializer(protocol=request.param)


@pytest.fixture(scope='module')
def collector_msg():
    return CollectorMessage(mtype=MsgTypes.Datagram, identity=0, heartbeat=5,
                            name="fake", version=1, payload={'foo': 5, 'baz': 'bat', 'bar': [1, 2, 4]})


serializers = [None, 'dill', 'pickle']
if pa:
    serializers.append(pytest.param('arrow', marks=pyarrowtest))

@pytest.mark.parametrize("serializer",
                         serializers,
                         indirect=True)
@pytest.mark.parametrize("obj", [5, "test", np.arange(10)])
def test_default_serializer(serializer, obj):
    serializer, deserializer = serializer
    if isinstance(obj, np.ndarray):
        assert np.array_equal(deserializer(serializer(obj)), obj)
    else:
        assert deserializer(serializer(obj)) == obj


@pytest.mark.parametrize("serializer",
                         serializers,
                         indirect=True)
def test_default_serializer_message(serializer, collector_msg):
    serializer, deserializer = serializer
    assert deserializer(serializer(collector_msg)) == collector_msg
