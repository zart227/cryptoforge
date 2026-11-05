"""Offline replay of retained original source events, without adopting a new DB.

The original source manifest, event bytes and head hashes retain their identity.
No claim is made that an old SQLite file's physical bytes were retained.
"""
from datetime import timedelta
from pathlib import Path
import sqlite3
import tempfile
from time import monotonic

from cryptoforge.local_source_provenance import canonical,digest,parse,stamp
from cryptoforge.reference_source_ledger import (
    SQL, _compute_forecast, _insert_versions, _rate_skip, _sources_ready,
    evaluate, source_summary,
)
from cryptoforge.reference_sources import INTERVAL_MS


class SourceReplay:
    def __init__(self, manifest, artifact, *, parent, maximum_database_bytes, maximum_seconds=60):
        self.manifest,self.artifact=manifest,artifact
        with tempfile.NamedTemporaryFile(prefix='reference-prefix-',suffix='.sqlite',dir=parent,delete=False) as f:
            self.path=Path(f.name)
        self.db=sqlite3.connect(self.path)
        self.db.execute(f'PRAGMA max_page_count={maximum_database_bytes//4096}')
        self.db.execute(SQL['versions']);self.db.execute(SQL['forecasts'])
        self.seq=0;self.head=digest(canonical(manifest));self.pending=None
        self.windows={};self.last_windows={};self.last_poll=None;self.latest_forecasts=[]
        self.last_time=stamp(manifest['registered_at']);self.started=monotonic();self.maximum_seconds=maximum_seconds
        self.missing_polls=0;self.rate_pauses=0
        self.version_count=0;self.forecast_count=0

    def close(self):
        self.db.close();self.path.unlink(missing_ok=True)

    def __enter__(self):return self
    def __exit__(self,*args):self.close()

    def feed(self, row):
        if monotonic()-self.started>self.maximum_seconds:
            raise ValueError('retained source replay wall budget exhausted')
        seq,kind,raw,previous,head=row
        if len(raw)>self.manifest['policy']['maximum_event_bytes']:
            raise ValueError('retained original event byte budget exceeded')
        value=parse(raw)
        keys={'poll_prepared':{'poll_id','anchor_ms','prepared_at','pairs'},
            'source_response':{'poll_id','observation','derived','request_performed','request_started_at','recorded_at'},
            'poll_complete':{'poll_id','anchor_ms','responses','completed_at','cooldown_until'},
            'forecast':{'forecast_id','payload','recorded_at'}}
        if kind not in keys or type(value) is not dict or set(value)!=keys[kind] or seq>self.manifest['policy']['maximum_events']:
            raise ValueError('original retained source event schema/budget differs')
        expected=digest(canonical(dict(sequence=seq,kind=kind,payload=value,previous_sha256=self.head)))
        if seq!=self.seq+1 or previous!=self.head or expected!=head or raw!=canonical(value):
            raise ValueError('retained source sequence/hash chain differs')
        if kind=='poll_prepared':
            at=stamp(value['prepared_at']);anchor=value['anchor_ms']
            identity=digest(canonical(dict(anchor_ms=anchor,prepared_at=value['prepared_at'],head=self.head)))
            if (self.pending is not None or value['pairs']!=self.manifest['pairs'] or at<self.last_time
                    or identity!=value['poll_id'] or anchor!=int(at.timestamp()*1000)//INTERVAL_MS*INTERVAL_MS
                    or not stamp(self.manifest['start'])<=at<=stamp(self.manifest['end'])
                    or self.last_poll and (anchor<=self.last_poll['anchor_ms'] or at<stamp(self.last_poll['cooldown_until']))):
                raise ValueError('retained source poll ordering/window differs')
            first=(int(stamp(self.manifest['start']).timestamp()*1000)//INTERVAL_MS*INTERVAL_MS
                if self.last_poll is None else self.last_poll['anchor_ms']+INTERVAL_MS)
            slots=max(0,(anchor-first)//INTERVAL_MS)
            paused=0
            if self.last_poll is not None:
                cooldown=int(stamp(self.last_poll['cooldown_until']).timestamp()*1000)
                paused=min(slots,max(0,(cooldown-first+INTERVAL_MS-1)//INTERVAL_MS))
            self.missing_polls+=slots-paused;self.rate_pauses+=paused
            self.pending=value;self.responses=[];self.windows={};self.expected_cooldown=at
            self.last_response_time=at;self.rate_blocked=False
        elif kind=='source_response':
            pending=self.pending
            if pending is None or value['poll_id']!=pending['poll_id']:
                raise ValueError('retained orphan source response')
            observation=value['observation'];pair=observation['pair'];recorded=stamp(value['recorded_at'])
            derived=evaluate(observation,started=value['request_started_at'],recorded=value['recorded_at'])
            if (canonical(source_summary(derived))!=canonical(value['derived']) or len(self.responses)>=len(pending['pairs'])
                    or pair!=pending['pairs'][len(self.responses)] or observation['anchor_ms']!=pending['anchor_ms']
                    or value['request_performed'] is not (not self.rate_blocked)
                    or self.rate_blocked and observation!=_rate_skip(pair,pending['anchor_ms'],stamp(value['request_started_at']))
                    or not self.last_response_time<=stamp(value['request_started_at'])<=recorded<=stamp(self.manifest['end'])
                    or derived['known_at'] is not None and not stamp(pending['prepared_at'])<=stamp(derived['known_at'])<=recorded):
                raise ValueError('retained original source response/availability differs')
            if derived['rate_limited']:
                self.expected_cooldown=max(self.expected_cooldown,recorded+timedelta(minutes=10));self.rate_blocked=True
            self.responses.append([pair,seq]);self.windows[pair]={**value,'derived':derived,'event_seq':seq}
            self.last_response_time=recorded;before=self.db.total_changes
            _insert_versions(self.db,derived['rows'],seq);self.version_count+=self.db.total_changes-before
        elif kind=='poll_complete':
            pending=self.pending;done=stamp(value['completed_at'])
            if (pending is None or value['poll_id']!=pending['poll_id'] or value['anchor_ms']!=pending['anchor_ms']
                    or value['responses']!=self.responses or len(self.responses)!=len(self.manifest['pairs'])
                    or not self.last_response_time<=done<=min(stamp(self.manifest['end']),stamp(pending['prepared_at'])+timedelta(seconds=75))
                    or stamp(value['cooldown_until'])!=self.expected_cooldown):
                raise ValueError('retained incomplete or invalid source poll')
            self.pending=None;self.last_time=done;self.last_poll=value
            self.last_windows=self.windows;self.latest_forecasts=[]
        elif kind=='forecast':
            p=value['payload'];at=stamp(p['predicted_at']);recorded=stamp(value['recorded_at'])
            if (self.pending is not None or not self.last_windows or self.artifact is None
                    or at<self.last_time or not at<=recorded<=min(stamp(self.manifest['end']),at+timedelta(seconds=5))
                    or not _sources_ready(self.last_windows,at)):
                raise ValueError('retained forecast source unavailable')
            identity=digest(canonical(dict(artifact=self.manifest['artifact_sha256'],pair=p['pair'],bar=p['input_bar_open_ms'])))
            if identity!=value['forecast_id'] or canonical(_compute_forecast(self.artifact,p['pair'],self.last_windows,at))!=canonical(p):
                raise ValueError('retained original forecast/source linkage differs')
            self.db.execute('INSERT INTO forecasts VALUES (?,?,?)',(identity,canonical(p),seq))
            self.forecast_count+=1
            self.latest_forecasts.append(value);self.last_time=recorded
        else:raise ValueError('unknown retained original source event')
        if (self.version_count>self.manifest['policy']['maximum_versions']
                or self.forecast_count>self.manifest['policy']['maximum_forecasts']):
            raise ValueError('retained source index budget exceeded')
        self.seq=seq;self.head=head

    def view(self):
        if self.pending is not None:raise ValueError('retained source prefix ends inside a poll')
        windows={}
        for pair,w in sorted(self.last_windows.items()):
            rows=[]
            for row in w['derived']['rows']:
                known,seq=self.db.execute('SELECT known_at,event_seq FROM versions WHERE source_id=? AND version=?',
                    (row['source_id'],row['version_sha256'])).fetchone()
                rows.append(dict(row,first_seen_at=known,first_seen_event_sequence=seq))
            windows[pair]=dict(w,derived=dict(w['derived'],rows=rows))
        return dict(source_sequence=self.seq,source_head_sha256=self.head,
            original_source_observed_at=self.last_time.isoformat(),windows=windows,
            forecasts=self.latest_forecasts,missing_source_poll_slots=self.missing_polls,
            explicit_rate_pause_slots=self.rate_pauses)
