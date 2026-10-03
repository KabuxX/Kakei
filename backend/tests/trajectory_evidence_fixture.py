import copy

def legacy_evidence(value):
    result=copy.deepcopy(value)
    for place in result['places'].values():place.update(placeEvidence='legacy',attribution=None)
    for day in result['days']:
        for event in day['events']:event.update(timeEvidence='legacy',timeEvidenceNote=None)
        for leg in day['legs']:leg.update(modeEvidence='legacy',modeEvidenceNote=None)
    return result
