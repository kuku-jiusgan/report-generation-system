from app.models import ExtractionRule
from app.rule_engine import find_in_text

def test_regex_extract_and_round():
    rule=ExtractionRule.model_validate({"fieldCode":"flow_rate","label":"流速","sourceType":"PDF","locator":{"kind":"anchor_regex","anchor":"Flow rate","pattern":"Flow rate[:\\s]+([0-9.]+)","page_from":1},"transformer":{"decimals":2},"validator":{"required":True,"minimum":0.1,"maximum":2},"targetControlTag":"FLOW_RATE"})
    result=find_in_text(rule,[(1,"Method parameters\nFlow rate: 0.4 mL/min")])
    assert result.status=="VALID" and result.normalizedValue=="0.40" and result.evidence.page==1

def test_missing_is_blocking():
    rule=ExtractionRule.model_validate({"fieldCode":"loq","label":"LOQ","sourceType":"PDF","locator":{"kind":"regex","pattern":"LOQ ([0-9.]+)"},"validator":{"required":True},"targetControlTag":"LOQ","onMissing":"BLOCK"})
    assert find_in_text(rule,[(1,"No result")]).status=="MISSING"

