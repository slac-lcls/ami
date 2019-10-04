import pytest
from ami.comm import AutoName


@pytest.fixture(scope='function')
def autonamer(request):
    return AutoName(request.param)


@pytest.mark.parametrize('prefix', ['test1', 'test2'])
def test_autoname_prefix(prefix):
    namer = AutoName(prefix)

    assert namer.prefix == prefix


@pytest.mark.parametrize('autonamer, name, expected',
                         [
                            ('_prefix1_', '_prefix1_test', True),
                            ('_prefix1_', '_prefix2_test', False),
                            ('_prefix1_', '_prefix1test', False),
                            ('_prefix1_', 'prefix1_test', False),
                         ],
                         indirect=['autonamer'])
def test_autoname_is_auto(autonamer, name, expected):
    assert autonamer.is_auto(name) == expected


@pytest.mark.parametrize('autonamer, name, expected',
                         [
                            ('_prefix1_', 'test1', '_prefix1_test1'),
                            ('_prefix2_', 'test2', '_prefix2_test2'),
                         ],
                         indirect=['autonamer'])
def test_autoname_mangle(autonamer, name, expected):
    # check that the unmangling returns the expected value
    assert autonamer.mangle(name) == expected


@pytest.mark.parametrize('autonamer, name, expected',
                         [
                            ('_prefix1_', '_prefix1_test1', 'test1'),
                            ('_prefix2_', '_prefix2_test2', 'test2'),
                         ],
                         indirect=['autonamer'])
def test_autoname_unmangle(autonamer, name, expected):
    # check that the mangling returns the expected value
    assert autonamer.unmangle(name) == expected


@pytest.mark.parametrize('autonamer, names, expected',
                         [
                            ('', ['test', ''], {'test', ''}),
                            ('_prefix1_', ['_prefix1_', '_prefix1_test'], {'', 'test'}),
                            ('_prefix1_', [], set()),
                            ('_prefix1_', ['_prefix1_test1'], {'test1'}),
                            ('_prefix2_', ['_prefix2_test2'], {'test2'}),
                            ('_prefix2_', ['_prefix3_test3'], set()),
                            ('_prefix1_', ['_prefix1_test1', '_prefix2_test2'], {'test1'}),
                            ('_prefix1_', {'_prefix1_test1', '_prefix2_test2'}, {'test1'}),
                         ],
                         indirect=['autonamer'])
def test_autoname_select(autonamer, names, expected):
    # check that the select returns the expected values
    assert autonamer.select(names) == expected
