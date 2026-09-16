"""控件里被模板作者手动折行拆出的多余段落，填值后不能留下空行。

表4-3「仪器信息列表」的仪器名称格在 Word 模板里是两个段落（"三重四极" / "液质联用仪"），
两段一起被包进了内容控件。写值只用得到第一个段落，另一段留着就会让每一行都多出一个空行。
"""

from lxml import etree

from backend.app.services.docx_field_values import set_control_text


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
NS = {"w": W_NS}


def _control(*lines: str) -> etree._Element:
    control = etree.Element(W + "sdt", nsmap={"w": W_NS})
    content = etree.SubElement(control, W + "sdtContent")
    for line in lines:
        node = etree.SubElement(etree.SubElement(etree.SubElement(content, W + "p"), W + "r"), W + "t")
        node.text = line
    return control


def _paragraph_texts(control: etree._Element) -> list[str]:
    return ["".join(item.xpath(".//w:t/text()", namespaces=NS))
            for item in control.find(W + "sdtContent").findall(W + "p")]


def test_multi_paragraph_control_collapses_to_one_line() -> None:
    control = _control("三重四极", "液质联用仪")
    set_control_text(control, "纯水机")
    assert _paragraph_texts(control) == ["纯水机"]


def test_single_paragraph_control_unchanged() -> None:
    control = _control("三重四极液质联用仪")
    set_control_text(control, "电子分析天平")
    assert _paragraph_texts(control) == ["电子分析天平"]


def test_empty_value_keeps_one_paragraph() -> None:
    control = _control("三重四极", "液质联用仪")
    set_control_text(control, "")
    assert _paragraph_texts(control) == [""]


def test_image_paragraph_survives() -> None:
    control = _control("图谱")
    content = control.find(W + "sdtContent")
    run = etree.SubElement(etree.SubElement(content, W + "p"), W + "r")
    etree.SubElement(run, W + "drawing")
    set_control_text(control, "https://example.com/a.png")
    paragraphs = content.findall(W + "p")
    assert len(paragraphs) == 2
    assert paragraphs[1].xpath(".//w:drawing", namespaces=NS)
