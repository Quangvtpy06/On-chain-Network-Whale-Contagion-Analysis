"""Human decisions are separate from AI lookup candidates and never backdated."""
import pandas as pd

VERIFIED_COLUMNS=['address','entity_name','entity_type','source_url','confidence',
    'verified_by','verified_at','label_available_at','effective_from','source_tier','verification_status']


def validate_decisions(frame):
    required=['address','entity_name','entity_type','source_url','confidence','verified_by',
              'verified_at','label_available_at','effective_from','source_opened_by_human','ethereum_address_confirmed','decision']
    if not set(required)<=set(frame):raise ValueError('Missing human decision fields')
    approved=frame.loc[frame.decision.eq('approve')].copy()
    if approved.address.duplicated().any():raise ValueError('Duplicate approved address')
    if not approved.address.str.fullmatch(r'0x[0-9a-f]{40}').all():raise ValueError('Invalid Ethereum address')
    for c in ['source_opened_by_human','ethereum_address_confirmed']:
        if not approved[c].map(lambda x:type(x) is bool and x).all():raise ValueError('Explicit human confirmation required')
    for c in ['entity_name','verified_by','source_url']:
        if not approved[c].fillna('').str.strip().ne('').all():raise ValueError('Missing human evidence metadata')
    if not approved.source_url.str.match(r'https://').all():raise ValueError('HTTPS source required')
    if not approved.confidence.isin(['low','medium','high']).all():raise ValueError('Invalid confidence')
    if not approved.entity_type.isin(['CEX','DEX','Bridge','Other','Contract','DeFi']).all():raise ValueError('Invalid entity type')
    dates={c:pd.to_datetime(approved[c],utc=True,errors='raise') for c in ['verified_at','label_available_at','effective_from']}
    if any(d.isna().any() for d in dates.values()):raise ValueError('Missing availability dates')
    if (dates['label_available_at']<dates['verified_at']).any():raise ValueError('Cannot backdate research availability before verification')
    if (dates['verified_at']>pd.Timestamp.now(tz='UTC')).any():raise ValueError('Future verification date')
    for c,d in dates.items():approved[c]=d.astype(str)
    approved['source_tier']=2;approved['verification_status']='human_verified'
    return approved[VERIFIED_COLUMNS].sort_values('address').reset_index(drop=True)


def available_labels(frame,cutoff):
    """Availability and effective date must both precede the prediction date."""
    if frame.empty:return frame
    cutoff=pd.Timestamp(cutoff)
    if cutoff.tzinfo is None:cutoff=cutoff.tz_localize('UTC')
    return frame.loc[frame.verification_status.eq('human_verified') &
        (pd.to_datetime(frame.label_available_at,utc=True)<cutoff) &
        (pd.to_datetime(frame.effective_from,utc=True)<cutoff)]
