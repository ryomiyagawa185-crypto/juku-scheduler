"""トークン計数。

重要: 既定の実装は**推定**であって実測ではない。日本語は1文字あたりの
トークン数が英語と大きく違うため、推定値で予算をブロックすると誤爆する。

入力トークン回帰テスト（tests/cost/）と予算見積りで意味のある数字を得るには、
本物のカウンタを注入すること:

    from origin_core import tokens
    tokens.set_counter(lambda text, model: client.messages.count_tokens(...))

set_counter() を呼ばない限り is_estimate() が True を返し、
policy 側は「推定値では予算判定をしない」という選択ができる。
"""

from __future__ import annotations

import re
from typing import Callable, Optional

_counter: Optional[Callable[[str, Optional[str]], int]] = None

_CJK = re.compile(
    r"[぀-ヿ㐀-䶿一-鿿豈-﫿ｦ-ﾟ]"
)


def set_counter(fn: Callable[[str, Optional[str]], int]) -> None:
    """実測カウンタを注入する（count_tokens API / トークナイザ）。"""
    global _counter
    _counter = fn


def reset_counter() -> None:
    global _counter
    _counter = None


def is_estimate() -> bool:
    """True の間、count() の戻り値は推定値。"""
    return _counter is None


def count(text: str, model: str | None = None) -> int:
    if _counter is not None:
        return _counter(text, model)
    return estimate(text)


def estimate(text: str) -> int:
    """粗い推定。CJK は約1文字1トークン、それ以外は約4文字1トークン。

    実測の代わりにはならない。桁を外さないための当て推量として使う。
    """
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    other = len(text) - cjk
    return cjk + (other + 3) // 4
