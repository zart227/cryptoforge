from datetime import datetime,UTC
from cryptoforge.historical_event_review import explicit_utc,reviewed_proposals

URL='https://announcements.bybit.com/en/article/test/'
SHA='a'*64


def source(title,body,article=None):
    return {'title':title,'body':body,'published_at':'2026-05-20T08:00:00Z','article':article or {}}


def test_explicit_dates_and_delisting_choose_only_spot_section():
    assert explicit_utc('May 28, 2026, 8AM UTC')==datetime(2026,5,28,8,tzinfo=UTC)
    assert explicit_utc('2026-05-28 08:00:00 UTC')==datetime(2026,5,28,8,tzinfo=UTC)
    body='Spot: Trading of AAAUSDT,BBBUSDT ends after May 28, 2026, 8AM UTC. Deposits: end May 27, 2026, 8AM UTC.'
    result=reviewed_proposals(source('Delisting tokens',body),URL,SHA)
    assert len(result['events'])==2
    assert all(e.effective_at=='2026-05-28T08:00:00+00:00' for e in result['events'])


def test_listing_rewards_do_not_prove_usdt_pair_or_replace_trading_time():
    missing=source('Bybit to List AAA on Spot','AAA listing: May 25, 2026, 1PM UTC. AAA USDT prize pool.')
    assert reviewed_proposals(missing,URL,SHA)['status']=='pending_listing_quote_pair_evidence'
    explicit=source('Bybit to List AAA on Spot','New Spot Trading Pairs: AAA/USDT. AAA listing: May 25, 2026, 1PM UTC. Deposits: May 24, 2026, 10AM UTC.')
    result=reviewed_proposals(explicit,URL,SHA)
    assert result['events'][0].effective_at=='2026-05-25T13:00:00+00:00'


def test_ambiguous_dates_and_other_venue_do_not_create_facts():
    ambiguous=source('Delisting tokens','Spot: Trading of AAAUSDT ends May 28, 2026, 8AM UTC or May 29, 2026, 8AM UTC.')
    assert reviewed_proposals(ambiguous,URL,SHA)['events']==[]
    eu=source('Spot tick update','Bybit EU will adjust Spot pairs on May 28, 2026, 8AM UTC.')
    assert reviewed_proposals(eu,URL,SHA)['status']=='excluded_other_venue'


def test_time_first_tick_deadline_and_multiple_times_remain_ambiguous():
    assert explicit_utc('10AM UTC on Oct 17, 2025')==datetime(2025,10,17,10,tzinfo=UTC)
    table='<table><tr><td>Spot Pair</td><td>Tick Size (Before)</td><td>Tick Size (Adjusted)</td></tr><tr><td>ORDERUSDT</td><td>0.00001</td><td>0.0001</td></tr></table>'
    parsed=source('Updates on Tick Size for Spot Pairs',
        'Adjustments to Spot pairs by 10AM UTC on Oct 17, 2025. Please refer to the table.',
        {'content_html':table})
    parsed['published_at']='2025-10-15T05:20:25Z'
    result=reviewed_proposals(parsed,URL,SHA)
    assert result['events'][0].effective_at=='2025-10-17T10:00:00+00:00'
    assert result['events'][0].values=={'tick_size':'0.0001'}
    parsed['body']='Adjustments to Spot pairs by 10AM UTC on Oct 17, 2025 or Oct 18, 2025, 10AM UTC. Please refer to the table.'
    assert reviewed_proposals(parsed,URL,SHA)['events']==[]


def test_non_usdt_rule_scope_does_not_invent_usdt_or_numeric_events():
    table='<table><tr><td>Spot pair</td><td>Min order (before)</td><td>Min order (after)</td></tr><tr><td>ETHMNT</td><td>2</td><td>1.5</td></tr></table>'
    parsed=source('Minimum order value update for spot and margin pairs',
                  'Update Spot and Margin minimum order value.',{'content_html':table})
    result=reviewed_proposals(parsed,URL,SHA)
    assert result['status']=='excluded_non_usdt_rule_table' and result['events']==[]
    parsed['article']['content_html']=table.replace('ETHMNT','ETHUSDT')
    assert reviewed_proposals(parsed,URL,SHA)['status']=='pending_other_rule_or_scope_review'


