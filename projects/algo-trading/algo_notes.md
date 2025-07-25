# 📊 Core Tools & Calculations in Algorithmic Trading

This section documents the most essential tools, indicators, and calculations used in algorithmic and quantitative trading strategies. These are useful for both traditional strategies and machine learning–enhanced approaches.

---

## 1. 🧮 Moving Averages (SMA, EMA)

**What it is:**  
A rolling average of past prices, used to smooth noise and detect trends.

**When it's used:**  
- Trend detection  
- Entry/exit signals (e.g., golden cross, death cross)

**Formulas:**
- **Simple Moving Average (SMA):** 
 
  \[
  \text{SMA}_t = \frac{1}{n} \sum_{i=0}^{n-1} P_{t-i}
  \]

**Popularity:** ⭐⭐⭐⭐⭐

---

## 2. 📈 Relative Strength Index (RSI)

**What it is:**  
A momentum oscillator measuring the speed and change of price movements (range 0–100).

**When it's used:**  
- Overbought (>70) / Oversold (<30) detection  
- Mean-reversion strategies

**Formula:**
\[
\text{RSI} = 100 - \frac{100}{1 + \frac{\text{Average Gain}}{\text{Average Loss}}}
\]

**Popularity:** ⭐⭐⭐⭐

---

## 3. 📊 MACD (Moving Average Convergence Divergence)

**What it is:**  
Momentum indicator based on the difference between short and long EMAs.

**When it's used:**  
- Trend reversals  
- Crossover-based entry/exit signals

**Formula:**
\[
\text{MACD} = \text{EMA}_{12} - \text{EMA}_{26}
\]
\[
\text{Signal Line} = \text{EMA}_{9}(\text{MACD})
\]

**Popularity:** ⭐⭐⭐⭐

---

## 4. ⚠️ Bollinger Bands

**What it is:**  
Volatility bands placed above and below a moving average using standard deviation.

**When it's used:**  
- Volatility breakouts  
- Mean reversion

**Formula:**
\[
\text{Upper Band} = \text{MA} + 2\sigma,\quad \text{Lower Band} = \text{MA} - 2\sigma
\]

**Popularity:** ⭐⭐⭐⭐

---

## 5. 🧠 Sharpe Ratio

**What it is:**  
A risk-adjusted return metric comparing excess return to volatility.

**When it's used:**  
- Strategy comparison  
- Backtesting performance evaluation

**Formula:**
\[
\text{Sharpe Ratio} = \frac{R_p - R_f}{\sigma_p}
\]

**Popularity:** ⭐⭐⭐⭐⭐

---

## 6. 📉 Value at Risk (VaR)

**What it is:**  
Estimates the worst expected portfolio loss over a given time frame at a certain confidence level.

**When it's used:**  
- Risk management  
- Position sizing

**Example:**  
95% daily VaR = \$10,000 → 5% chance of losing more than \$10,000 in a day.

**Popularity:** ⭐⭐⭐⭐

---

## 7. 📐 Expected Returns & Covariance

**What it is:**  
Statistical estimates used in portfolio optimization and risk analysis.

**When it's used:**  
- Portfolio optimization (Markowitz)  
- Risk modeling

**Formulas:**
- Expected Return:  
  \[
  \mu_i = \frac{1}{T} \sum_{t=1}^T r_{i,t}
  \]
- Covariance Matrix:  
  \[
  \Sigma_{ij} = \text{Cov}(r_i, r_j)
  \]

**Popularity:** ⭐⭐⭐⭐⭐

---

## 8. 🔄 Backtesting Frameworks

**What they are:**  
Simulation engines that test a strategy on historical data.

**Popular tools:**  
- Backtrader  
- Zipline (legacy)  
- QuantConnect (cloud)

**When it's used:**  
- Validating new strategies  
- Measuring drawdown, CAGR, Sharpe, etc.

**Popularity:** ⭐⭐⭐⭐⭐

---

## 9. 🧪 Alpha Factors & Feature Engineering

**What they are:**  
Quantitative signals (features) used in both rule-based and ML-driven trading.

**Examples:**  
- Momentum (12-month return)  
- Volatility (rolling std)  
- Volume/liquidity indicators

**When it's used:**  
- Predictive modeling  
- Portfolio sorting  
- ML model inputs

**Popularity:** ⭐⭐⭐⭐⭐

---

## 10. 🤖 Machine Learning Models

**What they are:**  
Predictive and generative models trained on financial data.

**Common Models:**
- Random Forest, XGBoost  
- Logistic Regression  
- LSTM / GRU (deep learning)  
- k-Means (unsupervised)

**When it's used:**  
- Directional prediction  
- Regime classification  
- RL for dynamic allocation

**Popularity:** ⭐⭐⭐⭐

---

## 📌 Summary Table

| Tool/Metric             | Purpose                         | When Used                   | Popularity |
|-------------------------|----------------------------------|-----------------------------|------------|
| Moving Averages (SMA/EMA) | Trend following                 | Entry/exit logic            | ⭐⭐⭐⭐⭐     |
| RSI                     | Mean reversion & momentum        | Oversold/overbought signals | ⭐⭐⭐⭐      |
| MACD                    | Momentum/trend change            | Signal crossovers           | ⭐⭐⭐⭐      |
| Bollinger Bands         | Volatility range                 | Reversion/breakouts         | ⭐⭐⭐⭐      |
| Sharpe Ratio            | Risk-adjusted performance        | Backtest evaluation         | ⭐⭐⭐⭐⭐     |
| Value at Risk (VaR)     | Downside risk estimation         | Portfolio risk              | ⭐⭐⭐⭐      |
| Expected Returns & Cov  | Portfolio construction           | Optimization, diversification| ⭐⭐⭐⭐⭐    |
| Backtesting Engines     | Strategy validation              | Before deployment           | ⭐⭐⭐⭐⭐     |
| Alpha Factors           | Feature generation for ML        | Quant modeling              | ⭐⭐⭐⭐⭐     |
| Machine Learning Models | Prediction & strategy control    | Forecasting & classification| ⭐⭐⭐⭐      |

---

