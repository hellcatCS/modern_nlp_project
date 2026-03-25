from src.local_embeddings import is_openai_geo_blocked_error


def test_geo_blocked_detection():
    class Fake(Exception):
        pass

    e = Fake(
        "Error code: 403 - {'error': {'code': 'unsupported_country_region_territory', "
        "'message': 'Country, region, or territory not supported'}}"
    )
    assert is_openai_geo_blocked_error(e) is True
    assert is_openai_geo_blocked_error(RuntimeError("other")) is False


def test_geo_blocked_from_body_dict():
    class WithBody(Exception):
        def __init__(self):
            super().__init__("permission denied")
            self.body = {
                "error": {
                    "code": "unsupported_country_region_territory",
                    "message": "Country, region, or territory not supported",
                }
            }

    assert is_openai_geo_blocked_error(WithBody()) is True
