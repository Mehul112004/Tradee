"""Freeze C01 observations for causal decisions or explicit research assumptions."""
from copy import deepcopy
from tradee.c01 import Policy, ValidationError
from tradee.c01.domain import fingerprint
from tradee.c02.domain import integer


def capture(registry,dataset,config):
    policy=Policy(config.enabled_symbols,max(1,(config.max_metadata_age_ms+999)//1000))
    if config.metadata_mode=='research_assumption': times=[dataset['as_of_ms']]
    else:
        with registry.connection() as db:
            times=[r[0] for r in db.execute('SELECT DISTINCT observed_ms FROM observations WHERE accepted=1 AND observed_ms>? AND observed_ms<=? ORDER BY observed_ms',
                                         (dataset['start_ms'],dataset['as_of_ms']))]
        times=[dataset['start_ms'],*times]
    snapshots=[registry.universe(policy,t) for t in times]
    versions={d['version_hash']:registry.version(d['version_hash'])['spec'] for u in snapshots for d in u['decisions'] if d['version_hash']}
    return snapshots,versions


class MetadataBook:
    def __init__(self,snapshots,versions,cutoff):
        if not isinstance(snapshots,(list,tuple)) or not snapshots or not isinstance(versions,dict):
            raise ValidationError('Frozen C01 snapshots and versions required')
        self.snapshots=deepcopy(list(snapshots)); self.versions=deepcopy(versions)
        previous=-1
        for u in self.snapshots:
            if not isinstance(u,dict): raise ValidationError('Invalid C01 snapshot')
            doc=dict(u); h=doc.pop('snapshot_hash',None)
            if type(doc.get('schema_version')) is not int or doc['schema_version']!=1 or fingerprint(doc)!=h:
                raise ValidationError('Corrupt C01 universe snapshot')
            t=integer(doc.get('as_of_ms'),'metadata as-of')
            if not previous<t<=cutoff or not isinstance(u.get('decisions'),list): raise ValidationError('Unordered/future metadata snapshots')
            previous=t
            symbols=[]
            for d in u['decisions']:
                if not isinstance(d,dict) or not {'symbol','state','reasons','instrument_id','version_hash','last_observed_ms'}<=set(d):
                    raise ValidationError('Malformed metadata decision')
                symbols.append(d['symbol'])
                if d['state'] not in ('eligible','ineligible','unknown') or not isinstance(d['reasons'],list): raise ValidationError('Invalid metadata state')
                if d['last_observed_ms'] is not None and integer(d['last_observed_ms'],'metadata observation')>t:
                    raise ValidationError('Metadata observed after its snapshot')
                if d['version_hash'] is not None and d['version_hash'] not in self.versions: raise ValidationError('Missing pinned metadata version')
            if len(set(symbols))!=len(symbols): raise ValidationError('Duplicate metadata symbol')
        for h,spec in self.versions.items():
            if fingerprint(spec)!=h: raise ValidationError('Corrupt metadata version')

    def gate(self,instrument,symbol,when,config):
        known=[u for u in self.snapshots if u['as_of_ms']<=when]
        u=self.snapshots[-1] if config.metadata_mode=='research_assumption' else (known[-1] if known else None)
        reasons=[]
        if symbol not in config.enabled_symbols: reasons.append('symbol_not_enabled')
        if u is None: return reasons+['metadata_not_available'],None,None
        d=next((d for d in u['decisions'] if d['symbol']==symbol),None)
        if d is None or d['version_hash'] is None: return reasons+['missing_instrument_rules'],u['snapshot_hash'],None
        spec=self.versions[d['version_hash']]
        if d['instrument_id']!=instrument or spec.get('instrument_id')!=instrument: reasons.append('instrument_identity_mismatch')
        if d['state']!='eligible': reasons.extend(['metadata_ineligible',*('metadata:'+r for r in d['reasons'])])
        if not spec.get('scope_supported') or spec.get('issues') or spec.get('status')!='TRADING': reasons.append('unsupported_or_ineligible_instrument')
        if type(spec.get('onboardDate')) is not int or spec['onboardDate']>when: reasons.append('before_reported_onboard_time')
        if config.metadata_mode=='observed':
            if d['last_observed_ms'] is None or d['last_observed_ms']>when: reasons.append('metadata_not_available')
            elif when-d['last_observed_ms']>=config.max_metadata_age_ms: reasons.append('metadata_stale')
        return reasons,u['snapshot_hash'],d['version_hash']
