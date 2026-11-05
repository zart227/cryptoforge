"""Independent integer/rational oracle: exact budgets, fees and residual basis."""
from decimal import Decimal as D,Inexact,localcontext
from fractions import Fraction as F
import ast
from pathlib import Path

import pytest
from cryptoforge.paper_replay_math_v2 import acquisition,sale,allocate,decimal,floor_quantity,total,product,difference,arithmetic,number


@pytest.mark.parametrize('budget,price,step,fee',[
 ('6','17','1e-28','0'),('6','100.05','.0001','.0018'),('123.45','3.14159','1e-12','.0025'),
 ('1e-30','1e-20','1e-20','.5'),('12','3','1','0'),('1','100','1','0'),
])
@pytest.mark.parametrize('currency',['base','quote'])
def test_maximal_affordable_steps_and_fee_currency(budget,price,step,fee,currency):
    result=acquisition(*map(D,(budget,price,step,fee)),fee_currency=currency)
    unit=F(D(price))*F(D(step))*(1+F(D(fee)) if currency=='quote' else 1)
    units=F(result['gross'])/F(D(step))
    assert units.denominator==1 and F(result['cost'])<=F(D(budget))<(units+1)*unit
    expected_net=F(result['gross'])*(1-F(D(fee))) if currency=='base' else F(result['gross'])
    assert F(result['quantity'])==expected_net
    assert F(result['fee'])==F(result['gross'])*F(D(price))*F(D(fee))


@pytest.mark.parametrize('precision',[3,7,28,90])
def test_oracle_is_independent_of_caller_decimal_precision_and_traps(precision):
    with localcontext() as context:
        context.prec=precision;context.traps[Inexact]=True
        result=acquisition(D(6),D(17),D('1e-28'),D('.0018'))
        cash=difference(D(6),result['cost'])
        assert F(cash)+F(result['cost'])==6 and cash>=0
        allocated=allocate(D(1),D(1),D(3))
        assert F(allocated)==F(10**512//3,10**512)
        assert total((allocated,difference(D(1),allocated)))==1


@pytest.mark.parametrize('basis,sold,qty', [('1','1','3'),('6.01234','.0067','.09999'),('1e-100','1','17'),('0','3','4')])
def test_partial_allocation_is_registered_floor_and_full_sale_keeps_all_residual(basis,sold,qty):
    b,s,q=map(D,(basis,sold,qty));allocated=allocate(b,s,q)
    exact=F(b)*F(s)/F(q)
    assert F(allocated)<=exact<F(allocated)+F(1,10**512)
    residual=difference(b,allocated)
    assert allocate(residual,difference(q,s),difference(q,s))==residual
    assert F(allocated)+F(residual)==F(b)


def test_cash_basis_and_realized_pnl_conserve_across_many_partial_closes():
    cash=D('94');basis=D(6);qty=D(3);realized=D(0)
    for sold in [D('.1')]*29+[D('.1')]:
        portion=allocate(basis,sold,qty);proceeds,fee=sale(sold,D('2.1'),D('.0018'))
        cash=total((cash,proceeds));realized=total((realized,difference(proceeds,portion)))
        qty=difference(qty,sold);basis=difference(basis,portion)
        assert F(cash)+F(basis)==100+F(realized)
        assert basis>=0 and qty>=0
    assert basis==qty==0


@pytest.mark.parametrize('text',['NaN','Infinity','-1','1e-129','1e129','1.'+'1'*129])
def test_number_bounds(text):
    with pytest.raises((ValueError,ArithmeticError)):number(text)


def test_nonterminating_and_oversized_outputs_cannot_expand_without_limit():
    with pytest.raises(ValueError):decimal(F(1,3))
    with pytest.raises(ValueError):decimal(F(1,10**4097))
    with pytest.raises(ValueError):allocate(D(1),D(4),D(3))
    with pytest.raises(ValueError):acquisition(D(6),D(17),D('.001'),D(1))
    assert floor_quantity(D('.29999999999999999999999999999999'),D('.1'))==D('.2')


def test_oracle_module_imports_no_producer_code():
    tree=ast.parse((Path(__file__).resolve().parents[1]/'src/cryptoforge/paper_replay_math_v2.py').read_text())
    imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert imports==['contextlib','decimal','fractions']
