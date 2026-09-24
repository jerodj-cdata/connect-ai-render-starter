import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.steps import current_turn, describe_step, queries_in
from tests.conftest import tool_step


@pytest.mark.parametrize(
    "name, args, label",
    [
        ("getInstructions", {"driverName": "Salesforce"}, "Loading Salesforce SQL instructions"),
        ("getCatalogs", {}, "Listing connections"),
        ("getSchemas", {"catalogName": "Salesforce1"}, "Listing schemas in Salesforce1"),
        ("getTables", {"catalogName": "Salesforce1"}, "Listing tables in Salesforce1"),
        ("getTables", {"catalogName": "Salesforce1", "tableName": "Opp%"},
         "Listing tables in Salesforce1 matching Opp%"),
        ("getColumns", {"catalogName": "Salesforce1", "tableName": "Opportunity"},
         "Inspecting columns of Opportunity in Salesforce1"),
        ("queryData", {"query": "SELECT 1"}, "Running a SQL query"),
        ("getProcedures", {}, "Looking up stored procedures"),
        ("execute_update", {}, "Writing data (execute_update)"),
        ("somethingNew", None, "Calling somethingNew"),
    ],
)
def test_describe_step(name, args, label):
    assert describe_step(name, args) == label


def test_current_turn_is_everything_after_the_last_user_message():
    old = [HumanMessage("q1"), AIMessage("a1")]
    new = [*tool_step("getCatalogs", {}), AIMessage("a2")]
    assert current_turn([*old, HumanMessage("q2"), *new]) == new
    assert current_turn(new) == new  # no user message at all


def test_queries_in_reports_sql_and_failures():
    messages = [
        *tool_step("getCatalogs", {}),
        *tool_step("queryData", {"query": "SELECT bad"}, "Error: no table", status="error", call_id="q1"),
        *tool_step("queryData", {"query": "SELECT Id FROM [Salesforce1].[Salesforce].[Account]"}, call_id="q2"),
    ]
    assert queries_in(messages) == [
        {"sql": "SELECT bad", "ok": False},
        {"sql": "SELECT Id FROM [Salesforce1].[Salesforce].[Account]", "ok": True},
    ]
