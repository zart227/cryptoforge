from scripts.find_archive_edge_cases import geometry


def row(symbol='ETHUSDT',stamp=300000,opened='100',high='101',low='99',close='100'):
    return (symbol,'5',stamp,opened,high,low,close,'10','1000')


def test_both_barriers_detected_at_exact_fixed_bounds():
    assert geometry(row(high='104',low='98'),None)==['both_barriers_from_bar_open']


def test_opening_drop_requires_adjacent_same_market_source():
    previous=row(stamp=0)
    current=row(opened='98',high='99',low='97',close='98')
    assert geometry(current,previous)==['opening_drop_at_least_two_percent']
    assert not geometry(current,row(symbol='BTCUSDT',stamp=0))
    assert not geometry(current,row(stamp=-300000))


def test_quiet_bar_does_not_invent_an_edge_case():
    assert not geometry(row(),row(stamp=0))
