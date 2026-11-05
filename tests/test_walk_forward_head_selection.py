from scripts.select_walk_forward_validation import rank_eligible_heads


def choice(balanced,stress,net,threshold='0.5'):
    sha=('b' if balanced else 'a')*64
    return {'class_balance':balanced,'study_sha256':sha,
        'selection':{'selected_report_sha256':sha,'selected_threshold':threshold},
        'reports':[{'sha256':sha,'payload':{'candidate':{'threshold':threshold},
            'portfolio':{'initial_cash':'100','net_pnl':net,'stress_net_pnl':stress}}}]}


def test_no_eligible_head_does_not_force_a_winner():
    assert rank_eligible_heads([{'selection':{'selected_report_sha256':None}}]) is None


def test_stress_return_precedes_larger_ordinary_return():
    winner=rank_eligible_heads([choice(False,'1','10'),choice(True,'2','3')])
    assert winner['class_balance'] is True


def test_exact_tie_selects_unweighted_independently_of_order():
    left=choice(False,'1','2');right=choice(True,'1','2')
    assert rank_eligible_heads([left,right])['class_balance'] is False
    assert rank_eligible_heads([right,left])['class_balance'] is False
