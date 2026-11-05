"""Manual review-only native dot patch; no trainer/model execution or apply command."""
import difflib
import hashlib
import math
from operator import mul as _dot_mul
from pathlib import Path

from cryptoforge.research_training_diagnostics import digest

REVIEWED_NATIVE_SHA256='9afb8aab375ec786aa8f9c9a7f617a5db642e49fcfbf45d311a413a05e63aeb7'


def fast_dot(left,right):
    if len(left)!=len(right):raise ValueError('coefficient/feature dimensions differ')
    result=sum(map(_dot_mul,left,right))
    if not math.isfinite(result):raise ValueError('nonfinite model dot product')
    return result


def reviewed_patch(source):
    """Produce a patch for literal reviewed bytes, never execute or apply it."""
    if type(source) is not bytes or hashlib.sha256(source).hexdigest()!=REVIEWED_NATIVE_SHA256:
        raise ValueError('reviewed_native_model_source_required')
    original=source.decode();anchor='import math\n';old='    result=sum(a*b for a,b in zip(left,right))\n'
    if original.count(anchor)!=1 or original.count(old)!=1:raise ValueError('reviewed_dot_source_shape_required')
    proposed=original.replace(anchor,anchor+'from operator import mul as _dot_mul\n',1).replace(old,'    result=sum(map(_dot_mul,left,right))\n',1)
    patch=''.join(difflib.unified_diff(original.splitlines(True),proposed.splitlines(True),
        fromfile='a/src/cryptoforge/model_training.py',tofile='b/src/cryptoforge/model_training.py',n=1))
    description={'schema_version':'manual-native-dot-optimization-v1','base_source_sha256':REVIEWED_NATIVE_SHA256,
        'proposed_source_sha256':hashlib.sha256(proposed.encode()).hexdigest(),'patch_sha256':hashlib.sha256(patch.encode()).hexdigest(),
        'helper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'multiplication_order_changed':False,'builtin_sum_replaced':False,'new_third_party_dependency':False,
        'production_applied':False,'genuine_LLM_patch':False,'model_fit_prediction_or_new_allowance':False,
        'actual_training_speedup_or_strategy_quality_measured':False}
    return {'patch':patch,'review':{**description,'review_sha256':digest(description)}}
