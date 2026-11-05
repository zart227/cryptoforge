"""Keep only unambiguous original entry decisions, independent of input ordering."""
import json


def unique_entry_contexts(decisions):
    contexts={};conflicts=set()
    for decision in decisions:
        if decision.get('decision')!='approve_entry':continue
        result=((decision.get('features') or {}).get('order') or {}).get('result') or {}
        order=result.get('orderId') if isinstance(result,dict) else None
        if not order:continue
        key=(decision['pair'],str(order))
        if key in conflicts:continue
        prior=contexts.get(key)
        if prior is not None and json.dumps(prior,sort_keys=True,default=str)!=json.dumps(decision,sort_keys=True,default=str):
            contexts.pop(key);conflicts.add(key)
        else:contexts[key]=decision
    return contexts,conflicts
