#!/usr/bin/env python3
"""Check installed package versions"""
import sys
print(f"Python: {sys.version}")
print()

pkgs = [
    ('binance', 'python-binance'),
    ('flask', 'flask'),
    ('pandas', 'pandas'),
    ('numpy', 'numpy'),
    ('sklearn', 'scikit-learn'),
    ('loguru', 'loguru'),
    ('websockets', 'websockets'),
    ('requests', 'requests'),
    ('aiohttp', 'aiohttp'),
    ('xgboost', 'xgboost'),
    ('lightgbm', 'lightgbm'),
    ('plotly', 'plotly'),
    ('scipy', 'scipy'),
    ('ta', 'ta'),
    ('joblib', 'joblib'),
    ('pydantic', 'pydantic'),
    ('waitress', 'waitress'),
    ('ccxt', 'ccxt'),
    ('tensorflow', 'tensorflow'),
    ('torch', 'torch'),
    ('seaborn', 'seaborn'),
    ('matplotlib', 'matplotlib'),
    ('sqlalchemy', 'SQLAlchemy'),
    ('cryptography', 'cryptography'),
    ('psutil', 'psutil'),
]

for mod, name in pkgs:
    try:
        m = __import__(mod)
        v = getattr(m, '__version__', 'N/A')
        print(f"  {name}: {v}")
    except ImportError:
        print(f"  {name}: NOT INSTALLED")
