from copy import deepcopy
import pytest
from cryptoforge.walk_forward_inputs import validate_source_rows


def rows():
    return [['BTCUSDT','5',stamp,'100','101','99','100','10','1000'] for stamp in (0,300000)]


def test_exact_complete_source_range():
    validate_source_rows(rows(),'BTCUSDT',0,600000)


@pytest.mark.parametrize('kind',['missing','duplicate','wrong_market','invalid_price'])
def test_source_gaps_duplicates_and_invalid_prices_cannot_bind(kind):
    values=deepcopy(rows())
    if kind=='missing':values.pop()
    elif kind=='duplicate':values[1][2]=0
    elif kind=='wrong_market':values[1][0]='ETHUSDT'
    else:values[1][4]='NaN'
    with pytest.raises(ValueError):validate_source_rows(values,'BTCUSDT',0,600000)
