"""Describe adjacent development configurations; never tune on outer test."""
from decimal import Decimal
import json


def _cell(parameters):
    return (parameters['hold'], (Decimal(parameters['stop']), Decimal(parameters['target'])))


def neighborhood_diagnostics(results):
    groups={}
    for result in results:
        p=result['parameters'];net=Decimal(result['net_pnl']);stress=Decimal(result['stress_net_pnl'])
        if not net.is_finite() or not stress.is_finite():raise ValueError('finite development neighborhood results required')
        group=json.dumps({key:p.get(key) for key in ('family','sensitivity','entry_filter')},sort_keys=True)
        cells=groups.setdefault(group,{})
        cell=_cell(p)
        if not all(value.is_finite() for value in cell[1]):
            raise ValueError('finite stop and target required')
        if cell in cells:raise ValueError('duplicate development configuration')
        cells[cell]=result
    diagnostics=[]
    for cells in groups.values():
        values=list(cells.values())
        holds=sorted({r['parameters']['hold'] for r in values})
        barriers=sorted({_cell(r['parameters'])[1] for r in values},key=lambda item:(Decimal(item[0]),Decimal(item[1])))
        for result in values:
            p=result['parameters'];h=holds.index(p['hold']);b=barriers.index(_cell(p)[1])
            adjacent={(holds[i],barriers[b]) for i in (h-1,h+1) if 0<=i<len(holds)}
            adjacent|={(holds[h],barriers[i]) for i in (b-1,b+1) if 0<=i<len(barriers)}
            neighbors=[r for r in values if _cell(r['parameters']) in adjacent]
            tested={_cell(r['parameters']) for r in neighbors}
            missing=adjacent-tested
            complete=bool(adjacent) and not missing
            positive=sum(Decimal(r['net_pnl'])>0 and Decimal(r['stress_net_pnl'])>0 for r in neighbors)
            peak=Decimal(result['net_pnl'])>0 and Decimal(result['stress_net_pnl'])>0
            diagnostics.append({'parameters':p,'adjacent_configurations':len(neighbors),
                'expected_adjacent_configurations':len(adjacent),
                'missing_adjacent_configurations':len(missing),'neighborhood_complete':complete,
                'adjacent_positive_after_stress':positive,'isolated_positive_peak':peak and complete and positive==0,
                'tested_axes':['holding_bars','linked_stop_target_pair'],
                'sensitivity_neighbors_tested':False,'selection_changed':False,'independent_profitability_established':False})
    return diagnostics
