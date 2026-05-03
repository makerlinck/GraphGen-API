from api.services.connection import test_connection as _test_connection


class TestConnectionService:
    def test_test_connection_returns_tuple(self):
        success, message = _test_connection(
            base_url="https://invalid.example.com/v1",
            api_key="fake-key",
            model="gpt-4",
        )
        assert isinstance(success, bool)
        assert isinstance(message, str)
        assert not success
