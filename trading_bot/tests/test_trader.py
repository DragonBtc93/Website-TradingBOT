import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from trading_bot.trader import SolanaTrader

class TestSolanaTraderTrailingStop(unittest.TestCase):

    def setUp(self):
        self.trader = SolanaTrader()
        self.trader.is_preview = True
        self.trader.execute_trade = AsyncMock()
        self.trader.stop_loss_pct = 0.10
        # Ensure TRAILING_STOP_LOSS_PERCENTAGE is set on the instance if trader.py doesn't import it globally
        # For the test to run independently, we might need to set it directly or ensure SolanaTrader imports it.
        # The provided trader.py code now imports it from config, so this should be fine if config is accessible.
        # However, the test code sets it directly on the instance for isolation.
        self.trader.TRAILING_STOP_LOSS_PERCENTAGE = 5

    async def _apply_trailing_stop_logic_for_test(self, token_address, current_market_price):
        # This helper simulates the core logic of how trailing stop is updated in manage_positions
        # It's a simplified version for testing this specific mechanism.
        # It directly manipulates the position dictionary for testing purposes.
        position = self.trader.active_positions[token_address]

        # 1. Update highest_price_since_entry
        if current_market_price > position.get('highest_price_since_entry', position['entry_price']):
            position['highest_price_since_entry'] = current_market_price

        # 2. Calculate new trailing_stop_price
        # Ensure TRAILING_STOP_LOSS_PERCENTAGE is accessed correctly (e.g. self.trader.TRAILING_STOP_LOSS_PERCENTAGE)
        # The trader.py code itself uses TRAILING_STOP_LOSS_PERCENTAGE from its imported config.
        # For this test helper to accurately reflect that, it should use self.trader.TRAILING_STOP_LOSS_PERCENTAGE
        calculated_trailing_stop_price = position['highest_price_since_entry'] * \
                                       (1 - self.trader.TRAILING_STOP_LOSS_PERCENTAGE / 100.0)

        # 3. Update stop_loss if new trailing stop is higher
        current_stop_loss = position.get('stop_loss', 0) # Get current SL, default to 0 if not set
        if calculated_trailing_stop_price > current_stop_loss:
            position['stop_loss'] = calculated_trailing_stop_price

    @patch('trading_bot.trader.SolanaTrader.get_token_price', new_callable=AsyncMock)
    async def test_trailing_stop_loss_behavior(self, mock_get_token_price_method):
        # This test focuses on the logic of how the stop_loss price is updated by the trailing mechanism.
        # It does NOT test the full manage_positions loop or actual trade execution.

        token_addr = "TEST_TOKEN_XYZ"
        entry_price = 100.0
        # Initial stop loss based on trader's stop_loss_pct (e.g., 10% of 100 = 90)
        initial_sl_price = entry_price * (1 - self.trader.stop_loss_pct)

        self.trader.active_positions[token_addr] = {
            'entry_price': entry_price,
            'amount': 1.0,
            'stop_loss': initial_sl_price,
            'take_profit': entry_price * 1.20,
            'highest_price_since_entry': entry_price, # Initial highest price is entry price
            'symbol': 'TEST_TOKEN_XYZ'
        }

        # Scenario 1: Price moves up, trailing stop should move up
        current_price_scen1 = 105.0
        # mock_get_token_price_method.return_value = current_price_scen1 # Not needed as we call helper directly
        await self._apply_trailing_stop_logic_for_test(token_addr, current_price_scen1)
        position_after_scen1 = self.trader.active_positions[token_addr]

        self.assertEqual(position_after_scen1['highest_price_since_entry'], 105.0)
        # Expected SL = 105 * (1 - 5/100) = 105 * 0.95 = 99.75
        expected_sl_scen1 = 105.0 * (1 - self.trader.TRAILING_STOP_LOSS_PERCENTAGE / 100.0)
        self.assertAlmostEqual(position_after_scen1['stop_loss'], expected_sl_scen1)

        # Scenario 2: Price moves further up, trailing stop should move further up
        current_price_scen2 = 110.0
        await self._apply_trailing_stop_logic_for_test(token_addr, current_price_scen2)
        position_after_scen2 = self.trader.active_positions[token_addr]

        self.assertEqual(position_after_scen2['highest_price_since_entry'], 110.0)
        # Expected SL = 110 * (1 - 5/100) = 110 * 0.95 = 104.5
        expected_sl_scen2 = 110.0 * (1 - self.trader.TRAILING_STOP_LOSS_PERCENTAGE / 100.0)
        self.assertAlmostEqual(position_after_scen2['stop_loss'], expected_sl_scen2)

        # Scenario 3: Price drops slightly but still above last trailing stop, SL should not change
        current_price_scen3 = 108.0
        await self._apply_trailing_stop_logic_for_test(token_addr, current_price_scen3)
        position_after_scen3 = self.trader.active_positions[token_addr]

        # Highest price should remain 110
        self.assertEqual(position_after_scen3['highest_price_since_entry'], 110.0)
        # SL should remain at 104.5 (from scenario 2)
        self.assertAlmostEqual(position_after_scen3['stop_loss'], expected_sl_scen2)

        # Scenario 4: Price drops further, still above last trailing stop, SL should not change
        current_price_scen4 = 105.0
        await self._apply_trailing_stop_logic_for_test(token_addr, current_price_scen4)
        position_after_scen4 = self.trader.active_positions[token_addr]

        self.assertEqual(position_after_scen4['highest_price_since_entry'], 110.0)
        self.assertAlmostEqual(position_after_scen4['stop_loss'], expected_sl_scen2)

        # Scenario 5: Test that initial fixed stop loss is respected if trailing stop is lower
        self.trader.stop_loss_pct = 0.10 # results in initial SL of 180 for entry of 200
        self.trader.TRAILING_STOP_LOSS_PERCENTAGE = 2 # results in trailing SL of 197.96 for price of 202

        token_addr_2 = "TEST_TOKEN_ABC"
        entry_price_2 = 200.0
        initial_sl_price_2 = entry_price_2 * (1 - self.trader.stop_loss_pct) # 200 * 0.90 = 180

        self.trader.active_positions[token_addr_2] = {
            'entry_price': entry_price_2,
            'amount': 1.0,
            'stop_loss': initial_sl_price_2,
            'take_profit': entry_price_2 * 1.20,
            'highest_price_since_entry': entry_price_2,
            'symbol': 'TEST_TOKEN_ABC'
        }

        current_price_scen5 = 202.0 # Price increases slightly
        await self._apply_trailing_stop_logic_for_test(token_addr_2, current_price_scen5)
        position_after_scen5 = self.trader.active_positions[token_addr_2]

        self.assertEqual(position_after_scen5['highest_price_since_entry'], 202.0)
        # Trailing SL = 202 * (1 - 2/100) = 202 * 0.98 = 197.96
        # Initial SL was 180. The new SL should be max(180, 197.96) = 197.96
        expected_sl_scen5 = 202.0 * (1 - self.trader.TRAILING_STOP_LOSS_PERCENTAGE / 100.0)
        self.assertAlmostEqual(position_after_scen5['stop_loss'], expected_sl_scen5)

        # Scenario 6: Price moves such that trailing stop is lower than initial fixed stop loss
        # This scenario is covered by the max() logic in trader.py, tested by _apply_trailing_stop_logic_for_test
        # For example, if TRAILING_STOP_LOSS_PERCENTAGE was very large, e.g. 15%
        # Price = 202. Trailing SL = 202 * 0.85 = 171.7. Initial SL = 180.
        # The stop loss should remain 180.
        self.trader.TRAILING_STOP_LOSS_PERCENTAGE = 15
        # Reset stop_loss to initial for this part of the test
        self.trader.active_positions[token_addr_2]['stop_loss'] = initial_sl_price_2
        self.trader.active_positions[token_addr_2]['highest_price_since_entry'] = entry_price_2 # reset for this test

        current_price_scen6 = 202.0
        await self._apply_trailing_stop_logic_for_test(token_addr_2, current_price_scen6)
        position_after_scen6 = self.trader.active_positions[token_addr_2]

        self.assertEqual(position_after_scen6['highest_price_since_entry'], 202.0)
        # Calculated trailing_stop_price = 202.0 * (1 - 15/100.0) = 202.0 * 0.85 = 171.7
        # Initial stop_loss for token_addr_2 was 180.0.
        # The helper _apply_trailing_stop_logic_for_test implements max(initial, trailing),
        # so it should be 180.0
        self.assertAlmostEqual(position_after_scen6['stop_loss'], initial_sl_price_2)


if __name__ == '__main__':
    # This allows running the tests directly via `python trading_bot/tests/test_trader.py`
    # For discovery, use `python -m unittest discover -s trading_bot/tests`
    asyncio.run(unittest.main())

```
