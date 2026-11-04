"""Fair-value model for Polymarket BTC 5m Up/Down (Chainlink 60s-TWAP settlement).

Window [S, S+300]. Strike K = TWAP of [S-60, S]  (= previous window's final price).
Final F = TWAP of [S+240, S+300]. Up wins iff F >= K.
With price as Brownian motion (per-second vol sig, in $), at time S+tau:
  tau <= 240:  F - X(tau) ~ N(0, sig^2 * (260 - tau))          [ (240-tau) + 60/3 ]
  tau  > 240:  F = ((tau-240)*A + r*X(tau) + noise)/60,  r = 300 - tau,
               noise ~ N(0, sig^2 * r^3 / 3)
               where A = average price over [S+240, S+tau] already observed.
Before the window opens (tau < 0) K itself is still forming; not modelled here.
"""
import math


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def p_up(tau, x, K, sig, A=None):
    """tau: seconds since window start; x: current price (same feed as K); sig: $/sqrt(s)."""
    if sig <= 0:
        sig = 1e-9
    if tau <= 240:
        mu, sd = x, sig * math.sqrt(max(260 - tau, 1e-6))
    else:
        r = max(300 - tau, 0.0)
        a = A if A is not None else x
        mu = ((tau - 240) * a + r * x) / 60
        sd = sig * math.sqrt(r ** 3 / 3) / 60
        if sd < 1e-9:
            return 1.0 if mu >= K else 0.0
    return ncdf((mu - K) / sd)


def p_up_spot_naive(tau, x, K, sig):
    """What a trader who thinks it settles on spot at S+300 would price."""
    return ncdf((x - K) / (sig * math.sqrt(max(300 - tau, 1e-6))))


def taker_fee(p, shares, rate=0.07, exponent=1):
    """Polymarket crypto fee (placeholder until docs confirm): shares * rate * (p*(1-p))**exponent."""
    return shares * rate * (p * (1 - p)) ** exponent
