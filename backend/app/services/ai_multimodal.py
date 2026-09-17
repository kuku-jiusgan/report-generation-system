import base64
import binascii
import re
from typing import Any


_IMAGE_DATA_URL = re.compile(
    r"data:image/(?P<subtype>[A-Za-z0-9.+-]+);base64,"
    r"(?P<payload>[A-Za-z0-9+/]+={0,2})"
    r"(?=$|[\"'\s,;，；)\]}])"
)


def _validate_image_data_url(match: re.Match[str]) -> None:
    try:
        content = base64.b64decode(match.group("payload"), validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("AI 提示词包含无效的 Base64 图片 Data URL") from error
    if not content:
        raise ValueError("AI 提示词包含空图片 Data URL")


def build_message_content(prompt: str) -> str | list[dict[str, Any]]:
    """将提示词中的图片 Data URL 转为 OpenAI 兼容的多模态消息。"""
    images: dict[str, int] = {}

    def replace_image(match: re.Match[str]) -> str:
        _validate_image_data_url(match)
        data_url = match.group(0)
        image_number = images.setdefault(data_url, len(images) + 1)
        return f"[图片 {image_number}，已作为视觉输入附加]"

    text = _IMAGE_DATA_URL.sub(replace_image, prompt)
    if "data:image/" in text:
        raise ValueError("AI 提示词包含格式错误的图片 Data URL")
    if not images:
        return prompt
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    content.extend(
        {"type": "image_url", "image_url": {"url": data_url}}
        for data_url in images
    )
    return content
