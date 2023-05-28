from datetime import datetime, timedelta,timezone
import time
from typing import Optional
from sqlalchemy import desc, and_
import numpy as np  # noqa
import pandas as pd  # noqa
from pandas import DataFrame
from freqtrade.strategy import (BooleanParameter, CategoricalParameter, DecimalParameter,
                                IStrategy, IntParameter)
from technical.util import resample_to_interval, resampled_merge
from freqtrade.strategy import stoploss_from_open
# --------------------------------
# Add your lib to import here
# version "v12.0.100"

import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from datetime import datetime, timedelta
from freqtrade.persistence import Trade, Order
class sma_rsi_atr(IStrategy):
    temel = {"r": 10, 
           "kaldırac": 3,
           "atr_ratio": 1}
    
    limits = {
        "limitstop_inrow": 2,
        "limitstop_inrow_sec": 3600,
        "limitstop_perday": 6,
        "limitatr_min": 0.002
    }  

    indicators = {
        "supertrend": {
            "length": 10,
            "multiplier": 3.0
        },
        "sma": {
            "short": 50,
            "long": 200
        },
        "atr": {
            "length": 14
        }
    }
    
    use_custom_stoploss = True
    INTERFACE_VERSION = 3
    # Can this strategy go short?
    can_short: bool = True
   
    # Run "populate_indicators()" only for new candle.
    process_only_new_candles: bool = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    

    startup_candle_count: int = 500

    
    # Optional order type mapping.
  
    # Optional order time in force.
    order_time_in_force = {
        'entry': 'GTC',
        'exit': 'GTC'
    }
   
    def informative_pairs(self):
        """
        """
        return []
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
      
        if self.dp.runmode.value in ('live', 'dry_run'):
            ticker = self.dp.ticker(metadata['pair'])
            self.unlock_pair(metadata['pair'])
            dataframe.loc[dataframe.index[-1], "close"] = ticker['last']
        

        dataframe['sma_short'] = ta.SMA(dataframe,self.indicators['sma']['short'])
        dataframe['sma_long'] = ta.SMA(dataframe,self.indicators['sma']['long'])
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        # Calculate the ATR indicator
        dataframe['atr'] = ta.ATR(dataframe,self.indicators['atr']['length'])
        dataframe['atr_rel'] = dataframe['atr'] / dataframe['close']
            
        return dataframe
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with entry columns populated
        """
        
        dataframe.loc[
            (   
                (dataframe['close'] > dataframe['sma_long']  ) &
                (dataframe['atr_rel'] > self.limits["limitatr_min"] ) & 
                (dataframe['rsi'] < 30 ) & 
                (dataframe['volume'] > 0)  # Make sure Volume is not 0
            ),
            ['enter_long', 'enter_tag', 'enter_short']] = (1, 'yukseliyooooor', 0)
      
    
        dataframe.loc[
            (   
                (dataframe['close'] < dataframe['sma_long']  ) &
                (dataframe['atr_rel'] > self.limits["limitatr_min"] ) & 
                (dataframe['rsi'] > 70 ) & 
                (dataframe['volume'] > 0)  # Make sure Volume is not 0
            ),
            ['enter_long', 'enter_tag', 'enter_short']] = (0, 'dusuyor', 1)
        
        return dataframe
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe
    
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
                 **kwargs) -> float:

        return self.temel["kaldırac"]

    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime,
                        current_rate: float, current_profit: float, **kwargs) -> float:
        
        calculated_stoploss = self.temel["r"]/trade.stake_amount
        if current_profit > 3*calculated_stoploss:
            return calculated_stoploss/2
        else:
            return calculated_stoploss 
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: Optional[float], max_stake: float,
                            leverage: float, entry_tag: Optional[str], side: str,
                            **kwargs) -> float:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        current_candle = dataframe.iloc[-1].squeeze()
        calculated_stake = self.temel["atr_ratio"] * current_rate * self.temel["r"]/(current_candle["atr"]*self.temel["kaldırac"])
        allowed = self.count_limits(pair,current_time)
        if leverage == self.temel["kaldırac"] and allowed == 1:
            return (calculated_stake)
        else:
            return 0

    
    def count_limits(self, pair: str,current_time: datetime):
        trades_today= Trade.get_trades_proxy(pair=pair, is_open=False, close_date=current_time - timedelta(days=1))
        # son 24 saatlik kötü trade sayısı        
        badtrades_daily = 0
        # son 2 kötü trade sayısı
        badtrades_inrow = 0
        try:
            trades_today.sort(key=lambda x: x.close_date,reverse=True)
            for trade in trades_today:
                if trade.close_profit * trade.stake_amount < -self.temel["r"]/2:
                    badtrades_daily = badtrades_daily+1 
            if  badtrades_daily >= self.limits["limitstop_perday"]:
#                self.dp.send_msg("Son 24 Saatlik zarar limiti geçildiğinden işleme bir süre girilmeyecektir.",always_send=False)
                return 0
        except:
            badtrades_daily = 0               
        try:
            if (current_time.replace(tzinfo=None)-trades_today[0].close_date.replace(tzinfo=None)).total_seconds()  < self.limits["limitstop_inrow_sec"]:
                for trade in trades_today[0:self.limits["limitstop_inrow"]]:
                    if trade.close_profit * trade.stake_amount < -self.temel["r"]/2 :
                        badtrades_inrow = badtrades_inrow+1
                if  badtrades_inrow >= self.limits["limitstop_inrow"]:
#                    self.dp.send_msg("Peş peşe zarar limiti geçildiğinden 1 saat işleme girilmeyecek.",always_send=False)
                    return 0           
        except:
            badtrades_daily = 0
        return 1
       
      
   
