from cryptoforge.parameter_stability import neighborhood_diagnostics


def grid(positive_all=False):
    return [{'parameters':{'family':'trend','sensitivity':.001,'hold':hold,'stop':stop,'target':target},
        'net_pnl':'1' if positive_all or (hold==24 and stop=='.02') else '-1',
        'stress_net_pnl':'.5' if positive_all or (hold==24 and stop=='.02') else '-2'}
        for hold in (12,24,48) for stop,target in (('.01','.02'),('.02','.04'))]


def test_isolated_best_development_point_is_identified_without_changing_selection():
    rows=neighborhood_diagnostics(grid())
    peak=next(r for r in rows if r['parameters']['hold']==24 and r['parameters']['stop']=='.02')
    assert peak['adjacent_configurations']==3 and peak['isolated_positive_peak']
    assert not peak['selection_changed'] and not peak['independent_profitability_established']


def test_positive_neighbors_and_group_filters_are_not_mixed():
    baseline=grid(True);filtered=[{**r,'parameters':{**r['parameters'],'entry_filter':'no_exit_conflict'},
        'net_pnl':'-1','stress_net_pnl':'-2'} for r in grid()]
    rows=neighborhood_diagnostics(baseline+filtered)
    assert all(r['adjacent_positive_after_stress']==r['adjacent_configurations'] for r in rows if not r['parameters'].get('entry_filter'))
    assert all(r['adjacent_positive_after_stress']==0 for r in rows if r['parameters'].get('entry_filter'))


def test_missing_neighbor_does_not_certify_isolated_peak():
    rows=neighborhood_diagnostics([r for r in grid() if not (r['parameters']['hold']==12 and r['parameters']['stop']=='.02')])
    peak=next(r for r in rows if r['parameters']['hold']==24 and r['parameters']['stop']=='.02')
    assert peak['expected_adjacent_configurations']==3
    assert peak['missing_adjacent_configurations']==1
    assert not peak['neighborhood_complete'] and not peak['isolated_positive_peak']


def test_single_configuration_has_no_neighborhood_evidence():
    row=neighborhood_diagnostics(grid(True)[:1])[0]
    assert row['expected_adjacent_configurations']==0
    assert not row['neighborhood_complete'] and not row['isolated_positive_peak']


def test_equivalent_decimal_spellings_are_the_same_configuration():
    import pytest
    row=grid()[0]
    equivalent={**row,'parameters':{**row['parameters'],'stop':'0.010','target':'0.020'}}
    with pytest.raises(ValueError,match='duplicate'):
        neighborhood_diagnostics([row,equivalent])


def test_nonfinite_barriers_are_rejected():
    import pytest
    row=grid()[0]
    with pytest.raises(ValueError,match='finite stop'):
        neighborhood_diagnostics([{**row,'parameters':{**row['parameters'],'stop':'NaN'}}])