def test_malformed_usdt_row_keeps_scope_review_open():
    table='<table><tr><td>ETHMNT</td><td>2</td><td>1.5</td></tr><tr><td>ETHUSDT</td><td>unknown</td></tr></table>'
    parsed=source('Minimum order value update for spot and margin pairs',
                  'Update Spot and Margin minimum order value.',{'content_html':table})
    assert reviewed_proposals(parsed,URL,SHA)['status']=='pending_other_rule_or_scope_review'


def test_pair_specific_listing_chooses_usdt_time_not_usdc():
    parsed=source('Bybit to List AAA on Spot',
        'AAA/USDT Listing: May 25, 2026, 1PM UTC AAA/USDC Listing: May 25, 2026, 2PM UTC')
    result=reviewed_proposals(parsed,URL,SHA)
    assert len(result['events'])==1 and result['events'][0].symbol=='AAAUSDT'
    assert result['events'][0].effective_at=='2026-05-25T13:00:00+00:00'


def test_numbered_sections_and_iso_am_date_keep_only_spot_time():
    parsed=source('Delisting of AAA',
        '1.Spot • Trading of AAA/USDT on Bybit Spot Spot trading platform ends 2026-5-28 8AM UTC. 2.Convert AAA ends May 29, 2026, 9AM UTC. 3.Deposits AAA ends May 27, 2026, 8AM UTC.')
    result=reviewed_proposals(parsed,URL,SHA)
    assert result['events'][0].effective_at=='2026-05-28T08:00:00+00:00'


def test_early_spot_delisting_and_earn_notice_have_separate_scope():
    parsed=source('Notice Regarding the Early Delisting of AAA Trading Pair',
        'Previously scheduled May 28, 2026. Spot Trading • Trading for AAA/USDT will be disabled on May 25, 2026, 3:30PM UTC. Convert • AAA ends May 25, 2026, 3:30PM UTC.')
    assert reviewed_proposals(parsed,URL,SHA)['events'][0].effective_at=='2026-05-25T15:30:00+00:00'
    earn=source('Notice of AAA delisting from Bybit On-Chain Earn',
        'Redeem via spot trading AAA/USDT before May 28, 2026, 8AM UTC.')
    assert reviewed_proposals(earn,URL,SHA)['status']=='excluded_non_spot_earn_notice'


def test_automatic_limits_are_recorded_as_gaps_not_invented_numbers():
    parsed=source('Enabling automated adjustments for selected spot trading parameters',
        'Bybit will enable automated adjustments for Spot trading starting Mar 20, 2026. Maximum quantity per market order will change without announcements.')
    result=reviewed_proposals(parsed,URL,SHA)
    assert result['events']==[] and result['coverage_gap']['numeric_values_reconstructed'] is False
    assert result['coverage_gap']['start_time_precision']=='day_only'
    assert 'maximum_market_quantity' in result['coverage_gap']['fields']
    parsed['body']=parsed['body'].replace('2026','2027')
    assert reviewed_proposals(parsed,URL,SHA)['status']=='pending_numeric_gap_date_review'


def test_suspension_observation_never_invents_actual_start():
    parsed=source('AAA/USDT Spot Trading Suspended',
        'Deposits and trading of AAA/USDT have been temporarily suspended. Withdrawals are not affected.')
    result=reviewed_proposals(parsed,URL,SHA)
    assert result['events'][0].kind=='suspension_observation'
    assert result['events'][0].effective_at==parsed['published_at'].replace('Z','+00:00')
    assert result['events'][0].evidence_scope=='publication_observation_not_suspension_start'


def test_aed_reward_usdt_is_not_a_usdt_quoted_pair():
    parsed=source('AED Spot pairs launch: Trade and win your share of USDT',
        'Available Spot trading pairs BTC/AED ETH/AED USDT/AED. Win 50000 USDT.')
    assert reviewed_proposals(parsed,URL,SHA)['status']=='excluded_non_usdt_aed_pairs'
    parsed['body']+=' Also BTC/USDT.'
    assert reviewed_proposals(parsed,URL,SHA)['status']=='pending_other_rule_or_scope_review'
