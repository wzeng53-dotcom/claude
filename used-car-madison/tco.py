#!/usr/bin/env python3
"""Total cost of ownership (TCO) for a used car bought Oct 2026 in Madison, WI and sold Aug 2027.

Net cost = price + tax/title/registration/dealer fees + inspection
         + insurance + fuel + maintenance/repair reserve + winter-tire net cost
         - resale value in Aug 2027

Every input is in the dicts below; sources and reasoning are in README.md and data/*.json.
Run:  python3 tco.py            -> markdown tables (archetypes, then listings if data/shortlist.json exists)
      python3 tco.py --json     -> machine-readable output
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- global assumptions
MONTHS = 10.5                 # mid-Oct 2026 -> end of Aug 2027
MILES = 9000                  # miles driven during the hold
WINTER_MPG_FACTOR = 0.92      # Madison winter drags average mpg ~8% below EPA combined
GAS = {                       # $/gal averages for Oct-26..Aug-27. Madison regular was $4.03-4.46 in Sep-26;
    'base': {'regular': 3.80, 'premium': 4.70},   # EIA STEO (Sep-26) sees US regular at $3.35 in 2027
    'high': {'regular': 4.40, 'premium': 5.30},
}

# Wisconsin government fees (City of Madison / Dane County, Oct 2026)
SALES_TAX = 0.055             # 5% state + 0.5% Dane County; follows where the car is kept, not where it's bought
TITLE_FEE = 214.50            # $207 + $7.50 supplemental (2025 Act 15, effective Oct 1 2025)
REGISTRATION = 85 + 40 + 40   # state $85 + City of Madison wheel tax $40 + Dane County wheel tax $40 (2026)
HYBRID_SURCHARGE = 75         # Wis. Stat. 341.255, per year
NEW_PLATES = 12               # $6/plate (collected since Apr 2026)
TEMP_PLATE_PRIVATE = 3        # WI dealers must issue a temp plate free to WI residents

# Dealer fees
WI_DEALER_SERVICE_FEE = 399   # Madison: Smart Toyota $299, Bergstrom/Zimbrick $399, Lexus of Brookfield $479, Kunes $499
IL_DEALER_DOC_FEE = 377.63    # Illinois 2026 cap. IL dealer collects no IL tax from a WI resident (ST-556 / ST-588)
IL_DRIVE_AWAY = 10            # IL 7/30-day permit

# Due diligence
PPI = 150                     # pre-purchase inspection at an independent shop
HISTORY_REPORT_PRIVATE = 30   # AutoCheck/Carfax when the seller doesn't provide one

# Insurance: profile (a) = US license 3+ yrs clean; (b) = new US driver / international student
INSURANCE_PROFILE_MULT = {'a': 1.0, 'b': 1.4}
# Liability 100/300/100 + UM/UIM + comprehensive (deer!) but NO collision, as a share of full coverage
LIAB_COMP_SHARE = 0.56
DROP_COLLISION_BELOW = 8000   # recommended: drop collision when the car's private value is below this

# ---------------------------------------------------------------- per-model parameters
# ins   : typical annual FULL-coverage premium, profile (a), Madison (Zebra model factors x Madison baseline)
# mpg   : EPA combined;  fuel: 'regular' | 'premium'
# maint : expected maintenance + repair spend per 12 months, 10-15-yr-old example (estimate)
# chg   : private-party value change over the hold (10.5 months, +9k miles, incl. Aug seasonality).
#         Anchored on CarGurus same-model-year YoY (Sep-26: 2012 ES +3.3%, 2011 RX AWD +0.1%, 2013 Camry +1.5%,
#         2015 Corolla 0%, 2013 Prius +1.7%, 2012 RAV4 -0.7%, LR4 -4..-13%) minus a turning market
#         (Manheim -0.4% YoY mid-Sep-26; SUVs/midsize falling, compact cars and hybrids holding).
# per_mi: extra value lost per mile beyond MILES
# dealer_ratio: dealer trade-in / instant offer as a share of private-party value (Edmunds TI/PP ratios)
# retail_premium: dealer retail ask vs private-party value
# ask   : typical dealer ask for a representative in-budget example today (CarGurus cohort averages, Sep-26)
# winter: net cost of a used winter-tire set (FWD 350, RWD 450, AWD/4WD 0 = optional)
MODELS = {
    'es350':     dict(name='Lexus ES 350 (2010-2012, ~120-140k mi)', ask=11800, ins=1720, mpg=22, fuel='regular', maint=850,  chg=-0.05, per_mi=0.06, dealer_ratio=0.70, retail_premium=1.15, winter=350, hybrid=False),
    'es350g6':   dict(name='Lexus ES 350 (2013-2014, ~130-160k mi)', ask=13300, ins=1720, mpg=24, fuel='regular', maint=800,  chg=-0.04, per_mi=0.06, dealer_ratio=0.72, retail_premium=1.15, winter=350, hybrid=False),
    'es300h':    dict(name='Lexus ES 300h (2013-2014)', ask=12800, ins=1720, mpg=40, fuel='regular', maint=900,  chg=-0.05, per_mi=0.07, dealer_ratio=0.66, retail_premium=1.15, winter=350, hybrid=True),
    'rx350':     dict(name='Lexus RX 350 AWD (2010-2012, ~130k mi)', ask=11600, ins=1620, mpg=20, fuel='regular', maint=1050, chg=-0.06, per_mi=0.06, dealer_ratio=0.72, retail_premium=1.15, winter=0,   hybrid=False),
    'is250awd':  dict(name='Lexus IS 250 AWD (2008-2011)', ask=9500,  ins=1790, mpg=22, fuel='premium', maint=1000, chg=-0.08, per_mi=0.06, dealer_ratio=0.72, retail_premium=1.15, winter=0,   hybrid=False),
    'gx470':     dict(name='Lexus GX 470 (2005-2009, 180k+ mi)', ask=13000, ins=1560, mpg=15, fuel='premium', maint=1250, chg=-0.03, per_mi=0.04, dealer_ratio=0.80, retail_premium=1.13, winter=0,   hybrid=False),
    'ct200h':    dict(name='Lexus CT 200h (2012-2014)', ask=10500, ins=1700, mpg=42, fuel='regular', maint=800,  chg=-0.05, per_mi=0.07, dealer_ratio=0.70, retail_premium=1.15, winter=350, hybrid=True),
    'camry':     dict(name='Toyota Camry 2.5 (2013-2014, ~120k mi)', ask=10900, ins=1640, mpg=28, fuel='regular', maint=650,  chg=-0.05, per_mi=0.06, dealer_ratio=0.74, retail_premium=1.15, winter=350, hybrid=False),
    'corolla':   dict(name='Toyota Corolla (2014-2016, ~110k mi)', ask=11800, ins=1650, mpg=31, fuel='regular', maint=575,  chg=-0.03, per_mi=0.06, dealer_ratio=0.75, retail_premium=1.15, winter=350, hybrid=False),
    'prius':     dict(name='Toyota Prius (2012-2014, ~130k mi)', ask=9500,  ins=1700, mpg=50, fuel='regular', maint=700,  chg=-0.04, per_mi=0.07, dealer_ratio=0.70, retail_premium=1.15, winter=350, hybrid=True),
    'avalon':    dict(name='Toyota Avalon (2013-2014)', ask=11500, ins=1680, mpg=25, fuel='regular', maint=750,  chg=-0.06, per_mi=0.06, dealer_ratio=0.70, retail_premium=1.15, winter=350, hybrid=False),
    'rav4awd':   dict(name='Toyota RAV4 AWD (2012-2014, ~140k mi)', ask=11000, ins=1430, mpg=24, fuel='regular', maint=650,  chg=-0.05, per_mi=0.06, dealer_ratio=0.75, retail_premium=1.15, winter=0,   hybrid=False),
    'highlander':dict(name='Toyota Highlander V6 AWD (2010-2012)', ask=10900, ins=1470, mpg=19, fuel='regular', maint=800,  chg=-0.06, per_mi=0.06, dealer_ratio=0.75, retail_premium=1.15, winter=0,   hybrid=False),
    'venza':     dict(name='Toyota Venza (2011-2013)', ask=10500, ins=1550, mpg=22, fuel='regular', maint=750,  chg=-0.06, per_mi=0.06, dealer_ratio=0.72, retail_premium=1.15, winter=0,   hybrid=False),
    'lr4':       dict(name='Land Rover LR4 (2011-2013)', ask=11000, ins=1720, mpg=14, fuel='premium', maint=3000, chg=-0.12, per_mi=0.08, dealer_ratio=0.58, retail_premium=1.22, winter=0,   hybrid=False),
    'rrsport':   dict(name='Range Rover Sport (2010-2012)', ask=9000,  ins=2100, mpg=14, fuel='premium', maint=3000, chg=-0.13, per_mi=0.08, dealer_ratio=0.52, retail_premium=1.22, winter=0,   hybrid=False),
    'evoque':    dict(name='Range Rover Evoque (2012-2014)', ask=10700, ins=1910, mpg=23, fuel='premium', maint=2250, chg=-0.10, per_mi=0.08, dealer_ratio=0.60, retail_premium=1.20, winter=0,   hybrid=False),
}


def purchase_costs(price, seller, hybrid):
    """One-time costs on top of the price. seller: 'private' | 'wi_dealer' | 'il_dealer'."""
    reg = REGISTRATION + (HYBRID_SURCHARGE if hybrid else 0)
    if seller == 'private':
        fee, tax, extra = 0, SALES_TAX * price, TEMP_PLATE_PRIVATE + HISTORY_REPORT_PRIVATE
    elif seller == 'wi_dealer':
        fee = WI_DEALER_SERVICE_FEE
        tax = SALES_TAX * (price + fee)          # WI service fee is part of the taxable price
        extra = 0
    elif seller == 'il_dealer':
        fee = IL_DEALER_DOC_FEE
        tax = SALES_TAX * (price + fee)          # conservative: assume WI taxes the IL doc fee too
        extra = IL_DRIVE_AWAY
    else:
        raise ValueError(seller)
    return dict(tax=tax, dealer_fee=fee, title=TITLE_FEE, registration=reg, plates=NEW_PLATES, ppi=PPI, other=extra)


def resale(pp_now, m, miles=MILES):
    """Private-party and dealer/instant-offer value in Aug 2027."""
    pp = pp_now * (1 + m['chg']) - m['per_mi'] * max(0, miles - MILES)
    return pp, pp * m['dealer_ratio']


def running_costs(m, pp_now, profile='a', gas='base', coverage='auto', miles=MILES):
    full = m['ins'] * INSURANCE_PROFILE_MULT[profile]
    if coverage == 'auto':
        coverage = 'liab_comp' if pp_now < DROP_COLLISION_BELOW else 'full'
    annual = full if coverage == 'full' else full * LIAB_COMP_SHARE
    return dict(insurance=annual * MONTHS / 12,
                fuel=miles / (m['mpg'] * WINTER_MPG_FACTOR) * GAS[gas][m['fuel']],
                maintenance=m['maint'] * MONTHS / 12,
                winter_tires=m['winter']), coverage


def tco(model_key, price, seller, pp_now, profile='a', gas='base', coverage='auto', miles=MILES):
    m = MODELS[model_key]
    buy = purchase_costs(price, seller, m['hybrid'])
    run, cov = running_costs(m, pp_now, profile, gas, coverage, miles)
    pp27, dealer27 = resale(pp_now, m, miles)
    upfront = price + sum(buy.values())
    running = sum(run.values())
    return dict(model=m['name'], price=price, seller=seller, pp_now=pp_now, coverage=cov,
                **{f'buy_{k}': v for k, v in buy.items()}, **run,
                out_the_door=upfront, running=running,
                resale_private=pp27, resale_dealer=dealer27,
                net_private_exit=upfront + running - pp27,
                net_dealer_exit=upfront + running - dealer27,
                per_month_private_exit=(upfront + running - pp27) / MONTHS)


def archetypes(profile='a', gas='base', coverage='full'):
    """Each model bought (1) privately at fair private-party value, (2) from a WI dealer at typical retail."""
    rows = []
    for k, m in MODELS.items():
        pp = round(m['ask'] / m['retail_premium'], -1)
        rows.append(dict(key=k, channel='private @ fair value', **tco(k, pp, 'private', pp, profile, gas, coverage)))
        rows.append(dict(key=k, channel='WI dealer @ avg ask', **tco(k, m['ask'], 'wi_dealer', pp, profile, gas, coverage)))
    return rows


def listings(profile='a', gas='base', coverage='auto'):
    path = os.path.join(HERE, 'data', 'shortlist.json')
    if not os.path.exists(path):
        return []
    rows = []
    for l in json.load(open(path)):
        m = MODELS[l['model_key']]
        # private-party market value of THIS car today
        pp_now = l.get('pp_now') or (l['price'] if l['seller'] == 'private' else l['price'] / m['retail_premium'])
        r = tco(l['model_key'], l['price'], l['seller'], pp_now, profile, gas, coverage)
        r.update(id=l['id'], label=l['label'], status=l.get('status', ''))
        rows.append(r)
    return rows


def fmt(rows, title):
    out = [f'### {title}', '',
           '| Car | Channel | Price | Out-the-door | Insurance | Fuel | Maint. | Winter tires | Resale Aug-27 private / dealer | **Net cost (sell private)** | Net cost (sell to dealer) | per month |',
           '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in sorted(rows, key=lambda r: r['net_private_exit']):
        out.append('| {} | {} | ${:,.0f} | ${:,.0f} | ${:,.0f} | ${:,.0f} | ${:,.0f} | ${:,.0f} | ${:,.0f} / ${:,.0f} | **${:,.0f}** | ${:,.0f} | ${:,.0f} |'.format(
            r.get('label', r['model']), r.get('channel', r['seller']), r['price'], r['out_the_door'], r['insurance'],
            r['fuel'], r['maintenance'], r['winter_tires'], r['resale_private'], r['resale_dealer'],
            r['net_private_exit'], r['net_dealer_exit'], r['per_month_private_exit']))
    return '\n'.join(out)


if __name__ == '__main__':
    if '--json' in sys.argv:
        print(json.dumps({'archetypes': archetypes(), 'listings': listings(),
                          'listings_profile_b': listings('b'), 'listings_gas_high': listings('a', 'high')}, indent=1))
    else:
        print(fmt(archetypes(), 'Archetypes: insurance profile (a), full coverage, base gas'))
        ls = listings()
        if ls:
            print()
            print(fmt(ls, 'Listings: insurance profile (a), base gas, collision dropped if value < $8k'))
