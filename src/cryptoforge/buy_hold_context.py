"""Fixed-stake passive context; different exit risk, never a strategy admission."""
from decimal import Decimal
from cryptoforge.spot_buy_math import spot_acquisition,spot_sale
from cryptoforge.trade_simulator import simulate_portfolio


def buy_hold_context(data,config,*,entry_index):
    if type(entry_index) is not int or entry_index<1 or any(len(rows)<=entry_index for rows in data.values()):
        raise ValueError('explicit next-open passive entry required')
    # Validate the same source history and equity grid without opening positions.
    simulate_portfolio(data,{},config)
    if not data:raise ValueError('nonempty passive basket required')
    times={rows[entry_index].open_time for rows in data.values()}
    ends={rows[-1].open_time for rows in data.values()}
    if len(times)!=1 or len(ends)!=1:raise ValueError('same passive entry/terminal times required')
    cash=config.capital;closed=[];open_positions=[];rejections=[];entries=[];acquired=[]
    for pair,rows in sorted(data.items()):
        if len(entries)>=config.max_positions:
            rejections.append({'pair':pair,'reason':'max_positions'});continue
        row=rows[entry_index];price=row.open*(1+config.spread_fraction/2)*(1+config.slippage)
        acquisition=spot_acquisition(stake=config.stake,price=price,quantity_step=config.quantity_step,
            fee_fraction=config.effective_entry_fee,fee_currency='quote')
        if acquisition.notional<config.min_notional:
            rejections.append({'pair':pair,'reason':'minimum_entry_notional'});continue
        if acquisition.gross_quantity>row.volume*config.max_volume_fraction:
            rejections.append({'pair':pair,'reason':'volume_limit'});continue
        if acquisition.cash_cost>cash:
            rejections.append({'pair':pair,'reason':'insufficient_cash'});continue
        cash-=acquisition.cash_cost
        entry={'pair':pair,'entry_at':row.open_time.isoformat(),'quantity':str(acquisition.net_quantity),
            'cost_basis':str(acquisition.cash_cost),'entry_fee_quote':str(acquisition.fee_quote_equivalent)}
        entries.append(entry)
        acquired.append((pair,rows,acquisition,entry))
    # Reserve every initial purchase before any terminal proceeds are available.
    for pair,rows,acquisition,entry in acquired:
        sell_price=rows[-1].close*(1-config.spread_fraction/2)*(1-config.slippage)
        sale=spot_sale(quantity=acquisition.net_quantity,price=sell_price,fee_fraction=config.effective_exit_fee,fee_currency='quote')
        if sale.notional<config.min_notional:
            open_positions.append({**entry,'reason':'unsellable_terminal_inventory','conditional_liquidation_value':'0'});continue
        cash+=sale.cash_proceeds
        closed.append({**entry,'terminal_at':rows[-1].open_time.isoformat(),'proceeds':str(sale.cash_proceeds),
            'net_pnl':str(sale.cash_proceeds-acquisition.cash_cost),'total_fees':str(acquisition.fee_quote_equivalent+sale.fee_amount)})
    basis=sum((Decimal(row['cost_basis']) for row in open_positions),Decimal(0))
    realized=sum((Decimal(row['net_pnl']) for row in closed),Decimal(0))
    if abs(cash+basis-config.capital-realized)>Decimal('1e-20'):raise ValueError('passive cash/basis accounting mismatch')
    return {'initial_capital':str(config.capital),'stake_per_pair':str(config.stake),'final_cash':str(cash),
        'realized_net_pnl':str(realized),'remaining_basis':str(basis),'open_positions':open_positions,
        'entries':entries,'closed_positions':closed,'rejections':rejections,
        'conditional_terminal_liquidation_equity':str(cash),'undeployed_initial_capital':str(config.capital-sum((Decimal(row['cost_basis']) for row in entries),Decimal(0))),
        'scope':'fixed_stake_passive_context_not_risk_matched_strategy','stop_and_target_policy_applied':False,
        'historical_execution_certified':False,'independent_evidence':False,'live_promotion_allowed':False}
