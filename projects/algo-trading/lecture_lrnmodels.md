# Machine Learning Concepts for Quantitative Finance

## Lecture Slide-Style Overview

---

## 1. **Supervised Learning**

### Concept:

Supervised learning uses labeled data to train models. The model learns a function that maps inputs (features) to outputs (labels).

### Types:

* **Regression**: Predicts continuous values.
* **Classification**: Predicts discrete labels.

### Applications in Quant:

* Stock price prediction (regression)
* Credit scoring (classification)
* Market regime detection

### Example in Python:

```python
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
import pandas as pd

# Load dataset
X = pd.read_csv("features.csv")
y = pd.read_csv("target.csv")

# Train/test split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

# Model
model = RandomForestRegressor()
model.fit(X_train, y_train)

# Predict
predictions = model.predict(X_test)
```

### Visualization:

* Plot predicted vs actual returns

---

## 2. **Unsupervised Learning**

### Concept:

No labels are provided. The model uncovers hidden structures from data.

### Types:

* **Clustering**: Grouping similar data points.
* **Dimensionality Reduction**: Reducing feature space.

### Applications in Quant:

* Portfolio clustering
* Regime detection without labels
* Noise reduction in high-dimensional features

### Example in Python:

```python
from sklearn.decomposition import PCA
import matplotlib.pyplot as plt

# PCA
pca = PCA(n_components=2)
X_pca = pca.fit_transform(X)

# Plot
plt.scatter(X_pca[:, 0], X_pca[:, 1])
plt.title('PCA of Market Features')
plt.show()
```

---

## 3. **Time Series Analysis**

### Concept:

Analyzing sequences of data points indexed in time order.

### Applications in Quant:

* Price forecasting
* Volatility modeling
* Signal extraction

### Example in Python:

```python
import statsmodels.api as sm

# ARIMA model
model = sm.tsa.ARIMA(y, order=(1,1,1))
results = model.fit()

# Forecast
forecast = results.forecast(steps=5)
```

### Visualization:

* Actual vs forecasted price trend

---

## 4. **Reinforcement Learning (RL)**

### Concept:

An agent learns to make decisions by receiving rewards from the environment.

### Applications in Quant:

* Optimal trading strategies
* Dynamic hedging
* Portfolio rebalancing

### Example in Python:

```python
# Simplified Q-learning stub
Q = {}
state = get_initial_state()
for episode in range(1000):
    action = choose_action(Q, state)
    reward, new_state = take_action(state, action)
    Q[state, action] = update_q(Q, state, action, reward, new_state)
    state = new_state
```

---

## 5. **Feature Engineering & Selection**

### Concept:

Creating and choosing the most informative features from raw data.

### Applications in Quant:

* Generating technical indicators
* Reducing overfitting
* Improving model accuracy

### Example in Python:

```python
from sklearn.feature_selection import SelectKBest, f_regression

selector = SelectKBest(score_func=f_regression, k=10)
X_new = selector.fit_transform(X, y)
```

---

## 6. **Model Evaluation and Backtesting**

### Concept:

Assess model performance using metrics and simulated historical data.

### Applications in Quant:

* Evaluating profitability
* Risk-adjusted returns

### Metrics:

* Sharpe Ratio
* Precision/Recall
* Mean Absolute Error

### Example in Python:

```python
def sharpe_ratio(returns):
    return returns.mean() / returns.std()

sr = sharpe_ratio(strategy_returns)
```

---

## Interview Q\&A

### Q1: What is the difference between supervised and unsupervised learning?

**A:** Supervised learning uses labeled data to predict outcomes, such as predicting stock prices. Unsupervised learning finds hidden patterns or groupings in unlabeled data, like clustering similar stocks based on volatility profiles.

### Q2: How would you use PCA in a trading strategy?

**A:** PCA can reduce dimensionality of market indicators, helping to de-noise signals or find orthogonal factors for trading strategies like statistical arbitrage.

### Q3: Why is backtesting important, and what are its pitfalls?

**A:** Backtesting evaluates a model on historical data to estimate performance. Pitfalls include overfitting, lookahead bias, and survivorship bias.

### Q4: How does reinforcement learning differ from supervised learning in quant trading?

**A:** Reinforcement learning focuses on sequential decision-making with delayed rewards, suitable for optimizing trading strategies. Supervised learning focuses on one-shot predictions based on historical labels.

### Q5: Explain the bias-variance tradeoff.

**A:** Bias refers to errors due to wrong assumptions; variance refers to sensitivity to training data. In quant, a high variance model may overfit to noise in historical prices, leading to poor generalization.
