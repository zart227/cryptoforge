"""Registered development-only comparison of declared ridge training windows."""
from dataclasses import asdict
from math import isfinite

from cryptoforge.net_regression import fit_net_regressor, evaluate_net_regressor, NET_TARGETS
from cryptoforge.research_attempts import identity, ResearchAttempts
from cryptoforge.model_training import fit_standardizer
from cryptoforge.source_contract import source_hashes, assert_source_dependencies
from cryptoforge.train_window import prepare_training_window
from cryptoforge.training_cohorts import net_training_cohorts
from cryptoforge.net_training_snapshot import save_net_training_snapshot
from cryptoforge.training_snapshot import save_runtime_sources


def window_study_dependencies():
    return {'runner': run_train_window_study,
        'window': prepare_training_window, 'net_head': fit_net_regressor,
        'net_evaluation': evaluate_net_regressor, 'source_guard': assert_source_dependencies,
        'ledger': ResearchAttempts.register, 'standardizer': fit_standardizer,
        'cohort_diagnostics': net_training_cohorts,
        'net_input_snapshot':save_net_training_snapshot,'runtime_snapshot':save_runtime_sources}


def window_study_sources():
    return source_hashes(window_study_dependencies())


def run_train_window_study(train, validation, *, grid, train_end, validation_end,
                           target_version, ridge, ledger, protocol_id,
                           protocol_version, maximum_per_family, study_context=None):
    """Consume observed examples only; outputs measure error, never cash profit.

    Archives, label provenance and resource guards belong to the calling runner.
    Every grid cell has explicit window_days and half_life_days (None = uniform).
    The validation set is fixed across cells, with entry strictly after train_end.
    """
    for timestamp in (train_end, validation_end):
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError('aware study boundaries required')
    if train_end >= validation_end:
        raise ValueError('ordered study boundaries required')
    if target_version not in NET_TARGETS or not isfinite(ridge) or ridge <= 0:
        raise ValueError('explicit net target and positive ridge required')
    train, validation = tuple(train), tuple(validation)
    if len(validation) < 2:
        raise ValueError('fixed nonempty validation required')
    for row in validation:
        if (row.open_time.tzinfo is None or row.open_time.utcoffset() is None
                or row.label_end_time is None or row.label_end_time.tzinfo is None
                or not train_end < row.open_time <= row.label_end_time <= validation_end):
            raise ValueError('validation must follow train cutoff with available labels')
    candidates=[]
    prepared={}
    for cell in grid:
        if set(cell) != {'window_days','half_life_days'}:
            raise ValueError('explicit window and half life specification required')
        candidate={'family':'ridge-net-training-window', **cell}
        # Canonical numeric spellings prevent .5 / 0.50 duplicating a trial.
        candidate['window_days']=float(cell['window_days'])
        candidate['half_life_days']=(None if cell['half_life_days'] is None else float(cell['half_life_days']))
        key=identity(candidate)
        if key in prepared:
            raise ValueError('duplicate effective training window')
        prepared[key]=prepare_training_window(train,train_end=train_end,
            window_days=cell['window_days'],half_life_days=cell['half_life_days'])
        candidates.append(candidate)
    if not candidates:
        raise ValueError('declared nonempty window grid required')
    sources=window_study_sources()
    directory=ledger.path.parent/'net-window-inputs'
    snapshot=save_net_training_snapshot(directory,train=train,validation=validation,
        target_version=target_version,metadata={'train_end':train_end.isoformat(),
            'validation_end':validation_end.isoformat()})
    runtime=save_runtime_sources(directory/'runtime',window_study_dependencies(),sources)
    manifest={'grid':candidates, 'base_config':{'ridge':ridge,'target_version':target_version},
        'study_context':study_context,
        'implementation_hashes':sources,'train_end':train_end.isoformat(),
        'validation_end':validation_end.isoformat(),
        'train_snapshot_sha256':identity([asdict(row) for row in train]),
        'validation_snapshot_sha256':identity([asdict(row) for row in validation]),
        'original_input_snapshot':snapshot,'original_runtime_sources':runtime,
        'scope':'development_net_prediction_error_only','outer_test_evaluated':False,
        'historical_reserved_final_compatible':False}
    study=ledger.register(manifest,protocol_id=protocol_id,protocol_version=protocol_version,
                          maximum_per_family=maximum_per_family)
    results=[]
    for candidate in candidates:
        prior=ledger.result(study,candidate)
        if prior is not None:
            results.append(prior)
            continue
        window=prepared[identity(candidate)]
        try:
            model=fit_net_regressor(window.rows,target_version=target_version,ridge=ridge,
                as_of=train_end,sample_weights=window.weights)
            metrics=evaluate_net_regressor(model,validation,as_of=validation_end,
                                            target_version=target_version)
            if sources != window_study_sources():
                raise ValueError('study source changed during fitting')
            result={'parameters':candidate,'metrics':metrics,'model':asdict(model),
                'train_count':len(window.rows),'effective_sample_size':window.effective_sample_size,
                'train_cohorts':net_training_cohorts(window.rows,as_of=train_end,target_version=target_version),
                'training_rows_sha256':identity([asdict(row) for row in window.rows]),
                'sample_weights_sha256':identity(window.weights)}
            ledger.record(study,candidate,result)
            # Return exactly the persisted JSON representation on first and cached runs.
            results.append(ledger.result(study,candidate))
        except Exception as exc:
            ledger.record(study,candidate,{'error':type(exc).__name__},failed=True)
            raise
    if sources != window_study_sources():
        raise ValueError('study source changed during evaluation')
    return {'study_sha256':study,'manifest':manifest,'results':results,
            'validation_cohorts':net_training_cohorts(validation,as_of=validation_end,target_version=target_version),
            'selection_performed':False,'live_promotion_allowed':False,
            'independent_profitability_established':False}
