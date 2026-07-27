from __future__ import annotations

import json
import os
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from viventium_health.whoop import USER_AGENT, WHOOP_RESOURCES

OPENAPI_URL = "https://api.prod.whoop.com/developer/doc/openapi.json"


@unittest.skipUnless(
    os.environ.get("VIVENTIUM_HEALTH_LIVE_CONTRACT") == "1",
    "set VIVENTIUM_HEALTH_LIVE_CONTRACT=1 for official WHOOP contract checks",
)
class LiveWhoopContractTests(unittest.TestCase):
    def test_current_openapi_matches_every_configured_path_scope_and_paging_control(self) -> None:
        request = Request(OPENAPI_URL, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
        with urlopen(request, timeout=30) as response:
            document = json.load(response)
        self.assertEqual(document["openapi"], "3.0.1")
        self.assertIn("https://api.prod.whoop.com/developer", {server["url"] for server in document["servers"]})
        paths = document["paths"]
        for resource in WHOOP_RESOURCES:
            openapi_path = resource.path.removeprefix("/developer")
            self.assertIn(openapi_path, paths)
            operation = paths[openapi_path]["get"]
            scopes = {
                scope
                for requirement in operation.get("security", [])
                for scope in requirement.get("OAuth", [])
            }
            self.assertIn(resource.scope, scopes)
            if resource.collection:
                parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}
                self.assertTrue({"start", "end", "limit", "nextToken"} <= set(parameters))
                self.assertEqual(parameters["limit"]["schema"]["maximum"], 25)

    def test_unauthenticated_live_collection_fails_closed(self) -> None:
        request = Request(
            "https://api.prod.whoop.com/developer/v2/cycle?limit=1",
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=30)
        try:
            self.assertEqual(caught.exception.code, 401)
        finally:
            caught.exception.close()


if __name__ == "__main__":
    unittest.main()
