"""#520 — compare host codecs, not their spellings.

`locale.getpreferredencoding(False)` answers `cp936` on a Windows host and
`UTF-8` on CI, and `codecs.lookup` is the comparison that knows `UTF-8`,
`utf8` and `utf-8` are one codec (measured: `lookup("UTF-8").name == "utf-8"`,
`lookup("cp936").name == "gbk"`). It lives here, apart from the gate that uses
it, so a child interpreter can ask the same question on the real plane without
importing the gate — which drags `craft.adapters` and, through it, elasticsearch
and the provider stack (measured: 26.7s of cumulative import time).
"""
from __future__ import annotations

import codecs
import locale


def host_prefers(codec: str) -> bool:
    """Does the host's preferred codec *be* `codec`, however it is spelled?"""
    return (
        codecs.lookup(locale.getpreferredencoding(False)).name
        == codecs.lookup(codec).name
    )
