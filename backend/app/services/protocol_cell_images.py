"""Extract embedded Word table-cell images without interpreting field meanings."""
import base64

from docx.oxml.ns import qn


_VML_IMAGE = '{urn:schemas-microsoft-com:vml}imagedata'


def cell_images(cell, part) -> list[str]:
    identifiers = []
    for element in cell._tc.iter():
        if element.tag == qn('a:blip'):
            if element.get(qn('r:link')):
                raise ValueError('方案表格含外链图片，请先将图片嵌入文档')
            identifiers.append(element.get(qn('r:embed')))
        elif element.tag == _VML_IMAGE:
            identifiers.append(element.get(qn('r:id')))
    result = []
    for identifier in identifiers:
        if not identifier or identifier not in part.related_parts:
            raise ValueError('方案表格的内嵌图片关系不存在')
        image = part.related_parts[identifier]
        if not image.content_type.startswith('image/') or not image.blob or len(image.blob) > 8 * 1024 * 1024:
            raise ValueError('方案表格图片的格式或大小无效')
        media_type = 'image/emf' if image.content_type == 'image/x-emf' else image.content_type
        result.append(f'data:{media_type};base64,{base64.b64encode(image.blob).decode("ascii")}')
    return result
