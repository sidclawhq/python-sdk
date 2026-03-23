from sidclaw.mcp.interceptor import derive_resource_scope, find_mapping
from sidclaw.mcp.config import ToolMapping


class TestFindMapping:
    def test_exact_match(self):
        mappings = [ToolMapping(tool_name="db_query")]
        assert find_mapping("db_query", mappings) is not None
        assert find_mapping("db_insert", mappings) is None

    def test_wildcard_prefix(self):
        mappings = [ToolMapping(tool_name="db_*")]
        assert find_mapping("db_query", mappings) is not None
        assert find_mapping("db_insert", mappings) is not None
        assert find_mapping("api_query", mappings) is None

    def test_wildcard_suffix(self):
        mappings = [ToolMapping(tool_name="*_query")]
        assert find_mapping("db_query", mappings) is not None
        assert find_mapping("api_query", mappings) is not None
        assert find_mapping("db_insert", mappings) is None

    def test_exact_match_preferred(self):
        mappings = [
            ToolMapping(tool_name="db_*", operation="generic"),
            ToolMapping(tool_name="db_query", operation="specific"),
        ]
        m = find_mapping("db_query", mappings)
        assert m is not None
        assert m.operation == "specific"


class TestDeriveResourceScope:
    def test_path_key(self):
        assert derive_resource_scope("tool", {"path": "/data/file.csv"}) == "/data/file.csv"

    def test_table_key(self):
        assert derive_resource_scope("tool", {"table": "users"}) == "users"

    def test_fallback_to_tool_name(self):
        assert derive_resource_scope("my_tool", {"other": "value"}) == "my_tool"

    def test_priority_order(self):
        assert derive_resource_scope("tool", {"table": "users", "path": "/data"}) == "/data"
