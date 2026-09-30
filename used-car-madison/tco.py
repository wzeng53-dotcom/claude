#!/usr/bin/env python3
"""Total cost of ownership (TCO) for a used car bought Oct 2026 in Madison, WI and sold Aug 2027.

Net cost = purchase price + tax/title/registration/dealer fees + insurance + fuel
           + maintenance/repair reserve + winter-tire net cost - resale value (Aug 2027).

All inputs live in the dicts below; sources are in data/*.json and README.md.
Run:  python3 tco.py            -> archetype table + listing table (if data/shortlist.json exists)
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
GAS = {                       # $/gal planning averages Oct-26..Aug-27 (Madison was $4.03-4.46 in Sep-26; EIA sees 2027 lower)
    'base': {'regular': 3.80, 'premium': 4.70},
    'high': {'regular': 4.40, 'premium': 5.30},
}

# Wisconsin government fees (City of Madison / Dane County, Oct 2026)
SALES_TAX = 0.055             # 5% state + 0.5% Dane County; follows where the car is kept, not where it's bought
TITLE_FEE = 214.50            # $207 + $7.50 supplemental (2025 Act 15, from Oct 1 2025)
REGISTRATION = 85 + 40 + 40   # state $85 + City of Madison wheel tax $40 + Dane County wheel tax $40 (2026)
HYBRID_SURCHARGE = 75         # Wis. Stat. 341.255
NEW_PLATES = 12               # $6/plate since Apr 2026
TEMP_PLATE_PRIVATE = 3        # dealers must issue a WI temp plate free to WI residents

# Dealer fees
WI_DEALER_SERVICE_FEE = 399   # Madison: Smart Toyota $299, Bergstrom/Zimbrick $399, Kunes $499 - no legal cap, negotiable down
IL_DEALER_DOC_FEE = 377.63    # Illinois statutory cap for 2026; IL dealer collects no IL tax from a WI resident (ST-556/ST-588)
IL_DRIVE_AWAY = 10            # IL 7/30-day permit

# Due diligence
PPI = 150                     # pre-purchase inspection at an independent shop
HISTORY_REPORT_PRIVATE = 30   # AutoCheck/Carfax when the seller doesn't provide one

INSURANCE_PROFILE_MULT = {'a': 1.0, 'b': 1.4}   # a = US license 3+ yrs clean; b = new US driver / intl student

# ---------------------------------------------------------------- per-model parameters
# ins  : typical annual FULL coverage (100/300/100 or 50/100/50, $500-1000 ded.) for profile (a), Madison
# mpg  : EPA combined;  fuel: 'regular' | 'premium'
# maint: expected maintenance + repair spend per 12 months for a 10-15-yr-old example (estimate)
# dep  : private-party depreciation per year (age only);  per_mi: $ value lost per mile driven
# season: Aug-2027 private-sale seasonal/demand adjustment (Madison student inflow)
# dealer_ratio: dealer / instant-offer price as a share of private-party value
# retail_premium: dealer retail ask vs private-party value
# winter: net cost of a used winter-tire set (FWD 350, RWD 450, AWD 0 = optional)
MODELS = {
    'es350':     dict(name='Lexus ES 350 (2010-2013)', ins=1720, mpg=22, fuel='regular', maint=850, dep=0.06, per_mi=0.06, season=0.02, dealer_ratio=0.72, retail_premium=1.17, winter=350, hybrid=False),
    'es300h':    dict(name='Lexus ES 300h (2013-2014)', ins=1720, mpg=40, fuel='regular', maint=900, dep=0.07, per_mi=0.07, season=0.02, dealer_ratio=0.70, retail_premium=1.17, winter=350, hybrid=True),
    'rx350':     dict(name='Lexus RX 350 AWD (2010-2012)', ins=1620, mpg=20, fuel='regular', maint=1050, dep=0.06, per_mi=0.06, season=0.01, dealer_ratio=0.68, retail_premium=1.18, winter=0, hybrid=False),
    'is250awd':  dict(name='Lexus IS 250 AWD (2009-2013)', ins=1790, mpg=22, fuel='premium', maint=1000, dep=0.08, per_mi=0.06, season=0.01, dealer_ratio=0.68, retail_premium=1.18, winter=0, hybrid=False),
    'gx470':     dict(name='Lexus GX 470 (2005-2009)', ins=1560, mpg=15, fuel='premium', maint=1250, dep=0.03, per_mi=0.04, season=0.01, dealer_ratio=0.71, retail_premium=1.13, winter=0, hybrid=False),
    'ct200h':    dict(name='Lexus CT 200h (2012-2015)', ins=1700, mpg=42, fuel='regular', maint=800, dep=0.07, per_mi=0.07, season=0.02, dealer_ratio=0.70, retail_premium=1.17, winter=350, hybrid=True),
    'camry':     dict(name='Toyota Camry 2.5 (2012-2016)', ins=1640, mpg=28, fuel='regular', maint=650, dep=0.06, per_mi=0.06, season=0.02, dealer_ratio=0.74, retail_premium=1.12, winter=350, hybrid=False),
    'corolla':   dict(name='Toyota Corolla (2014-2017)', ins=1650, mpg=31, fuel='regular', maint=575, dep=0.055, per_mi=0.06, season=0.02, dealer_ratio=0.75, retail_premium=1.18, winter=350, hybrid=False),
    'prius':     dict(name='Toyota Prius (2012-2015)', ins=1700, mpg=50, fuel='regular', maint=700, dep=0.07, per_mi=0.07, season=0.02, dealer_ratio=0.70, retail_premium=1.18, winter=350, hybrid=True),
    'avalon':    dict(name='Toyota Avalon (2013-2015)', ins=1680, mpg=25, fuel='regular', maint=750, dep=0.065, per_mi=0.06, season=0.01, dealer_ratio=0.70, retail_premium=1.17, winter=350, hybrid=False),
    'rav4awd':   dict(name='Toyota RAV4 AWD (2011-2014)', ins=1430, mpg=24, fuel='regular', maint=650, dep=0.055, per_mi=0.06, season=0.02, dealer_ratio=0.76, retail_premium=1.17, winter=0, hybrid=False),
    'highlander':dict(name='Toyota Highlander V6 AWD (2009-2012)', ins=1470, mpg=19, fuel='regular', maint=800, dep=0.065, per_mi=0.06, season=0.01, dealer_ratio=0.73, retail_premium=1.18, winter=0, hybrid=False),
    'venza':     dict(name='Toyota Venza (2011-2014)', ins=1550, mpg=22, fuel='regular', maint=750, dep=0.065, per_mi=0.06, season=0.01, dealer_ratio=0.70, retail_premium=1.17, winter=0, hybrid=False),
    'lr4':       dict(name='Land Rover LR4 5.0 V8 (2011-2013)', ins=1720, mpg=14, fuel='premium', maint=3000, dep=0.15, per_mi=0.08, season=0.0, dealer_ratio=0.56, retail_premium=1.28, winter=0, hybrid=False),
    'rrsport':   dict(name='Range Rover Sport (2010-2012)', ins=2100, mpg=14, fuel='premium', maint=3000, dep=0.17, per_mi=0.08, season=0.0, dealer_ratio=0.51, retail_premium=1.24, winter=0, hybrid=False),
    'evoque':    dict(name='Range Rover Evoque (2012-2015)', ins=1910, mpg=23, fuel='premium', maint=2250, dep=0.15, per_mi=0.08, season=0.0, dealer_ratio=0.62, retail_premium=1.21, winter=0, hybrid=False),
}

# Typical private-party value of a representative $8-13k example today (Oct 2026), used for archetype rows.
ARCHETYPE_PP = {
    'es350': 9800, 'es300h': 11000, 'rx350': 9300, 'is250awd': 8500, 'gx470': 12000, 'ct200h': 10000,
    'camry': 9800, 'corolla': 9300, 'prius': 9300, 'avalon': 10000, 'rav4awd': 10300, 'highlander': 9300,
    'venza': 9500, 'lr4': 9000, 'rrsport': 8500, 'evoque': 8700,
}


def purchase_costs(price, seller, hybrid):
    """One-time costs on top of the price. seller: 'private' | 'wi_dealer' | 'il_dealer'."""
    reg = REGISTRATION + (HYBRID_SURCHARGE if hybrid else 0)
    if seller == 'private':
        fee = 0
        tax = SALES_TAX * price
        extra = TEMP_PLATE_PRIVATE + HISTORY_REPORT_PRIVATE
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
    return dict(tax=tax, dealer_fee=fee, title=TITLE_FEE, registration=reg, plates=NEW_PLATES,
                ppi=PPI, other=extra)


def resale(pp_now, m):
    """Private-party and dealer/instant-offer value in Aug 2027."""
    pp = pp_now * (1 - m['dep'] * MONTHS / 12) - m['per_mi'] * MILES
    pp *= 1 + m['season']
    return pp, pp * m['dealer_ratio']


def running_costs(m, profile='a', gas='base'):
    ins = m['ins'] * INSURANCE_PROFILE_MULT[profile] * MONTHS / 12
    fuel = MILES / (m['mpg'] * WINTER_MPG_FACTOR) * GAS[gas][m['fuel']]
    maint = m['maint'] * MONTHS / 12
    return dict(insurance=ins, fuel=fuel, maintenance=maint, winter_tires=m['winter'])


def tco(model_key, price, seller, pp_now, profile='a', gas='base'):
    m = MODELS[model_key]
    buy = purchase_costs(price, seller, m['hybrid'])
    run = running_costs(m, profile, gas)
    pp27, dealer27 = resale(pp_now, m)
    upfront = price + sum(buy.values())
    running = sum(run.values())
    return dict(
        model=m['name'], price=price, seller=seller, pp_now=pp_now,
        **{f'buy_{k}': v for k, v in buy.items()}, **run,
        out_the_door=upfront, running=running,
        resale_private=pp27, resale_dealer=dealer27,
        net_private_exit=upfront + running - pp27,
        net_dealer_exit=upfront + running - dealer27,
        per_month_private_exit=(upfront + running - pp27) / MONTHS,
    )


def archetypes(profile='a', gas='base'):
    rows = []
    for k, pp in ARCHETYPE_PP.items():
        m = MODELS[k]
        retail = round(pp * m['retail_premium'], -1)
        rows.append(dict(key=k, channel='private buy @ market', **tco(k, pp, 'private', pp, profile, gas)))
        rows.append(dict(key=k, channel='WI dealer @ retail', **tco(k, retail, 'wi_dealer', pp, profile, gas)))
    return rows


def listings(profile='a', gas='base'):
    path = os.path.join(HERE, 'data', 'shortlist.json')
    if not os.path.exists(path):
        return []
    rows = []
    for l in json.load(open(path)):
        m = MODELS[l['model_key']]
        if l.get('pp_now'):
            pp_now = l['pp_now']
        elif l['seller'] == 'private':
            pp_now = l.get('market_pp', l['price'])
        else:  # dealer: private-party value = market retail / retail premium
            pp_now = l.get('market_retail', l['price']) / m['retail_premium']
        r = tco(l['model_key'], l['price'], l['seller'], pp_now, profile, gas)
        r.update(id=l['id'], label=l['label'])
        rows.append(r)
    return rows


def fmt(rows, title):
    out = [f'### {title}', '',
           '| Car | Channel | Price | Out-the-door | Insurance | Fuel | Maint | Winter | Resale Aug-27 (private / dealer) | **Net cost, private exit** | Net cost, dealer exit | $/month |',
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
        print(fmt(archetypes(), 'Archetypes - insurance profile (a), base gas'))
        print()
        ls = listings()
        if ls:
            print(fmt(ls, 'Shortlisted listings - insurance profile (a), base gas'))
