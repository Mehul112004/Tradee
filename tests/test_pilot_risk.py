from decimal import Decimal as D
import unittest

from tradee.pilots.risk import RiskBook,replay_capital
from tradee.pilots.contracts import DAY


def trade(symbol='BTCUSDT',key='a',family='liquidity_sweep_v1'):
    return dict(plan=dict(symbol=symbol,opportunity_id=key,strategy=family),entry='100',expected_stopped_loss='2',
                entry_ms=2*DAY,status='unresolved',marks=[])


class CapitalRules(unittest.TestCase):
    def test_all_in_size_floor_notional_and_shared_correlation_risk(self):
        b=RiskBook('10000'); t=2*DAY
        self.assertEqual(D(b.admit(trade(),t)['quantity']),D('12.5'))
        self.assertEqual(D(b.admit(trade('ETHUSDT','b'),t)['quantity']),D('12.5'))
        self.assertEqual(D(b.report()['reserved_risk']),D('50'))
        self.assertFalse(b.admit(trade('BTCUSDT','c'),t)['admitted'])
        self.assertFalse(RiskBook('1').admit(trade(),t)['admitted'])

    def test_unresolved_never_releases_exposure_and_stale_mark_blocks_risk(self):
        b=RiskBook(); t=2*DAY; b.admit(trade(),t)
        self.assertEqual(b.admit(trade('ETHUSDT','b'),t+60001)['reason'],'mark_unknown')
        before=b.report()['reserved_risk']; b.advance(t+DAY)
        self.assertEqual(b.report()['reserved_risk'],before)
        self.assertEqual(b.admit(trade('BTCUSDT','c'),t+DAY)['reason'],'instrument_occupied')

    def test_two_negative_completed_family_trades_pause_and_calendar_reset_does_not_erase_history(self):
        b=RiskBook(); t=2*DAY
        for i in range(2):
            x=trade(key=str(i)); b.admit(x,t+i*1000); b.advance(t+i*1000+1,[(str(i),'-2','TRANSITION')],[str(i)])
        self.assertEqual(b.admit(trade(key='third'),t+3000)['reason'],'family_loss_pause')
        self.assertTrue(b.admit(trade(key='next-day'),t+DAY)['admitted'])
        self.assertEqual(len(b.closed),2)

    def test_three_losses_pause_day_across_families(self):
        b=RiskBook(); t=2*DAY
        for i,f in enumerate(('liquidity_sweep_v1','ema200_rejection_v1','key_level_retest_v1')):
            b.admit(trade(key=str(i),family=f),t+i*1000); b.advance(t+i*1000+1,[(str(i),'-2','DULL')],[str(i)])
        self.assertEqual(b.admit(trade(key='fourth'),t+4000)['reason'],'risk_pause')
        self.assertTrue(b.admit(trade(key='next'),t+DAY)['admitted'])

    def test_marked_loss_and_campaign_halt_count_carried_range_damage_and_overshoot(self):
        b=RiskBook(); t=2*DAY; b.admit(trade(),t)
        b.advance(t+1000,[('a','-8','HEALTHY_RANGE')])
        self.assertEqual(b.admit(trade('ETHUSDT','b'),t+1000)['reason'],'risk_pause')
        b.advance(t+2000,[('a','-60','DULL')])
        self.assertTrue(b.halted); self.assertGreater(D(b.report()['max_marked_drawdown']),D('.06'))
        self.assertEqual(D(b.report()['time_in_regime_pnl']['HEALTHY_RANGE']),D('-100'))
        self.assertEqual(b.admit(trade('ETHUSDT','b'),t+DAY)['reason'],'campaign_drawdown')

    def test_realized_net_booked_once_and_unresolved_tail_not_forced_closed(self):
        x=trade(); x.update(status='modeled_closed',exit_ms=2*DAY+60000,marks=[dict(at_ms=2*DAY,pnl='-.1',regime='TREND_UP'),dict(at_ms=2*DAY+60000,pnl='2',regime='DULL')])
        report=replay_capital([x]); self.assertEqual(D(report['cash']),D('10025'))
        self.assertEqual(report['open_unresolved_positions'],0)
        y=trade('ETHUSDT','b'); y['marks']=[dict(at_ms=2*DAY,pnl='-.1',regime='TREND_UP')]
        report=replay_capital([y]); self.assertEqual(report['open_unresolved_positions'],1)
        self.assertEqual(D(report['cash']),D('10000')); self.assertEqual(D(report['marked_equity']),D('9998.75'))


if __name__=='__main__': unittest.main()
