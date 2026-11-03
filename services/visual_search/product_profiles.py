"""Owner-reviewed artwork recipes, applied by the ordinary incremental indexer.

Pixel transforms apply only to an exact matching stock profile. Individual
custom geometry keeps priority. No query photograph becomes an index source.
"""
from .views import profile

VERSION = 'physical-layouts-3'
MIRRORED = ('Брелок Акрил', 'БрелокС Акрил', 'Фигурка Акрил')


def preset(label):
    upper = [[0,0,1,.5],[.1,.05,.9,.45]]
    # Exact front first; retain prior overlapping views for print bleed,
    # identical repeated sides and photographs of the other side.
    cover = [[.5,0,1,1],[0,0,.52,1],[.48,0,1,1],[.28,0,1,1]]
    quarters = [[0,0,.5,.5],[.5,0,1,.5],[0,.5,.5,1],[.5,.5,1,1]]
    rules = {
        'Пенал':upper, 'Пенал Большой':upper, 'Пенал-косметичка':upper,
        'Монетница':upper,
        'Минидак':[[0,0,.5,1],[.5,0,1,1],[.025,.05,.475,.95],[.525,.05,.975,.95]],
        'БрелокС Акрил': [[0,0,1,.72],[0,.30,.55,1],[.45,.30,1,1]],
        'Брелок Набор 2+1': [[0,.25,.55,1],[.45,.25,1,1],[0,.25,1,1]],
        'Дневник':cover, 'Дневник Т':cover,
        'Обложка на паспорт':cover, 'Обложка на военник':cover,
        'Обложка на студенческий':[[0,0,1,.5]],
        'Стикерпак':quarters, 'Тетрадь Набор 4+1':quarters,
        'Плакат Набор (3шт)':[[0,0,1/3,1],[1/3,0,2/3,1],[2/3,0,1,1]],
        'Набор значков (6шт)': [[x0,y0,x1,y1] for x0,x1 in ((0,.55),(.45,1))
                              for y0,y1 in ((.16,.49),(.40,.76),(.67,1))],
    }
    if label == 'Кружка':
        boxes = [[x,0,x+1/3,1] for x in (0,1/3,2/3)]
        boxes += [[x,0,x+.5,1] for x in (0,.125,.25,.375,.5)]
        return profile({'layout':'cylinder','regions':boxes,'revision':3,'full_wrap':True})
    if label in rules:
        return profile({'layout':'collage','regions':rules[label],'revision':3})
    if label in MIRRORED:
        return profile({'layout':'single','revision':3})
    return None


def transforms(label, settings):
    """Canonical pixel transforms without extending the shared admin schema."""
    expected = preset(label)
    if expected is None:return {}
    actual = profile(settings)
    expected['source_policy'] = actual['source_policy']
    if actual != expected:return {}
    return {'rotation':90 if label == 'Обложка на студенческий' else 0,
            'mirror':label in MIRRORED}
