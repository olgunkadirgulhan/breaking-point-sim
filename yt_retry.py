"""Google bu projede ara ara geçici 401 'Invalid Credentials' veriyor: her YouTube API çağrısını
token yenileyip birkaç kez tekrar dener. Sadece import etmek yeter: `import yt_retry  # noqa`."""
import time

import googleapiclient.http as _h
from google.auth.transport.requests import Request

_orig = _h.HttpRequest.execute


def _execute(self, *a, **k):
    for attempt in range(5):
        try:
            return _orig(self, *a, **k)
        except _h.HttpError as e:
            if e.resp.status != 401 or attempt == 4:
                raise
            print(f"transient 401, retry {attempt + 1}", flush=True)
            time.sleep(5 * (attempt + 1))
            creds = getattr(self.http, "credentials", None)
            if creds is not None:
                creds.refresh(Request())


_h.HttpRequest.execute = _execute
