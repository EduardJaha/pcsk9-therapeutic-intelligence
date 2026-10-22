"""Unit-explicit numerical analysis; never inserts training measurements."""
import warnings

import numpy as np
import scipy
from scipy.optimize import OptimizeWarning, curve_fit
from scipy.special import expit

from cvti.registry import json_hash

MOLAR = {'M': 1., 'mM': 1e-3, 'uM': 1e-6, 'µM': 1e-6, 'nM': 1e-9, 'pM': 1e-12}


def fit_curve(concentrations, responses, units, direction):
    x, y = np.array(concentrations, dtype=float), np.array(responses, dtype=float)
    if units not in MOLAR or direction not in {'increasing', 'decreasing'}:
        raise ValueError('Choose molar concentration units and an increasing/decreasing response')
    if len(x) != len(y) or not 6 <= len(x) <= 500:
        raise ValueError('Supply 6–500 paired observations')
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)) or np.any(x <= 0):
        raise ValueError('All observations must be finite and concentrations strictly positive; keep zero-dose controls in plate QC')
    if len(np.unique(x)) < 6 or np.ptp(y) < 1e-8:
        raise ValueError('At least six distinct concentrations and varying responses are required')
    logx, sign = np.log10(x * MOLAR[units]), 1 if direction == 'increasing' else -1

    def model(logc, bottom, amplitude, midpoint, slope):
        return bottom + amplitude * expit(sign * slope * np.log(10) * (logc - midpoint))

    span = float(np.ptp(y))
    with warnings.catch_warnings():
        warnings.simplefilter('error', OptimizeWarning)
        try:
            params, covariance = curve_fit(model, logx, y,
                p0=[float(y.min()), span, float(np.median(logx)), 1.],
                bounds=([float(y.min() - 2*span), 0, float(logx.min()-2), .05],
                        [float(y.max()), 5*span, float(logx.max()+2), 8]), maxfev=20000)
        except (ValueError, RuntimeError, OptimizeWarning) as exc:
            raise ValueError('The 4PL fit is not identifiable or failed to converge; inspect the raw observations') from exc
    bottom, amplitude, mid, slope = map(float, params)
    predictions = model(logx, *params)
    residual = y - predictions
    r2 = 1 - float(np.sum(residual**2) / np.sum((y-y.mean())**2))
    flags = []
    inside = float(logx.min()) < mid < float(logx.max())
    if not inside:
        flags.append('Midpoint lies outside the tested concentration range; extrapolated fit')
    if not np.all(np.isfinite(covariance)) or np.linalg.cond(covariance) > 1e12:
        flags.append('Parameter uncertainty is poorly identified')
    fractions = (predictions - bottom) / amplitude if amplitude > 0 else np.zeros(len(x))
    if fractions.min() > .1 or fractions.max() < .9:
        flags.append('Both plateaus are not covered by the tested concentrations')
    if slope <= .051 or slope >= 7.999:
        flags.append('Hill slope reached a fitting bound')
    grid = np.linspace(logx.min(), logx.max(), 120)
    se = float(np.sqrt(max(covariance[2, 2], 0)))
    interval = None
    if np.isfinite(se) and se < 10 and not flags:
        interval = [float(10**(mid-1.96*se)/MOLAR[units]), float(10**(mid+1.96*se)/MOLAR[units])]
    return {'midpoint': 10**mid/MOLAR[units], 'units': units, 'p_midpoint': -mid,
            'bottom': bottom, 'top': bottom+amplitude, 'hill_slope': slope, 'r_squared': r2,
            'midpoint_approximate_95_interval': interval, 'warnings': flags,
            'raw': [{'concentration': float(a), 'response': float(b), 'residual': float(c)} for a,b,c in zip(x,y,residual)],
            'curve': [{'concentration': float(10**a/MOLAR[units]), 'response': float(b)} for a,b in zip(grid,model(grid,*params))],
            'provenance': {'method': 'bounded unweighted four-parameter logistic', 'direction': direction,
                           'scipy': scipy.__version__, 'input_sha256': json_hash({'x': concentrations,'y': responses,'units': units,'direction': direction})},
            'notice': 'A fitted response midpoint is not automatically IC50/EC50. Replicates are retained with equal weight. Approximate intervals assume independent, constant-variance errors; no assay approval is implied.'}


def plate_qc(positive, negative):
    pos, neg = np.asarray(positive, dtype=float), np.asarray(negative, dtype=float)
    if not 3 <= len(pos) <= 500 or not 3 <= len(neg) <= 500 or not np.all(np.isfinite(pos)) or not np.all(np.isfinite(neg)):
        raise ValueError('Supply 3–500 finite control values per group')
    separation = abs(float(pos.mean() - neg.mean()))
    if separation == 0:
        raise ValueError('Control means are equal; Z-prime is undefined')
    z = 1 - 3*(float(pos.std(ddof=1))+float(neg.std(ddof=1)))/separation
    return {'z_prime': z, 'positive_mean': float(pos.mean()), 'negative_mean': float(neg.mean()),
            'positive_sd': float(pos.std(ddof=1)), 'negative_sd': float(neg.std(ddof=1)),
            'positive_n': len(pos), 'negative_n': len(neg),
            'assessment': 'Well separated controls' if z >= .5 else 'Marginal separation' if z >= 0 else 'Overlapping control distributions',
            'notice': 'Z-prime summarizes control separation only. It does not validate endpoint specificity or an assay protocol.'}
