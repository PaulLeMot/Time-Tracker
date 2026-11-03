"""Reviewed catalogue-layout presets, revision 2; never specific SKU examples.

Administrators apply these through the audited OperKontur profile setting.
The ordinary incremental indexer then uses that setting for every new product
of the same kind. Per-asset overrides remain authoritative. No query photo is
an index source. Coordinates refer to the complete catalogue artwork.
"""
from .views import profile

VERSION = 'physical-layouts-2'


def preset(label):
    fold = [[0,0,.52,1],[.48,0,1,1],[0,0,1,.52],[0,.48,1,1]]
    cover = [[0,0,.52,1],[.48,0,1,1],[.28,0,1,1]]
    rules = {
        'Пенал': fold, 'Пенал Большой': fold,
        'Минидак': fold + [[0,0,1,.72],[0,.28,1,1]],
        'БрелокС Акрил': [[0,0,1,.72],[0,.30,.55,1],[.45,.30,1,1]],
        'Брелок Набор 2+1': [[0,.25,.55,1],[.45,.25,1,1],[0,.25,1,1]],
        'Дневник': cover, 'Дневник Т': cover,
        'Обложка на паспорт': cover, 'Обложка на военник': cover,
        'Обложка на студенческий': cover,
        'Стикерпак': fold,
        'Набор значков (6шт)': [[x0,y0,x1,y1] for x0,x1 in ((0,.55),(.45,1))
                              for y0,y1 in ((.16,.49),(.40,.76),(.67,1))],
    }
    if label == 'Кружка':
        boxes = [[x,0,x+1/3,1] for x in (0,1/3,2/3)]
        boxes += [[x,0,x+.5,1] for x in (0,.125,.25,.375,.5)]
        return profile({'layout':'cylinder','regions':boxes,'revision':2,'full_wrap':True})
    if label in rules:
        return profile({'layout':'collage','regions':rules[label],'revision':2})
    return None
