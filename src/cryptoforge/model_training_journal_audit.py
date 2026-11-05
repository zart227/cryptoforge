"""Read-only analysis of one pinned, filtered training journal window."""
import ast
import math
from pathlib import Path
import re

from cryptoforge.local_source_provenance import digest,parse,read_file


def _finite(value,*,probability=False):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('finite metric required')
    if probability and not 0<=value<=1:raise ValueError('bounded probability metric required')
    return value


def audit_training_journal(path,pin):
    path=Path(path).absolute()
    if path.resolve()!=path or not re.fullmatch('[a-f0-9]{64}',str(pin)):raise ValueError('canonical pinned journal required')
    raw=read_file(path,maximum=65536)
    if digest(raw)!=pin:raise ValueError('journal hash mismatch')
    source=parse(raw)
    if (source.get('orders_placed') is not False or source.get('source_is_live_executions') is not False or
            not isinstance(source.get('filtered_journal'),str)):
        raise ValueError('filtered read-only training evidence required')
    lines=source['filtered_journal'].splitlines()
    if len(lines)>32 or any(len(x)>8192 for x in lines):raise ValueError('bounded training journal required')
    promotions=[x[len('promotion='):] for x in lines if x.startswith('promotion=')]
    models=[x for x in lines if x.startswith('model_training ')]
    if len(promotions)!=1 or len(models)!=1:raise ValueError('one training result and promotion required')
    try:promotion=ast.literal_eval(promotions[0])
    except (ValueError,SyntaxError,MemoryError,RecursionError):raise ValueError('invalid promotion record') from None
    if not isinstance(promotion,dict) or type(promotion.get('promoted')) is not bool:
        raise ValueError('typed promotion record required')
    if promotion.get('scope')!='fixed_candle_return_signal_screen_not_executed_cash_or_portfolio_income':
        raise ValueError('price-screen scope required')
    reason=promotion.get('reason');block=promotion.get('comparison_blocked_reason')
    if (not isinstance(reason,str) or not re.fullmatch('[a-z0-9_]{1,100}',reason) or
            (block is not None and (not isinstance(block,str) or not re.fullmatch('[a-z0-9_]{1,100}',block)))):
        raise ValueError('bounded promotion reasons required')
    incumbent=promotion.get('incumbent')
    if incumbent is not None and (not isinstance(incumbent,str) or not re.fullmatch('[A-Za-z0-9_.-]{1,160}',incumbent)):
        raise ValueError('bounded incumbent model version required')
    count=promotion.get('count');candidate=promotion.get('candidate')
    if type(count) is not int or not 0<=count<=1000000 or not isinstance(candidate,dict):raise ValueError('bounded promotion support required')
    signals=candidate.get('signals')
    if type(signals) is not int or not 0<=signals<=count:raise ValueError('bounded signal support required')
    accuracy=_finite(promotion.get('accuracy'),probability=True);baseline=_finite(promotion.get('majority_baseline'),probability=True)
    net=_finite(candidate.get('mean_net_signal_return')) if candidate.get('mean_net_signal_return') is not None else None
    cost=_finite(promotion.get('round_trip_cost'),probability=True)
    match=re.search(r'\bversion=([A-Za-z0-9_.-]{1,160})\s+pairs=(\d+)\b',models[0])
    test_match=re.search(r'\btest:n=(\d+):acc=([0-9.]+):precision=([0-9.]+):recall=([0-9.]+)',models[0])
    if not match or not test_match:raise ValueError('bounded model metrics required')
    pair_count=int(match[2]);test_n=int(test_match[1])
    if not 1<=pair_count<=100 or not 1<=test_n<=1000000:raise ValueError('bounded model sample counts required')
    test_acc=_finite(float(test_match[2]),probability=True);test_precision=_finite(float(test_match[3]),probability=True);test_recall=_finite(float(test_match[4]),probability=True)
    quality={}
    for line in lines:
        if not line.startswith('probability_quality '):continue
        fields={}
        for token in line.split()[1:]:
            key,sep,value=token.partition('=')
            if not sep or key in fields:raise ValueError('invalid quality fields')
            fields[key]=value
        required={'head','split','log_loss','baseline_log_loss','brier','baseline_brier','max_probability','signals','threshold'}
        if set(fields)!=required or fields['head'] not in ('long','short') or fields['split'] not in ('train','validation','test'):
            raise ValueError('quality scope differs')
        key=fields['head']+'_'+fields['split']
        if key in quality:raise ValueError('duplicate quality scope')
        try:
            loss=_finite(float(fields['log_loss']));base_loss=_finite(float(fields['baseline_log_loss']))
            brier=_finite(float(fields['brier']),probability=True);base_brier=_finite(float(fields['baseline_brier']),probability=True)
            maximum=_finite(float(fields['max_probability']),probability=True);threshold=_finite(float(fields['threshold']),probability=True)
            n=int(fields['signals'])
        except (ValueError,OverflowError):raise ValueError('invalid quality metric') from None
        if loss<0 or base_loss<0 or not 0<=n<=1000000:raise ValueError('invalid quality metric')
        quality[key]={'log_loss':loss,'baseline_log_loss':base_loss,'brier':brier,'baseline_brier':base_brier,
                      'signals':n,'max_probability':maximum,'threshold':threshold}
    if not {'long_test','short_test'}<=quality.keys():raise ValueError('test quality metrics missing')
    if digest(read_file(path,maximum=65536))!=pin:raise ValueError('journal changed during audit')
    return {'schema_version':'model-training-journal-audit-v1','input_sha256':pin,
            'requested_window_msk':source.get('requested_window_msk'),'journal_entry_timestamps_retained':False,
            'candidate_model_version':match[1],'incumbent_model_version':incumbent,'training_pair_count':pair_count,
            'model_test':{'examples':test_n,'accuracy':test_acc,'precision':test_precision,'recall':test_recall},
            'promotion':{'promoted':promotion['promoted'],'sample_count':count,'signals':signals,
                         'accuracy':accuracy,'majority_baseline':baseline,'mean_net_signal_return':net,
                         'assumed_round_trip_cost':cost,'reason':reason,'comparison_blocked_reason':block},
            'quality_test':{'long':quality['long_test'],'short':quality['short_test']},
            'scope':'filtered price-target training logs; test and promotion are distinct samples',
            'current_incumbent_comparison_established':False,'executed_cash_profit_established':False,
            'live_promotion_allowed':False,'orders_placed':False}
